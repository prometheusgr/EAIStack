# Adding a LangGraph Agent

This is the canonical worked example for adding a second agent alongside `chat_agent`. Follow this pattern exactly — a new agent should look like `chat_agent.py`, not invent a new shape.

Governing standards live in [AGENTS.md](../AGENTS.md); this doc is the how-to. See also [BACKEND_SERVICES.md](BACKEND_SERVICES.md) and [REPOSITORY_PATTERN.md](REPOSITORY_PATTERN.md) for the layers an agent's tools typically call into.

## Directory Shape

Each agent gets its own module in `app/agents/` and its own prompt module in `app/prompts/`:

```
app/agents/
  chat_agent.py        # existing agent: TypedDict state + factory + graph wiring
  summarizer_agent.py  # a hypothetical second agent, same shape
  checkpointer.py       # shared: SqlAlchemyCheckpointSaver works for any graph, not agent-specific
  registry.py            # name -> AgentDefinition lookup, see below
app/prompts/
  chat_prompts.py         # chat_agent's PromptTemplate instances
  summarizer_prompts.py   # summarizer_agent's own prompts, not appended to chat_prompts.py
```

Don't put a second agent's prompts in an existing agent's prompts module, and don't share a state `TypedDict` between two agents whose state actually differs — see "No premature abstraction" below.

## 1. Write a Failing Test First (TDD)

Follow `tests/unit/test_chat_agent.py`'s shape: build the graph with a `FakeChatModel`, invoke it, assert on the resulting state.

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

    Same per-request construction as chat_agent.create_chat_agent, and for
    the same reason: any bound tool or checkpointer must be scoped to this
    caller's own validated credentials and db session.
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

**Key points, matching `chat_agent.py`:**
- Factory signature is `(db: Session, token: str, mcp_url: str) -> CompiledStateGraph` — even an agent with no MCP tool takes `token`/`mcp_url`, so every registered agent has one uniform factory signature (see `AgentFactory` in `registry.py`).
- Built per-request, not cached: any tool or checkpointer construction must bind the caller's own already-validated token, never a bare `user_id`.
- Compiled with `SqlAlchemyCheckpointSaver(db)` — this class is already generic across any graph, not chat_agent-specific.

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

No inline `SystemMessage(...)` constants in the agent module — this is the exact pattern Phase 4 replaced in `chat_agent.py`.

## 4. Register the Agent

```python
# app/agents/registry.py
from app.agents.summarizer_agent import create_summarizer_agent

_REGISTRY: dict[str, AgentDefinition] = {
    "chat": AgentDefinition(name="chat", factory=create_chat_agent),
    "summarizer": AgentDefinition(name="summarizer", factory=create_summarizer_agent),
}
```

`name` is the stable identifier for logging, audit entries, and (if exposed over HTTP) the API path segment — not the Python module or function name.

## 5. Wire an Endpoint (if the agent is user-facing)

Follow `app/api/agents.py`'s `POST /api/agents/chat` shape: resolve the agent via `get_agent_definition(name).factory(...)`, run input guardrails before invoking it and output guardrails on its response (see `app/guardrails/`), touch/commit the owning thread, and return.

## Run Tests

```bash
pytest tests/unit/test_summarizer_agent.py -v
pytest tests/unit/test_agent_registry.py -v
pytest tests/unit/ -v
```

## No Premature Abstraction

This doc describes the pattern for a *second* agent, not a plugin framework. `registry.py` is a plain dict, not a dynamic loader — with one real agent registered today, there is nothing to auto-discover. Don't build a shared `BaseAgentState` or a generic tool-binding abstraction until a second real agent actually needs one; two agents whose states happen to both have `messages`/`thread_id`/`user_id` is not yet a reason to extract a shared type (see AGENTS.md's "No premature abstractions").

## Code Review Checklist for a New Agent

- [ ] Own module in `app/agents/`, own prompts module in `app/prompts/`
- [ ] Factory signature is `(db: Session, token: str, mcp_url: str) -> CompiledStateGraph`
- [ ] Built per-request (not cached/module-level), compiled with `SqlAlchemyCheckpointSaver(db)`
- [ ] No inline `SystemMessage(...)` constants — prompts are `PromptTemplate` instances
- [ ] Registered in `app/agents/registry.py` with a stable `name`
- [ ] Unit-tested with `FakeChatModel`, following `test_chat_agent.py`'s shape
- [ ] If user-facing: endpoint runs input guardrails before invoking, output guardrails on the response
