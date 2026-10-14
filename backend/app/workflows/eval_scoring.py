"""Scoring one eval run of a workflow test case (issue #84 slice B).

Pure: a run is first reduced to a CaseRunObservation (by
app.services.workflow_eval_service), then judged here against the case's
checks, so every scoring rule is unit-tested without an LLM.

Details never quote the model's reply - only the test's own expectations
and schema locations - so eval results hold no conversation content and can
be kept as publish evidence after the conversation itself is purged.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from app.workflows.primitives import choose_route_branch, review_rounds_key
from app.workflows.schema import EvalCaseDef, ReviewLoopStepDef, RouteStepDef, WorkflowDef

CheckKind = Literal["structural", "content"]
RunOutcome = Literal["completed", "timed_out", "rejected_by_input_guardrail", "error"]

_INCOMPLETE_RUN_DETAIL: dict[RunOutcome, str] = {
    "timed_out": "the run timed out",
    "rejected_by_input_guardrail": "the input guardrail rejected the test input",
    "error": "the run failed with an error",
}


@dataclass(frozen=True)
class CaseRunObservation:
    """What one run of a test case did, as far as its checks can see.

    reply is the guarded reply (what a user would have been shown);
    tools_called are the tools left in the final state's messages - for a
    review_loop worker, only the finalized round's (see docs/WORKFLOWS.md).
    """

    outcome: RunOutcome
    reply: str = ""
    step_outputs: Mapping[str, str] = field(default_factory=dict)
    tools_called: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CheckResult:
    check: str
    kind: CheckKind
    passed: bool
    detail: str


def score_case_run(
    case: EvalCaseDef,
    definition: WorkflowDef,
    observation: CaseRunObservation,
) -> list[CheckResult]:
    """One CheckResult per check the case declares.

    A run that didn't complete fails every check, with the reason as detail.
    """
    results = list(_check_results(case, definition, observation))
    if observation.outcome == "completed":
        return results
    reason = _INCOMPLETE_RUN_DETAIL[observation.outcome]
    return [CheckResult(r.check, r.kind, passed=False, detail=reason) for r in results]


def run_passed(results: list[CheckResult]) -> bool:
    """A run passes when it was checked at all and every check passed."""
    return bool(results) and all(result.passed for result in results)


def case_passed(case: EvalCaseDef, run_passes: Iterable[bool]) -> bool:
    return sum(1 for passed in run_passes if passed) >= case.required_passes()


def _check_results(
    case: EvalCaseDef, definition: WorkflowDef, observation: CaseRunObservation
) -> Iterable[CheckResult]:
    expect = case.expect
    if expect.route is not None:
        yield _route_result(definition, observation, expect.route.step, expect.route.branch)
    if expect.review_rounds_at_most is not None:
        yield _review_rounds_result(
            definition,
            observation,
            expect.review_rounds_at_most.step,
            expect.review_rounds_at_most.rounds,
        )
    if expect.tool_called is not None:
        yield _tool_called_result(observation, expect.tool_called)
    for expected_text in expect.reply_contains:
        yield _reply_contains_result(observation, expected_text)
    if expect.reply_json_schema is not None:
        yield _reply_json_schema_result(observation, expect.reply_json_schema)


def _route_result(
    definition: WorkflowDef, observation: CaseRunObservation, step: str, expected_branch: str
) -> CheckResult:
    route_step = definition.steps[step]
    assert isinstance(route_step, RouteStepDef)  # guaranteed by schema validation
    if step not in observation.step_outputs:
        return CheckResult("route", "structural", False, f"route step '{step}' did not run")
    taken = choose_route_branch(observation.step_outputs[step], list(route_step.branches))
    if taken == expected_branch:
        return CheckResult("route", "structural", True, f"route step '{step}' took '{taken}'")
    return CheckResult(
        "route",
        "structural",
        False,
        f"route step '{step}' took '{taken}', expected '{expected_branch}'",
    )


def _review_rounds_result(
    definition: WorkflowDef, observation: CaseRunObservation, step: str, max_rounds: int
) -> CheckResult:
    loop_step = definition.steps[step]
    assert isinstance(loop_step, ReviewLoopStepDef)  # guaranteed by schema validation
    rounds_taken = observation.step_outputs.get(review_rounds_key(loop_step.reviewer_step))
    if rounds_taken is None:
        return CheckResult(
            "review_rounds_at_most", "structural", False, f"review loop '{step}' did not run"
        )
    rounds = int(rounds_taken)
    return CheckResult(
        "review_rounds_at_most",
        "structural",
        rounds <= max_rounds,
        f"review loop '{step}' finished in {rounds} round(s), limit {max_rounds}",
    )


def _tool_called_result(observation: CaseRunObservation, tool_name: str) -> CheckResult:
    if tool_name in observation.tools_called:
        return CheckResult("tool_called", "structural", True, f"'{tool_name}' was called")
    return CheckResult("tool_called", "structural", False, f"'{tool_name}' was not called")


def _reply_contains_result(observation: CaseRunObservation, expected_text: str) -> CheckResult:
    if expected_text.casefold() in observation.reply.casefold():
        return CheckResult("reply_contains", "content", True, f"reply contains '{expected_text}'")
    return CheckResult(
        "reply_contains", "content", False, f"reply does not contain '{expected_text}'"
    )


def _reply_json_schema_result(observation: CaseRunObservation, schema: dict) -> CheckResult:
    try:
        reply_json = json.loads(observation.reply)
    except json.JSONDecodeError:
        return CheckResult("reply_json_schema", "content", False, "reply is not valid JSON")
    error = best_match(Draft202012Validator(schema).iter_errors(reply_json))
    if error is None:
        return CheckResult("reply_json_schema", "content", True, "reply matches the schema")
    # The schema path, never error.message: the message quotes the reply.
    schema_location = "/".join(str(part) for part in error.relative_schema_path)
    return CheckResult(
        "reply_json_schema",
        "content",
        False,
        f"reply fails the schema at {schema_location or '(root)'}",
    )
