# Multi-Agent Workflow Engine (Issue #81, Epic #80)

**Status**: engine slice implemented (slice 1 of 5). This document is the YAML
reference for the workflow engine that composes agents into LangGraph graphs
declaratively. See `docs/AGENT_LIBRARY.md` for the hand-coded-agent pattern
this engine's `agent` primitive generalizes, and epic #80 for the full
multi-slice plan (versioned store + admin UI in #83, iteration loop in #84,
workflow selection in chat in #85).

## What this is, and isn't

A workflow is a YAML file composing a small, fixed set of code-defined
primitives (`agent`, `sequence` via `next`, `route`, `review_loop`) into a
LangGraph `StateGraph`. YAML is validated (Pydantic) at load time and
**compiled** to a graph — it is never a general-purpose scripting language,
and it can never reach an unregistered tool or an LLM call outside the
engine's own boundary. A fork needing a new primitive adds it in code, with
tests, in `backend/app/workflows/primitives.py` — not by extending YAML's
expressiveness.

This slice ships one built-in workflow, `backend/workflows/chat.yaml`, which
re-expresses today's chat agent through the engine with identical behavior —
proof the engine covers what the hand-coded agent already did. There is no
DB-backed store, admin UI, or workflow-selection UI yet (later slices).

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
```

- `prompt` is inline text, matching `PromptTemplate`'s own current scope (no
  variable substitution yet — add it when a concrete workflow needs it).
- `tools` names must be registered in `app.workflows.tool_registry` — an
  unregistered name is rejected at load time, so a workflow definition can
  never reach a tool the engine doesn't know about. Today's only registered
  tool is `search_knowledge_base`.
- A tool-bound agent step gets the same tool-call routing
  `chat_agent.py` used to hand-wire: up to 5 tool-call rounds
  (`app.workflows.compiler._MAX_TOOL_CALL_ROUNDS`, a fixed constant — see
  "Configuration" below) before it's forced to its `next` step (or `END`).
- Omitting `next` makes this step terminal for whatever branch reaches it.

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
approves or rejects, looping until approval or a bounded number of rounds.

```yaml
worker:                                  # top-level step name (referenced by entry/next)
  type: review_loop
  worker_step: worker_agent              # internal node name for the worker
  reviewer_step: reviewer_agent          # internal node name for the reviewer
  worker_prompt: "Draft an answer."
  reviewer_prompt: "Review the answer; reply 'approve' or 'reject: <why>'."
  approve_keyword: approve
  max_iterations: 3                      # required; see the ceiling below
```

- The reviewer's response is checked for `approve_keyword` as a substring;
  finding it ends the loop. Otherwise the worker runs again, up to
  `max_iterations` worker/reviewer rounds — the loop always terminates even
  if the reviewer never approves, surfacing whatever the worker last
  produced rather than hanging the request.
- `max_iterations` is **required** (no default) and bounded by a hard,
  non-overridable ceiling: `REVIEW_LOOP_MAX_ITERATIONS_CEILING = 10`
  (`app.workflows.schema`). A workflow definition — even one an admin
  authors through a later slice's UI — can never raise the number of LLM
  calls a single review loop makes per turn above this. See "Configuration"
  below.
- The top-level step name (`worker` in the example) is a label for the
  whole worker/reviewer pair, not itself a graph node — `entry: worker`
  resolves to `worker_step`'s actual node internally
  (`app.workflows.compiler.compile_workflow`'s `entry_nodes` map).

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

## Worked example: a minimal review loop

```yaml
name: reviewed_answer
version: 1
entry: worker
steps:
  worker:
    type: review_loop
    worker_step: worker_agent
    reviewer_step: reviewer_agent
    worker_prompt: "Draft a concise answer to the user's question."
    reviewer_prompt: >-
      Review the draft answer. If it directly and correctly answers the
      question, reply exactly 'approve'. Otherwise reply 'reject: <reason>'.
    approve_keyword: approve
    max_iterations: 3
```

This is illustrative only — the actual reference review-loop and routing
workflows (with production-quality prompts) ship in issue #82, not this
slice.

## Configuration

Per `AGENTS.md`'s TDD Discipline step 0 (every new numeric/boolean knob
must be explicitly called out as an admin setting or a named constant):

| Value | Kind | Why |
|---|---|---|
| `WORKFLOW_DEFINITIONS_DIR` | Env-only, no DB override | A deploy-time filesystem path (where a fork mounts its own workflow directory). Restart-only by nature since the container's filesystem is what changes — a DB override adds nothing over setting the env var and restarting. |
| `REVIEW_LOOP_MAX_ITERATIONS_CEILING` (`app.workflows.schema`) | Fixed code constant, never DB-editable | Safety ceiling on LLM calls per turn. A workflow edit — even an admin-authored one, in a later slice — must not be able to raise the number of LLM calls a single review loop makes. Per-workflow `max_iterations` lives in the YAML, bounded by this. |
| `_MAX_TOOL_CALL_ROUNDS` (`app.workflows.compiler`) | Fixed code constant | The same fixed cap `chat_agent.py`'s `MAX_TOOL_CALL_ROUNDS` used, applied to any YAML-defined tool-bound agent step. Not yet YAML-configurable: no workflow has needed a different value, and making it per-step configurable ahead of a real need would be a premature abstraction. |

Neither of these two constants is a `SystemSettings`-backed admin knob — see
the table for why in each case.

## Testing

- `backend/tests/unit/test_workflow_primitives.py` — each primitive in
  isolation, hand-built graphs, `FakeChatModel`.
- `backend/tests/unit/test_workflow_schema.py` — every validation rule.
- `backend/tests/unit/test_workflow_compiler.py` — schema → compiler →
  runnable graph, for each primitive type.
- `backend/tests/unit/test_workflow_loader.py` — directory scanning,
  multi-file loading, invalid-file error propagation.
- `backend/tests/unit/test_agent_registry.py` — the name → factory lookup.
- `backend/tests/unit/test_chat_workflow.py` — the built-in `chat.yaml`
  workflow specifically, loaded and compiled the same way
  `app.main`'s lifespan hook does, proving the engine reproduces every
  behavior the old hand-coded `chat_agent.py` had (tool-call routing,
  thread persistence, the max-tool-call-round cap, source extraction).
- `backend/tests/unit/test_main_lifespan.py` — a corrupted built-in workflow
  file fails app startup with a `WorkflowValidationError`, not a runtime
  500.

**Scripted per-node fake harness**: `app.core.llm_client.FakeChatModel`'s
existing `responses: list[AIMessage]` queue (consumed one-per-call, in
invocation order) is reused directly for multi-step workflows — see
`test_workflow_compiler.py`'s review-loop test for the "reviewer rejects
once, then approves" pattern. Each step's own `get_llm_client(db)` call
resolves to the same shared `FakeChatModel` instance in a test, so its
queue is consumed across steps in the order they actually run.

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
