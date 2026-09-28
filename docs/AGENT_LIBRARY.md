# Adding a LangGraph Agent

**Two ways to add an agent, as of issue #81:**

1. **A declarative workflow (the default choice)**: compose the engine's
   fixed primitives (`agent`, `sequence`, `route`, `review_loop`) in a YAML
   file under `backend/workflows/`. This is how the built-in chat agent
   itself works today (`backend/workflows/chat.yaml`) — see
   [docs/WORKFLOWS.md](WORKFLOWS.md) for the full YAML reference. Prefer
   this path whenever the agent's logic fits the engine's primitive set; it
   needs no new Python module, gets `app.agents.registry` wiring for free,
   and (in later slices of epic #80) versioning, an admin UI, and audit
   trail with zero extra code.
2. **A hand-coded agent (this document's worked example)**: for logic the
   engine's primitives don't yet cover — a genuinely custom graph shape, or
   a structured-output/state pattern the primitives don't express. Follow
   this pattern exactly — a new hand-coded agent should look like
   `summarizer_agent.py` below, not invent a new shape.

Governing standards live in [AGENTS.md](../AGENTS.md); this doc is the how-to. See also [BACKEND_SERVICES.md](BACKEND_SERVICES.md) and [REPOSITORY_PATTERN.md](REPOSITORY_PATTERN.md) for the layers an agent's tools typically call into.

## Directory Shape

A hand-coded agent gets its own module in `app/agents/` and its own prompt module in `app/prompts/`:

```
app/agents/
  registry.py           # name -> AgentDefinition lookup (shared across both hand-coded and YAML-compiled agents), see below
  checkpointer.py        # shared: SqlAlchemyCheckpointSaver works for any graph, not agent-specific
  summarizer_agent.py   # a hypothetical hand-coded agent, same shape this doc walks through
app/prompts/
  summarizer_prompts.py  # summarizer_agent's own prompts
app/workflows/
  primitives.py, schema.py, compiler.py, loader.py, tool_registry.py  # the declarative engine — see docs/WORKFLOWS.md
backend/workflows/
  chat.yaml              # the built-in chat agent, expressed as a one-step workflow (not a hand-coded module)
```

Don't put a second agent's prompts in an existing agent's prompts module, and don't share a state `TypedDict` between two hand-coded agents whose state actually differs — see "No premature abstraction" below. (The engine's own `WorkflowState`, in `app.workflows.primitives`, is the one shared state shape every YAML-compiled workflow uses — that sharing is deliberate, since every such workflow runs through the same generic primitives, not an exception to this guidance.)

## 1. Write a Failing Test First (TDD)

Follow `tests/unit/test_chat_workflow.py`'s shape: build the graph with a `FakeChatModel`, invoke it, assert on the resulting state. (That file exercises the built-in chat *workflow*, not a hand-coded agent — but its state-building/assertion shape is the same one a hand-coded agent's test follows.)

```python
# tests/unit/test_summarizer_agent.py
def test_summarizer_agent_invoke_with_message(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.agents.summarizer_agent.get_llm_client",
        lambda db: FakeChatModel(response="Summary: ..."),
    )
    graph = create_summarizer_agent(db=db_session, token=_UNUSED_TOKEN, mcp_url=_UNREACHABLE_MCP_URL)
    ...
```

## 2. Define the Agent's State and Factory

```python
# app/agents/summarizer_agent.py
"""LangGraph agent for summarizing a document."""

from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy.orm import Session

from app.agents.checkpointer import SqlAlchemyCheckpointSaver
from app.core.llm_client import get_llm_client
from app.prompts.summarizer_prompts import SUMMARIZER_SYSTEM_PROMPT


class SummarizerState(TypedDict):
    """State for the summarizer agent."""

    messages: Annotated[list, add_messages]
    thread_id: str
    user_id: str


def create_summarizer_agent(db: Session, token: str, mcp_url: str):
    """Create and compile the summarizer agent graph for one request.

    Same per-request construction every factory in this codebase uses
    (both hand-coded and YAML-compiled, via app.workflows.compiler.
    compile_workflow), and for the same reason: any bound tool or
    checkpointer must be scoped to this caller's own validated credentials
    and db session.
    """
    llm = get_llm_client(db)

    def call_agent(state: SummarizerState) -> SummarizerState:
        response = llm.invoke([SUMMARIZER_SYSTEM_PROMPT.render(), *state["messages"]])
        return {**state, "messages": [response]}

    graph = StateGraph(SummarizerState)
    graph.add_node("call_agent", call_agent)
    graph.set_entry_point("call_agent")
    graph.add_edge("call_agent", END)

    return graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db))
```

**Key points, matching every other agent in this codebase (hand-coded or YAML-compiled):**
- Factory signature is `(db: Session, token: str, mcp_url: str) -> CompiledStateGraph` — even an agent with no MCP tool takes `token`/`mcp_url`, so every registered agent has one uniform factory signature (see `AgentFactory` in `registry.py`).
- Built per-request, not cached: any tool or checkpointer construction must bind the caller's own already-validated token, never a bare `user_id`.
- Compiled with `SqlAlchemyCheckpointSaver(db)` — this class is generic across any graph, not agent-specific.

## 3. Add the Agent's Prompts

```python
# app/prompts/summarizer_prompts.py
"""Prompt templates for the summarizer agent (app.agents.summarizer_agent)."""

from app.prompts.prompt_template import PromptTemplate

SUMMARIZER_SYSTEM_PROMPT = PromptTemplate(
    name="summarizer_system",
    version=1,
    template="You summarize documents in three sentences or fewer.",
)
```

No inline `SystemMessage(...)` constants in the agent module — this is the exact pattern Phase 4 established, and that `chat_agent.py` (since superseded by `backend/workflows/chat.yaml`, see issue #81) originally set.

## 4. Register the Agent

`app.agents.registry` is populated two ways: YAML-compiled workflows are registered automatically at startup by `app.main`'s lifespan hook (see [docs/WORKFLOWS.md](WORKFLOWS.md)); a hand-coded agent registers itself explicitly, the same shape `register_workflow_definitions` produces:

```python
# app/agents/registry.py, near register_workflow_definitions
from app.agents.summarizer_agent import create_summarizer_agent

_REGISTRY["summarizer"] = AgentDefinition(
    name="summarizer",
    factory=create_summarizer_agent,
    system_prompt=SUMMARIZER_SYSTEM_PROMPT.template,
)
```

`name` is the stable identifier for logging, audit entries, and (if exposed over HTTP) the API path segment — not the Python module or function name. `system_prompt` exists on every `AgentDefinition` (not just YAML-compiled ones) because `app.api.agents`'s output-guardrail leak detector needs the exact text a given agent's model call was given, regardless of how that agent was built.

## 5. Wire an Endpoint (if the agent is user-facing)

Follow `app/api/agents.py`'s `POST /api/agents/chat` shape: resolve the agent via `get_agent_definition(name).factory(...)`, run input guardrails before invoking it and output guardrails on its response (see `app/guardrails/`), touch/commit the owning thread, and return.

## Run Tests

```bash
pytest tests/unit/test_summarizer_agent.py -v
pytest tests/unit/test_agent_registry.py -v
pytest tests/unit/ -v
```

## No Premature Abstraction

This doc describes the pattern for a hand-coded agent alongside the engine, not a plugin framework. `registry.py`'s `_REGISTRY` is a plain dict — workflow registration is automatic (the loader scans one directory once at startup), but a hand-coded agent still registers itself explicitly, by design: with zero hand-coded agents registered today (the built-in `chat` workflow is YAML-compiled, not hand-coded), there is nothing to auto-discover on that path. Don't build a shared `BaseAgentState` or a generic tool-binding abstraction for hand-coded agents until a second real one actually needs it — the engine's own `WorkflowState` (`app.workflows.primitives`) already covers the "many similar agents share a state shape" case for anything expressible as a workflow (see AGENTS.md's "No premature abstractions").

## Code Review Checklist for a New Agent

- [ ] Own module in `app/agents/`, own prompts module in `app/prompts/`
- [ ] Factory signature is `(db: Session, token: str, mcp_url: str) -> CompiledStateGraph`
- [ ] Built per-request (not cached/module-level), compiled with `SqlAlchemyCheckpointSaver(db)`
- [ ] No inline `SystemMessage(...)` constants — prompts are `PromptTemplate` instances
- [ ] Registered in `app/agents/registry.py` with a stable `name`
- [ ] Unit-tested with `FakeChatModel`, following `test_chat_workflow.py`'s shape
- [ ] If user-facing: endpoint runs input guardrails before invoking, output guardrails on the response
