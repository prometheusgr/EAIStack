# Multi-Agent Workflow Engine (Issues #81/#82, Epic #80)

**Status**: engine slice (1 of 5) plus reference workflows (slice 2 of 5)
implemented. This document is the YAML reference for the workflow engine
that composes agents into LangGraph graphs declaratively. See
`docs/AGENT_LIBRARY.md` for the hand-coded-agent pattern this engine's
`agent` primitive generalizes, and epic #80 for the full multi-slice plan
(versioned store + admin UI in #83, iteration loop in #84, workflow
selection in chat in #85).

## What this is, and isn't

A workflow is a YAML file composing a small, fixed set of code-defined
primitives (`agent`, `sequence` via `next`, `route`, `review_loop`) into a
LangGraph `StateGraph`. YAML is validated (Pydantic) at load time and
**compiled** to a graph — it is never a general-purpose scripting language,
and it can never reach an unregistered tool or an LLM call outside the
engine's own boundary. A fork needing a new primitive adds it in code, with
tests, in `backend/app/workflows/primitives.py` — not by extending YAML's
expressiveness.

Three built-in workflows ship today:

- `backend/workflows/chat.yaml` — re-expresses the chat agent through the
  engine with identical behavior (slice 1); the only one wired to an HTTP
  endpoint (`POST /api/agents/chat`).
- `backend/workflows/reviewed_answer.yaml` — interpret → work → review loop
  (slice 2, issue #82), the evaluator-optimizer reference workflow.
- `backend/workflows/triage.yaml` — route to specialists (slice 2, issue
  #82), the routing reference workflow.

The latter two are reference examples for forkers, not reachable by any
endpoint yet — workflow *selection* in chat is issue #85's scope. There is
no DB-backed store or admin UI yet either (later slices).

## Directory & loading

- Built-in workflow definitions live in `backend/workflows/*.yaml`.
- `WORKFLOW_DEFINITIONS_DIR` (env var, default `workflows`, relative to the
  backend process's working directory) points at that directory — a fork or
  Helm deployment can mount its own directory without rebuilding the image.
  Env-only, not DB-overridable: this is a deploy-time filesystem path,
  restart-only by nature (see `backend/app/core/config.py`'s field comment).
- `app.workflows.loader.load_workflow_definitions(directory)` reads every
  `*.yaml` file, parses and validates each one, and returns a
  `dict[name, WorkflowDef]` keyed by each definition's own `name` field.
- `app.main`'s lifespan hook calls the loader once at process startup and
  registers every definition into `app.agents.registry` — **a broken YAML
  file fails the container at boot** with a `WorkflowValidationError` naming
  the file and field, not a 500 on the first chat request.

## Versioned store & the Workflows screen (issue #83)

Postgres is the system of record for workflows; the YAML files above are the
*built-in defaults*, recorded into the store at startup.

- **Startup sync** (`app.services.workflow_service.sync_builtin_versions`): each
  built-in file whose text differs from its last recorded built-in version is
  stored as a new `source=builtin` version. It becomes active only if the active
  version is itself a built-in; if an admin has published their own version, the
  new built-in is recorded and the Workflows screen shows "built-in update
  available" instead. A restart with unchanged files is a no-op.
- **Versions are immutable** (`workflow_versions`, append-only, per-workflow
  `sequence`, hash-chained — see `app/workflows/version_chain.py`). There is no
  status column: "published" means the per-workflow pointer
  (`workflow_active_versions`) points at it; a saved version it has never pointed
  at is a draft.
- **Lifecycle** (all admin-only, all audited — see `docs/AUDIT_EVENTS.md`):
  1. *Create* a new workflow (`POST /api/workflows`; name comes from the YAML),
     or edit an existing one — saving a draft (`POST /api/workflows/{name}/versions`)
     validates it with exactly the startup rules plus a required change note.
     Editing a built-in never modifies it; the draft is an `admin` version.
  2. *Publish* (`POST /api/workflows/{name}/publish`) after confirming the diff
     against the active version on screen. Live from the next chat turn.
  3. *Roll back* (`POST /api/workflows/{name}/rollback`) re-publishes an older
     version, recorded as `workflow.rolled_back`.
- **What runs**: `POST /api/agents/chat` resolves the *published* `chat` version
  per request (`resolve_active_workflow`), records it in `chat_turn_versions`, and
  tags the run's trace metadata with `workflow_name`/`workflow_version_id`.
  Thread replay's output-guardrail re-filter uses the same published prompt.
  New workflows are not reachable from chat until workflow selection (issue #85).
- **Not yet built**: the step diagram endpoint exists
  (`GET /api/workflows/{name}/versions/{id}/graph`) but the screen doesn't draw it
  yet; no syntax highlighting (plain textarea; a highlighting editor would need
  vendoring); no file upload/bulk import; no rename or delete of a workflow.

## Schema reference

Every workflow file has this top-level shape:

```yaml
name: chat          # stable identifier — registry lookup key, not the filename
version: 1           # documents intent (bump when wording/behavior changes); not yet read programmatically, same as PromptTemplate.version
entry: respond       # the step name execution starts at
steps:
  respond:           # step name, referenced by entry/next/branches
    type: agent
    ...
```

### `agent`

One LLM-calling step.

```yaml
respond:
  type: agent
  prompt: "You are a helpful assistant..."   # inline system prompt text
  tools:                                      # optional; names from the tool registry
    - search_knowledge_base
  next: polish                                # optional; chains to another step (the `sequence` pattern)
  output_field: task                          # optional; see below
```

- `prompt` is inline text, matching `PromptTemplate`'s own current scope (no
  variable substitution of its own — see `review_loop`'s `{task}`/`{draft}`/
  `{review_issues}` substitution below, which is scoped to that primitive,
  not a general `PromptTemplate` feature).
- `tools` names must be registered in `app.workflows.tool_registry` — an
  unregistered name is rejected at load time, so a workflow definition can
  never reach a tool the engine doesn't know about. Today's only registered
  tool is `search_knowledge_base`.
- A tool-bound agent step gets the same tool-call routing
  `chat_agent.py` used to hand-wire: up to 5 tool-call rounds
  (`app.workflows.compiler._MAX_TOOL_CALL_ROUNDS`, a fixed constant — see
  "Configuration" below) before it's forced to its `next` step (or `END`).
- Omitting `next` makes this step terminal for whatever branch reaches it.
- `output_field` (optional, only valid value today: `task`): writes this
  step's response to workflow state (`state["task"]`) instead of appending
  it to `messages`. Used by an **interpreter** step that feeds a downstream
  `review_loop`'s `{task}` prompt placeholder — see "State shape decision"
  below for why this exists.

### `sequence`

Not a distinct `type` — chain `agent` steps with `next`, e.g. `draft` →
`polish`. Each step in the chain runs in order; the graph ends after the
last step in the chain (the one with no `next`).

### `route`

An LLM-classified branch to one of several named steps.

```yaml
classify:
  type: route
  prompt: "Classify the request as billing or support."
  branches:
    billing: billing_agent
    support: support_agent
```

The classifier step's raw text response is matched against each branch
name; the first branch name found as a substring of the response wins. An
unrecognized response falls back to the first declared branch rather than
raising — the classifier is an LLM call, and per `AGENTS.md`'s "error
handling only at system boundaries," a malformed response degrades
predictably instead of crashing the graph mid-turn.

### `review_loop`

The evaluator–optimizer pattern: a worker step drafts, a reviewer step
returns a **structured** verdict that approves or rejects, looping until
approval or a bounded number of rounds.

```yaml
worker:                                  # top-level step name (referenced by entry/next)
  type: review_loop
  worker_step: worker_agent              # internal node name for the worker
  reviewer_step: reviewer_agent          # internal node name for the reviewer
  worker_prompt: >-
    Complete the task: {task}
    Reviewer feedback (if any): {review_issues}
  worker_tools:                          # optional; same registry as `agent`'s `tools`
    - search_knowledge_base
  reviewer_prompt: >-
    Review this draft against the task.
    Task: {task}
    Draft: {draft}
  max_iterations: 3                      # required; see the ceiling below
```

- **Structured reviewer output, not a keyword match.** The reviewer's LLM
  call goes through `with_structured_output(ReviewResult)`
  (`app.workflows.primitives.ReviewResult`: `{approved: bool, issues:
  list[str]}`), which maps to the OpenAI-compatible `response_format:
  json_schema` request llama.cpp's server honors as grammar-constrained
  decoding — not prose a substring match is applied to. This replaced
  slice 1's illustrative-only `approve_keyword` scheme (issue #82): local
  models' free-text critiques are unreliable and code can't branch on them.
  `review.approved == true` ends the loop; otherwise the worker runs again,
  up to `max_iterations` worker/reviewer rounds — the loop always
  terminates even if the reviewer never approves, surfacing whatever the
  worker last produced rather than hanging the request.
- **Malformed reviewer output is handled, not a crash.** If the structured-
  output call raises (the model's response didn't conform to the schema),
  the round is treated as `ReviewResult(approved=False, issues=["reviewer
  output could not be parsed"])` and still counts against
  `max_iterations` — an LLM response is never fully trustworthy at this
  system boundary (`AGENTS.md`'s "error handling only at system
  boundaries").
- `worker_tools` (optional, default none): tool names from the same
  registry `agent`'s `tools` uses. A worker step with tools resolves its
  own tool calls internally (up to 5 rounds, mirroring
  `_MAX_TOOL_CALL_ROUNDS`), **asynchronously** — `search_knowledge_base` is
  a coroutine-only tool, so a review_loop's worker node is always `async
  def` regardless of whether it binds tools, and a workflow containing a
  `review_loop` step must be invoked via `graph.ainvoke()`, not
  `graph.invoke()`.
- `worker_prompt`/`reviewer_prompt` may reference `{task}`, `{draft}`, and
  (worker only) `{review_issues}` — substituted via plain `str.format()`
  from workflow state on every round (missing/not-yet-populated fields
  render as `""`, never `KeyError`). See "State shape decision" below.
- `max_iterations` is **required** (no default) and bounded by a hard,
  non-overridable ceiling: `REVIEW_LOOP_MAX_ITERATIONS_CEILING = 10`
  (`app.workflows.schema`). A workflow definition — even one an admin
  authors through a later slice's UI — can never raise the number of LLM
  calls a single review loop makes per turn above this. See "Configuration"
  below.
- The top-level step name (`worker` in the example) is a label for the
  whole worker/reviewer pair, not itself a graph node — `entry: worker`
  resolves to `worker_step`'s actual node internally
  (`app.workflows.compiler.compile_workflow`'s `entry_nodes` map). An
  earlier step's `next` can also target a review_loop step by its
  top-level name (as `reviewed_answer.yaml`'s `interpret` step does) — the
  compiler resolves that edge through the same map, not the raw step name.

#### State shape decision (issue #82)

A review_loop's intermediate worker drafts and reviewer verdicts are read
and written via dedicated `WorkflowState` fields — `task`, `draft`,
`review` (a `ReviewResult | None`) — **never** appended to `messages`.
`POST /api/agents/chat` (and any future caller) reads `result["messages"]
[-1]` as the reply shown to the user, so an unreviewed draft or a
reviewer's structured critique landing in `messages` would leak into the
visible transcript, and would also pollute the worker's own prompt context
on a revision round with its own prior, rejected attempts. Only the loop's
**final** draft (approved, or the last one produced when `max_iterations`
is reached) is appended to `messages`, once, when the loop ends — the one
message the whole loop ever contributes to the visible conversation. If
the worker used `worker_tools`, that final round's tool-call exchange
(`AIMessage` with `tool_calls` + the resulting `ToolMessage`s) is
re-attached alongside it, so `extract_sources_from_messages` can find the
sources that grounded the answer the user actually sees — exactly as it
already does for a plain tool-bound `agent` step.

`task` is written by an upstream **interpreter** step — a plain `agent`
step with `output_field: task` (see the `agent` section above) — so a
review_loop's worker/reviewer prompts can reference the restated task via
`{task}` without the interpreter's own response appearing in `messages`
either.

### `parallel`

Not yet implemented in this slice — the primitive set is fixed at `agent`,
`sequence` (via `next`), `route`, and `review_loop` for now. `parallel`
(fan-out/fan-in) is scoped for a later slice once a concrete workflow needs
it, per `AGENTS.md`'s no-premature-abstraction guidance.

## Validation rules (fail loudly at load time)

`app.workflows.schema.parse_workflow_definition` rejects, each with a
`WorkflowValidationError` naming the source file and the specific field:

- An `entry` that doesn't reference a defined step.
- An `agent` step's `tools` entry that isn't a registered tool name.
- A `next`/`branches` target that doesn't reference a defined step
  (dangling reference).
- Any step not reachable from `entry` by following `next`/`branches` edges
  (an orphaned step).
- A `review_loop` step missing `max_iterations`.
- A `review_loop`'s `max_iterations` exceeding
  `REVIEW_LOOP_MAX_ITERATIONS_CEILING`.
- A `review_loop` step's `worker_tools` entry that isn't a registered tool
  name (same check as `agent`'s `tools`).

## Worked examples: the reference workflows

These are the real, shipped built-in workflows (issue #82) — not
illustrative snippets. Both are reachable through
`app.workflows.loader.load_workflow_definitions` and
`app.agents.registry`, but neither is wired to an HTTP endpoint yet
(workflow selection in chat is issue #85's scope); they exist as
structurally-tested, copyable examples for a fork building its own
review-loop or routing workflow.

### `backend/workflows/reviewed_answer.yaml` — interpret → work → review loop

```yaml
name: reviewed_answer
version: 1
entry: interpret
steps:
  interpret:
    type: agent
    prompt: >-
      Restate the user's request as a precise, self-contained task
      specification ...
    output_field: task
    next: draft_and_review
  draft_and_review:
    type: review_loop
    worker_step: worker
    reviewer_step: reviewer
    worker_prompt: >-
      Complete the following task ... Task: {task} ...
      Reviewer feedback: {review_issues}
    worker_tools:
      - search_knowledge_base
    reviewer_prompt: >-
      Review this draft against the task ...
      Task: {task}
      Draft: {draft}
    max_iterations: 3
```

An **interpreter** (`agent`, `output_field: task`) restates the request as
a task spec, then a **worker** (bound to `search_knowledge_base`) drafts an
answer and a **reviewer** returns a structured verdict, looping until
approved or `max_iterations` rounds. See the full file for the actual
production-quality prompt text.

### `backend/workflows/triage.yaml` — route to specialists

```yaml
name: triage
version: 1
entry: classify
steps:
  classify:
    type: route
    prompt: "Classify the user's request as exactly one of: technical, general."
    branches:
      technical: technical_specialist
      general: general_specialist
  technical_specialist:
    type: agent
    prompt: "You are a technical support specialist ..."
    tools:
      - search_knowledge_base
  general_specialist:
    type: agent
    prompt: "You are a general-purpose assistant ..."
```

Uses the `route` primitive exactly as slice 1 shipped it — no engine
changes were needed for this half of issue #82, only this file and its
structural test.

### Real-model verification (issue #82 DoD)

Both workflows were exercised by hand against a real llama-server +
embedding-server + doc-search stack (`docker-compose up --profile llm`,
Meta-Llama-3.1-8B-Instruct Q4_K_M, CPU inference), in addition to the
`FakeChatModel`-based structural tests below, by invoking each compiled
graph directly through `app.agents.registry` (neither workflow is wired to
an endpoint yet). Confirmed working end-to-end: the reviewer returned real
grammar-constrained JSON (`ReviewResult`) each round, not prose; a worker
tool-call failure (an unauthenticated placeholder token against doc-search,
expected in this ad-hoc script) was caught and handled without crashing the
loop; the final answer contained no leaked reviewer text or intermediate
drafts; `triage.yaml` classified and routed correctly on both branches.

Observed per-turn latency (CPU inference, 12 threads, single run — not a
benchmark, but representative of the cost shape):

| Workflow | Rounds | Elapsed |
|---|---|---|
| `reviewed_answer.yaml` (interpret + 3 worker/reviewer rounds, reviewer never approved — bounded correctly by `max_iterations`) | 1 interpret + 3×(worker + reviewer) = 7 LLM calls | ~345s |
| `triage.yaml` (technical branch: classify + specialist) | 2 LLM calls | ~25s |
| `triage.yaml` (general branch: classify + specialist) | 2 LLM calls | ~14s |

The review loop's cost scales linearly with `max_iterations` — each round
is a full worker + reviewer inference pair, so a 3-round loop costs
roughly 3.5x a single triage turn. This is the expected trade-off for
local CPU inference and is unchanged by this issue (the engine's cost
shape was already this way in slice 1); it's noted here because it's the
first workflow to actually exercise a multi-round loop against a real
model.

## Configuration

Per `AGENTS.md`'s TDD Discipline step 0 (every new numeric/boolean knob
must be explicitly called out as an admin setting or a named constant):

| Value | Kind | Why |
|---|---|---|
| `WORKFLOW_DEFINITIONS_DIR` | Env-only, no DB override | A deploy-time filesystem path (where a fork mounts its own workflow directory). Restart-only by nature since the container's filesystem is what changes — a DB override adds nothing over setting the env var and restarting. |
| `REVIEW_LOOP_MAX_ITERATIONS_CEILING` (`app.workflows.schema`) | Fixed code constant, never DB-editable | Safety ceiling on LLM calls per turn. A workflow edit — even an admin-authored one, in a later slice — must not be able to raise the number of LLM calls a single review loop makes. Per-workflow `max_iterations` lives in the YAML, bounded by this. |
| `_MAX_TOOL_CALL_ROUNDS` (`app.workflows.compiler`) | Fixed code constant | The same fixed cap `chat_agent.py`'s `MAX_TOOL_CALL_ROUNDS` used, applied to any YAML-defined tool-bound agent step. Not yet YAML-configurable: no workflow has needed a different value, and making it per-step configurable ahead of a real need would be a premature abstraction. |
| `_WORKER_MAX_TOOL_CALL_ROUNDS` (`app.workflows.primitives`) | Fixed code constant | The same cap as `_MAX_TOOL_CALL_ROUNDS`, applied to a `review_loop` worker's own internal tool-call resolution. Private to `primitives.py` since a worker's tool calls are resolved inside one node invocation, never as separate graph nodes the compiler wires up. |

None of these three constants is a `SystemSettings`-backed admin knob — see
the table for why in each case. Per issue #82's own configuration call-out:
no new admin-configurable field was introduced — `max_iterations` lives in
each workflow's YAML, already bounded by `REVIEW_LOOP_MAX_ITERATIONS_CEILING`.

## Testing

- `backend/tests/unit/test_workflow_primitives.py` — each primitive in
  isolation, hand-built graphs, `FakeChatModel` (including the structured
  `ReviewResult` reviewer, malformed-output handling, `{task}`/`{draft}`
  prompt substitution, and a worker resolving its own tool calls).
- `backend/tests/unit/test_workflow_schema.py` — every validation rule,
  including `worker_tools` and the `entry_prompt`/`entry_prompt_or_none`
  distinction for a non-`agent` entry step.
- `backend/tests/unit/test_workflow_compiler.py` — schema → compiler →
  runnable graph, for each primitive type, including a `next` edge from an
  `agent` step into a `review_loop` step's worker node.
- `backend/tests/unit/test_workflow_loader.py` — directory scanning,
  multi-file loading, invalid-file error propagation.
- `backend/tests/unit/test_agent_registry.py` — the name → factory lookup,
  including a route-entry workflow registering with `system_prompt=None`.
- `backend/tests/unit/test_chat_workflow.py` — the built-in `chat.yaml`
  workflow specifically, loaded and compiled the same way
  `app.main`'s lifespan hook does, proving the engine reproduces every
  behavior the old hand-coded `chat_agent.py` had (tool-call routing,
  thread persistence, the max-tool-call-round cap, source extraction).
- `backend/tests/unit/test_reference_workflows.py` — `reviewed_answer.yaml`
  and `triage.yaml` specifically, loaded and compiled the same way, covering
  first-pass approval, reject-then-revise, hitting `max_iterations`, and
  both routing branches.
- `backend/tests/unit/test_main_lifespan.py` — a corrupted built-in workflow
  file fails app startup with a `WorkflowValidationError`, not a runtime
  500.

**Scripted per-node fake harness**: `app.core.llm_client.FakeChatModel`'s
existing `responses: list[AIMessage]` queue (consumed one-per-call, in
invocation order) is reused directly for multi-step workflows — see
`test_workflow_compiler.py`'s review-loop test for the "reviewer rejects
once, then approves" pattern. Each step's own `get_llm_client(db)` call
resolves to the same shared `FakeChatModel` instance in a test, so its
queue is consumed across steps in the order they actually run. A separate
`structured_responses: list[BaseModel]` queue, consumed by its own
`with_structured_output()` override, scripts a reviewer's structured
verdicts independently of the worker's prose queue on the same shared
instance.

**A workflow containing a `review_loop` step must be invoked with
`graph.ainvoke()`, not `graph.invoke()`** — its worker node is always
`async def` (see the `review_loop` section above), so a sync `invoke()`
raises `TypeError`. Every other primitive (`agent`, `route`) still works
under either.

## Adding a new built-in workflow

1. Write a `*.yaml` file under `backend/workflows/`.
2. Add a test (following `test_chat_workflow.py`'s shape) that loads it via
   `load_workflow_definitions` and compiles it via `compile_workflow`,
   exercising its behavior with `FakeChatModel`.
3. If it should be reachable over HTTP, wire an endpoint the way
   `POST /api/agents/chat` resolves `get_agent_definition("chat")` — see
   `docs/AGENT_LIBRARY.md`'s endpoint-wiring step. Workflow *selection* in
   chat (letting a user pick which workflow to run) is issue #85's scope,
   not this slice's.
