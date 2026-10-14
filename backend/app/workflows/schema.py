"""Pydantic schema and load-time validation for YAML workflow definitions.

YAML composes a small, fixed set of primitives (app.workflows.primitives);
this module is the boundary that turns a raw parsed YAML dict into a
validated WorkflowDef, or raises a WorkflowValidationError naming exactly
what's wrong — a workflow definition is untrusted input (an admin- or
fork-authored file) the same way any other request body is, so it gets
the same "reject clearly rather than fail deep inside the compiler"
treatment AGENTS.md's "error handling at system boundaries" calls for.

Field-level shape is Pydantic's job (a required field, a wrong type);
cross-referential rules that Pydantic's field validators can't express on
their own (a step referencing another step that doesn't exist, an
unreachable step, an unregistered tool name) are enforced by
_validate_definition, once the whole tree has parsed.
"""

from typing import Annotated, Any, Literal, Union

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.workflows.tool_registry import is_registered_tool

# Hard ceiling on review_loop's max_iterations, independent of anything
# admin-configurable: a workflow definition (even one an admin authored
# through a later slice's UI) must never be able to raise the number of
# LLM calls a single review loop can make per turn above this. Lives here,
# in the module that enforces it, not app.core.config.Settings — mirrors
# app.guardrails.input_guardrail.MAX_INPUT_LENGTH_CEILING's placement
# (see AGENT_LIBRARY.md-adjacent config precedent: a ceiling is a fixed
# code constant enforced at the validation boundary, never a DB-overridable
# SystemSettings field, since that would let the thing it constrains
# disable the constraint).
REVIEW_LOOP_MAX_ITERATIONS_CEILING = 10

# Eval-run cost ceilings (issue #84), fixed for the same reason as the
# review-loop ceiling above: an eval run multiplies CPU-bound LLM calls, and
# a YAML edit must never be able to raise that without bound. Enforced when a
# version is saved, so an over-budget suite is a validation error rather than
# a run that discovers its own cost halfway through.
EVAL_RUNS_PER_CASE_CEILING = 10
EVAL_MAX_CASE_RUNS_PER_SUITE = 50

# JSON-schema keywords that take a regular expression. Rejected anywhere in
# a test case's reply_json_schema, matching the guardrails' rule that admin
# configuration never supplies regex (no ReDoS surface; see issue #16).
# Deliberately conservative: a property literally named "pattern" is
# rejected too.
_REGEX_SCHEMA_KEYWORDS = frozenset({"pattern", "patternProperties"})


class WorkflowValidationError(Exception):
    """A workflow definition failed validation.

    Carries the source file name and the specific field/step at fault, so
    a startup failure (app.workflows.loader) names exactly what's wrong
    rather than surfacing a bare Pydantic traceback — per issue #81's DoD:
    "Invalid definitions fail loudly at startup with a clear error naming
    the file and field."
    """

    def __init__(self, *, file: str, field: str, message: str):
        self.file = file
        self.field = field
        self.message = message
        super().__init__(f"{file}: {field}: {message}")


class AgentStepDef(BaseModel):
    """A single LLM-calling step.

    prompt is inline template text, matching PromptTemplate's own current
    scope (app/prompts/prompt_template.py — "nothing yet needs variable
    substitution... add it when a concrete prompt needs it"). tools names
    a subset of app.workflows.tool_registry's registered tools; an empty
    list (the default) means this step calls the LLM with no tools bound.
    next, if set, chains to another step (the `sequence` primitive); a
    step with no next is a terminal step for its branch of the graph.

    output_field, when set to "task", writes this step's response to
    state["task"] instead of appending it to `messages` (see
    app.workflows.primitives.build_agent_node's output_field param and
    WorkflowState's docstring) — how an interpreter step feeds a
    downstream review_loop's {task} prompt placeholder without the
    restated task itself appearing in the visible conversation. Only
    "task" is a valid value here: "draft"/"review" are written internally
    by build_review_loop's own worker/reviewer nodes, never by a plain
    `agent` step.
    """

    type: Literal["agent"]
    prompt: str
    tools: list[str] = Field(default_factory=list)
    next: str | None = None
    output_field: Literal["task"] | None = None


class ReviewLoopStepDef(BaseModel):
    """The evaluator-optimizer pattern: a worker step and a reviewer step,
    looping until the reviewer's structured verdict (ReviewResult.approved,
    see app.workflows.primitives) is true, or max_iterations rounds have
    run.

    No approve_keyword field (issue #82 replaces slice 1's illustrative-only
    prose keyword match): the reviewer's approval is grammar-constrained
    JSON output, not a substring match against free text.

    worker_prompt/reviewer_prompt may reference {task}, {draft}, and (for
    reviewer_prompt) {review_issues} — substituted from workflow state by
    app.workflows.primitives.build_review_loop; see docs/WORKFLOWS.md.
    """

    type: Literal["review_loop"]
    worker_step: str
    reviewer_step: str
    worker_prompt: str
    worker_tools: list[str] = Field(default_factory=list)
    reviewer_prompt: str
    max_iterations: int


class RouteStepDef(BaseModel):
    """An LLM-classified branch: prompt asks the model to choose, and
    branches maps each expected answer to the step name it dispatches to.
    """

    type: Literal["route"]
    prompt: str
    branches: dict[str, str]


StepDef = Annotated[
    Union[AgentStepDef, ReviewLoopStepDef, RouteStepDef], Field(discriminator="type")
]


class RouteExpectation(BaseModel):
    """The route step `step` dispatched to `branch`."""

    model_config = ConfigDict(extra="forbid")

    step: str
    branch: str


class ReviewRoundsExpectation(BaseModel):
    """The review_loop step `step` finished within `rounds` rounds."""

    model_config = ConfigDict(extra="forbid")

    step: str
    rounds: int


class EvalExpectations(BaseModel):
    """The checks one test case makes (scored by app.workflows.eval_scoring).

    Structural checks (route, review_rounds_at_most, tool_called) inspect
    how the workflow ran and are deterministic under a scripted fake model;
    content checks (reply_contains, reply_json_schema) inspect the guarded
    reply and only mean something against a real model.

    extra="forbid": a misspelled check name must fail validation, not
    become a check that silently never runs.
    """

    model_config = ConfigDict(extra="forbid")

    route: RouteExpectation | None = None
    review_rounds_at_most: ReviewRoundsExpectation | None = None
    tool_called: str | None = None
    # Literal, case-insensitive substrings - never regex.
    reply_contains: list[str] = Field(default_factory=list)
    reply_json_schema: dict[str, Any] | None = None

    def is_empty(self) -> bool:
        return (
            self.route is None
            and self.review_rounds_at_most is None
            and self.tool_called is None
            and not self.reply_contains
            and self.reply_json_schema is None
        )


class EvalCaseDef(BaseModel):
    """One test case: an input, run `runs` times, passing when at least
    `min_passes` of those runs pass every check (default: all of them).

    Several runs per case because a real model varies from run to run: a
    pass rate, not a single pass/fail, is what an eval reports. The
    threshold is a whole number of runs rather than a fractional rate, so
    "2 of 3" can't be lost to rounding (2/3 < 0.67).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    input: str
    runs: int = Field(default=1, ge=1)
    min_passes: int | None = Field(default=None, ge=1)
    expect: EvalExpectations

    def required_passes(self) -> int:
        return self.min_passes if self.min_passes is not None else self.runs


class WorkflowDef(BaseModel):
    """A fully validated workflow definition, ready for
    app.workflows.compiler.compile_workflow.

    name is the stable identifier used for registry lookup and (in a
    later slice) audit/version tracking — not the source filename.
    """

    name: str
    version: int
    # One line shown to end users when they pick a workflow in chat
    # (issue #85). Optional so a fork's existing definitions stay valid.
    description: str = ""
    entry: str
    steps: dict[str, StepDef]
    # Issue #84: versioned with the workflow, so the evidence for a publish
    # is pinned to the exact suite that version carried.
    tests: list[EvalCaseDef] = Field(default_factory=list)

    def guarded_prompt_text(self) -> str:
        """Every prompt this workflow sends to the model, joined.

        What the output guardrail's verbatim-leak check compares a reply
        against. A workflow whose entry is a route or review_loop step has no
        single "system prompt", and any of its steps' prompts could be the
        one a model is coaxed into repeating, so all of them are protected.
        """
        prompts: list[str] = []
        for step in self.steps.values():
            if isinstance(step, ReviewLoopStepDef):
                prompts.extend([step.worker_prompt, step.reviewer_prompt])
            else:
                prompts.append(step.prompt)
        return "\n\n".join(prompts)

    def entry_prompt_or_none(self) -> str | None:
        """entry_prompt(), or None for a workflow whose entry step isn't a
        single `agent` step, instead of raising.

        Used by app.agents.registry.register_workflow_definitions, which
        registers every loaded workflow uniformly regardless of its entry
        step's type (issue #82 ships reviewed_answer.yaml/triage.yaml,
        whose entries are `agent`/`route` respectively — neither is wired
        to an endpoint yet, so there's no guardrail leak-check that needs
        their prompt text today; see AgentDefinition.system_prompt's
        docstring).
        """
        entry_step = self.steps[self.entry]
        if not isinstance(entry_step, AgentStepDef):
            return None
        return entry_step.prompt

    def entry_prompt(self) -> str:
        """The entry step's prompt text, for callers that need this
        workflow's system prompt outside the compiled graph itself (e.g.
        app.api.agents.chat passing it to the output guardrail's leak
        detector, which must compare against the *exact* text the model
        was given — see app.guardrails.output_guardrail).

        Only meaningful for a workflow whose entry step is an `agent` step
        (true of chat.yaml, the only workflow this slice ships); a
        route/review_loop entry has no single "the" system prompt, so
        this raises rather than silently returning a wrong/empty string.
        Callers that can tolerate a route/review_loop entry (e.g. the
        registry, which must register every loaded workflow uniformly)
        should use entry_prompt_or_none() instead.
        """
        entry_step = self.steps[self.entry]
        if not isinstance(entry_step, AgentStepDef):
            raise ValueError(
                f"entry_prompt() is only defined for an `agent`-type entry step; "
                f"'{self.entry}' is type={entry_step.type!r}"
            )
        return entry_step.prompt


def _step_targets(step_name: str, step: StepDef) -> list[str]:
    """The other step names a given step can transition to, used both for
    dangling-reference checking and reachability analysis.
    """
    if isinstance(step, AgentStepDef):
        return [step.next] if step.next else []
    if isinstance(step, ReviewLoopStepDef):
        return (
            []
        )  # worker_step/reviewer_step are step labels *within* this primitive, not references to other top-level steps
    if isinstance(step, RouteStepDef):
        return list(step.branches.values())
    return []


def _validate_definition(definition: WorkflowDef, *, source_file: str) -> None:
    """Cross-referential checks that span the whole definition tree."""
    step_names = set(definition.steps.keys())

    if definition.entry not in step_names:
        raise WorkflowValidationError(
            file=source_file,
            field="entry",
            message=f"entry '{definition.entry}' does not reference a defined step",
        )

    for step_name, step in definition.steps.items():
        if isinstance(step, AgentStepDef):
            for tool_name in step.tools:
                if not is_registered_tool(tool_name):
                    raise WorkflowValidationError(
                        file=source_file,
                        field=f"steps.{step_name}.tools",
                        message=f"unknown tool '{tool_name}' is not registered",
                    )

        if isinstance(step, ReviewLoopStepDef):
            if step.max_iterations > REVIEW_LOOP_MAX_ITERATIONS_CEILING:
                raise WorkflowValidationError(
                    file=source_file,
                    field=f"steps.{step_name}.max_iterations",
                    message=(
                        f"max_iterations={step.max_iterations} exceeds the fixed ceiling "
                        f"of {REVIEW_LOOP_MAX_ITERATIONS_CEILING}"
                    ),
                )
            for tool_name in step.worker_tools:
                if not is_registered_tool(tool_name):
                    raise WorkflowValidationError(
                        file=source_file,
                        field=f"steps.{step_name}.worker_tools",
                        message=f"unknown tool '{tool_name}' is not registered",
                    )

        for target in _step_targets(step_name, step):
            if target not in step_names:
                raise WorkflowValidationError(
                    file=source_file,
                    field=f"steps.{step_name}",
                    message=f"references undefined step '{target}'",
                )

    reachable = _reachable_steps(definition)
    unreachable = step_names - reachable
    if unreachable:
        raise WorkflowValidationError(
            file=source_file,
            field="steps",
            message=f"unreachable step(s) not reachable from entry '{definition.entry}': {sorted(unreachable)}",
        )

    _validate_eval_cases(definition, source_file=source_file)


def _validate_eval_cases(definition: WorkflowDef, *, source_file: str) -> None:
    """A test case may only reference steps, branches and tools that exist,
    and the whole suite must fit the eval cost ceilings."""
    seen_names: set[str] = set()
    for case in definition.tests:
        prefix = f"tests.{case.name}"

        def reject(field: str, message: str) -> None:
            raise WorkflowValidationError(file=source_file, field=field, message=message)

        if case.name in seen_names:
            reject(f"{prefix}.name", f"duplicate test case name '{case.name}'")
        seen_names.add(case.name)

        if case.runs > EVAL_RUNS_PER_CASE_CEILING:
            reject(
                f"{prefix}.runs",
                f"runs={case.runs} exceeds the fixed ceiling of {EVAL_RUNS_PER_CASE_CEILING}",
            )

        if case.min_passes is not None and case.min_passes > case.runs:
            reject(
                f"{prefix}.min_passes",
                f"min_passes={case.min_passes} is more than the case's runs ({case.runs})",
            )

        expect = case.expect
        if expect.is_empty():
            reject(f"{prefix}.expect", "a test case must declare at least one check")

        if expect.route is not None:
            route_step = definition.steps.get(expect.route.step)
            if not isinstance(route_step, RouteStepDef):
                reject(f"{prefix}.expect.route", f"'{expect.route.step}' is not a route step")
            elif expect.route.branch not in route_step.branches:
                reject(
                    f"{prefix}.expect.route",
                    f"'{expect.route.branch}' is not a branch of route step '{expect.route.step}'",
                )

        if expect.review_rounds_at_most is not None:
            rounds_check = expect.review_rounds_at_most
            loop_step = definition.steps.get(rounds_check.step)
            if not isinstance(loop_step, ReviewLoopStepDef):
                reject(
                    f"{prefix}.expect.review_rounds_at_most",
                    f"'{rounds_check.step}' is not a review_loop step",
                )
            elif not 1 <= rounds_check.rounds <= loop_step.max_iterations:
                reject(
                    f"{prefix}.expect.review_rounds_at_most",
                    f"rounds must be between 1 and the step's max_iterations "
                    f"({loop_step.max_iterations})",
                )

        if expect.tool_called is not None and not is_registered_tool(expect.tool_called):
            reject(
                f"{prefix}.expect.tool_called",
                f"unknown tool '{expect.tool_called}' is not registered",
            )

        if expect.reply_json_schema is not None:
            schema_problem = _json_schema_problem(expect.reply_json_schema)
            if schema_problem is not None:
                reject(f"{prefix}.expect.reply_json_schema", schema_problem)

    total_runs = sum(case.runs for case in definition.tests)
    if total_runs > EVAL_MAX_CASE_RUNS_PER_SUITE:
        raise WorkflowValidationError(
            file=source_file,
            field="tests",
            message=(
                f"the suite's runs add up to {total_runs}, above the fixed ceiling of "
                f"{EVAL_MAX_CASE_RUNS_PER_SUITE} per eval run"
            ),
        )


def _json_schema_problem(schema: dict[str, Any]) -> str | None:
    if _uses_regex_keyword(schema):
        return "regex keywords (pattern, patternProperties) are not allowed"
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return f"not a valid JSON schema: {exc.message}"
    return None


def _uses_regex_keyword(node: Any) -> bool:
    if isinstance(node, dict):
        return any(
            key in _REGEX_SCHEMA_KEYWORDS or _uses_regex_keyword(value)
            for key, value in node.items()
        )
    if isinstance(node, list):
        return any(_uses_regex_keyword(item) for item in node)
    return False


def _reachable_steps(definition: WorkflowDef) -> set[str]:
    """Steps reachable from entry by following each step's next/branches
    edges. review_loop steps have no outgoing top-level references (their
    worker/reviewer are internal labels, not other top-level steps), so
    they're always leaves in this traversal.
    """
    visited: set[str] = set()
    frontier = [definition.entry]
    while frontier:
        current = frontier.pop()
        if current in visited or current not in definition.steps:
            continue
        visited.add(current)
        frontier.extend(_step_targets(current, definition.steps[current]))
    return visited


def parse_workflow_definition(raw: dict, *, source_file: str) -> WorkflowDef:
    """Parse and fully validate one workflow definition (a dict, as
    yaml.safe_load would produce it) against the schema and this module's
    cross-referential rules.

    Raises WorkflowValidationError — never a bare pydantic.ValidationError
    — so every caller (the built-in loader today, an admin-facing draft
    validator in a later slice) gets one consistent, file/field-naming
    exception type to catch.
    """
    try:
        definition = WorkflowDef.model_validate(raw)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        field = ".".join(str(part) for part in first_error["loc"])
        raise WorkflowValidationError(
            file=source_file,
            field=field or "<root>",
            message=f"{field or '<root>'}: {first_error['msg']}",
        ) from exc

    _validate_definition(definition, source_file=source_file)

    # review_loop's max_iterations-required check is a plain Pydantic
    # required-field rule (no default), already enforced by model_validate
    # above via ReviewLoopStepDef's non-Optional field. Nothing further
    # needed here; kept out of _validate_definition to avoid duplicating a
    # check Pydantic already performs.

    return definition
