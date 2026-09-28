"""Tests for the built-in chat workflow (backend/workflows/chat.yaml),
loaded and compiled through the workflow engine.

Supersedes the old tests/unit/test_chat_agent.py: issue #81 re-expresses
the hand-coded chat_agent as a one-step YAML workflow, and this file
proves the engine reproduces every behavior that file pinned -- tool-call
routing, thread persistence, the max-tool-call-round cap, and source
extraction -- unchanged, against the actual chat.yaml file this repo
ships (not a hand-built WorkflowDef), so a regression in the shipped file
itself would fail these tests too.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage

from app.core.llm_client import FakeChatModel
from app.db.models import Embedding, KnowledgeBase
from app.mcp_client import Source
from app.repositories import ThreadRepository
from app.services import generate_embedding
from app.workflows.compiler import compile_workflow
from app.workflows.loader import load_workflow_definitions
from app.workflows.primitives import extract_sources_from_messages
from tests.conftest import FAKE_KEYCLOAK_PRIVATE_KEY
from tests.integration.doc_search_helper import (
    make_signed_token,
    running_doc_search_subprocess,
)

_CHAT_WORKFLOW_TEST_PORT = 8197

# Tests that never trigger a tool call don't need a reachable doc-search
# server -- token/mcp_url are still required by compile_workflow's
# signature (they're bound into the search tool unconditionally), but the
# fake LLM never emits tool_calls, so the tool is built but never invoked.
_UNUSED_TOKEN = "unused-token"
_UNREACHABLE_MCP_URL = "http://localhost:1/mcp"

_WORKFLOWS_DIR = str(Path(__file__).resolve().parents[2] / "workflows")


def _new_thread(db_session, user_id: str = "test-user") -> str:
    """Create a real ConversationThread row and return its id.

    The checkpointer's conversation_checkpoints table has a foreign key
    to conversation_threads, matching how the API layer always creates a
    thread via ThreadRepository before invoking the graph - tests must
    do the same rather than inventing arbitrary thread_id strings.
    """
    thread = ThreadRepository(db_session).get_or_create_owned(None, user_id)
    db_session.commit()
    return thread.id


def _compile_chat_workflow(
    db_session, *, token: str = _UNUSED_TOKEN, mcp_url: str = _UNREACHABLE_MCP_URL
):
    """Load the real, shipped chat.yaml and compile it -- the exact path
    app.main's lifespan hook and app.agents.registry take at process
    startup, not a hand-built definition.
    """
    definitions = load_workflow_definitions(_WORKFLOWS_DIR)
    return compile_workflow(definitions["chat"], db=db_session, token=token, mcp_url=mcp_url)


def _initial_state(message: str, thread_id: str, user_id: str = "test-user") -> dict:
    return {
        "messages": [HumanMessage(content=message)],
        "thread_id": thread_id,
        "user_id": user_id,
        "step_outputs": {},
    }


@pytest.mark.unit
def test_chat_workflow_prompt_still_instructs_direct_tool_result_use():
    """Regression guard for the specific llama.cpp behavior chat_agent.py's
    original inline comment documented (now chat.yaml's own comment):
    without this instruction, some local models describe a tool call's
    JSON instead of answering from its result. Re-expressing the prompt as
    YAML (issue #81) must not lose it.
    """
    definitions = load_workflow_definitions(_WORKFLOWS_DIR)
    prompt = definitions["chat"].entry_prompt().lower()

    assert "tool" in prompt
    assert "directly" in prompt


@pytest.mark.unit
def test_compile_chat_workflow_returns_runnable(db_session, monkeypatch):
    """Compiling the built-in chat workflow produces a runnable graph."""
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: FakeChatModel())
    graph = _compile_chat_workflow(db_session)
    assert graph is not None
    assert hasattr(graph, "invoke")


@pytest.mark.unit
def test_chat_workflow_invoke_with_message(db_session, monkeypatch):
    """The compiled chat workflow accepts a user message and returns a
    response, with no tool calls.
    """
    monkeypatch.setattr(
        "app.workflows.compiler.get_llm_client", lambda db: FakeChatModel(response="4")
    )
    graph = _compile_chat_workflow(db_session)
    thread_id = _new_thread(db_session)

    result = graph.invoke(
        _initial_state("What is 2+2?", thread_id),
        config={"configurable": {"thread_id": thread_id}},
    )

    final_message = result["messages"][-1]
    assert isinstance(final_message, AIMessage)
    assert final_message.content == "4"
    assert result["thread_id"] == thread_id


@pytest.mark.unit
def test_conversation_persists_across_two_invokes_same_thread_same_user(db_session, monkeypatch):
    """A second invoke on the same thread_id sees the first turn's messages."""
    fake_llm = FakeChatModel(responses=[AIMessage(content="4"), AIMessage(content="Yes, 2+2=4.")])
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: fake_llm)
    thread_id = _new_thread(db_session)
    config = {"configurable": {"thread_id": thread_id}}

    first_graph = _compile_chat_workflow(db_session)
    first_graph.invoke(_initial_state("What is 2+2?", thread_id), config=config)
    db_session.commit()

    second_graph = _compile_chat_workflow(db_session)
    result = second_graph.invoke(_initial_state("Are you sure?", thread_id), config=config)

    contents = [m.content for m in result["messages"]]
    assert "What is 2+2?" in contents
    assert "4" in contents
    assert "Are you sure?" in contents
    assert contents[-1] == "Yes, 2+2=4."


@pytest.mark.unit
def test_chat_workflow_invoke_passes_through_thread_id(db_session, monkeypatch):
    """The workflow passes through the thread_id unchanged."""
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: FakeChatModel())
    graph = _compile_chat_workflow(db_session)
    thread_id = _new_thread(db_session)

    result = graph.invoke(
        _initial_state("Hello", thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert result["thread_id"] == thread_id


@pytest.mark.unit
def test_chat_workflow_plain_response_skips_tool_node(db_session, monkeypatch):
    """A response with no tool_calls routes straight to END without invoking the tool."""
    fake_llm = FakeChatModel(response="No tool needed here.")
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: fake_llm)
    graph = _compile_chat_workflow(db_session)
    thread_id = _new_thread(db_session)

    result = graph.invoke(
        _initial_state("Hello", thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert fake_llm.call_count == 1
    messages = result["messages"]
    assert isinstance(messages[-1], AIMessage)
    assert messages[-1].content == "No tool needed here."


@pytest.mark.unit
def test_extract_sources_from_messages_collects_tool_message_artifacts():
    """Every ToolMessage in a turn's message list contributes its .artifact
    (a list[Source], see app.mcp_client.doc_search_client) to one flat,
    order-preserving list — the shape app.api.agents.chat needs to populate
    ChatResponse.sources, see issue #19.
    """
    messages = [
        HumanMessage(content="How many vacation days do I get?"),
        AIMessage(content="", tool_calls=[]),
        ToolMessage(
            content="Title: Vacation Policy\n25 days of paid vacation.",
            tool_call_id="call-1",
            artifact=[Source(knowledge_base_id="kb-1", title="Vacation Policy", heading_path=None)],
        ),
        AIMessage(content="You get 25 days of paid vacation per year."),
    ]

    sources = extract_sources_from_messages(messages)

    assert sources == [Source(knowledge_base_id="kb-1", title="Vacation Policy", heading_path=None)]


@pytest.mark.unit
def test_extract_sources_from_messages_deduplicates_by_knowledge_base_id():
    """Two tool calls in the same turn (or a re-ranked repeat match) that
    both surface the same document must not produce a duplicate source
    entry in the final response.
    """
    same_source = Source(knowledge_base_id="kb-1", title="Vacation Policy", heading_path=None)
    messages = [
        ToolMessage(content="...", tool_call_id="call-1", artifact=[same_source]),
        ToolMessage(content="...", tool_call_id="call-2", artifact=[same_source]),
    ]

    sources = extract_sources_from_messages(messages)

    assert sources == [same_source]


@pytest.mark.unit
def test_extract_sources_from_messages_returns_empty_list_when_no_tool_messages():
    """A turn that never called the tool (plain conversational answer)
    contributes no sources, not an error.
    """
    messages = [HumanMessage(content="Hello"), AIMessage(content="Hi there!")]

    assert extract_sources_from_messages(messages) == []


@pytest.mark.unit
def test_extract_sources_from_messages_tolerates_tool_message_with_no_artifact():
    """A ToolMessage from a tool other than search_knowledge_base (or the
    unreachable-server fallback, whose artifact is an empty list per
    doc_search_client) must not crash source extraction.
    """
    messages = [ToolMessage(content="unrelated tool output", tool_call_id="call-1")]

    assert extract_sources_from_messages(messages) == []


@pytest.mark.unit
def test_extract_sources_from_messages_ignores_a_prior_turns_sources():
    """result["messages"] from graph.ainvoke() is the FULL accumulated
    thread history (see test_conversation_persists_across_two_invokes_
    same_thread_same_user above), not just the current turn's new messages.
    A second turn that never calls the tool must not resurface the first
    turn's source -- regression test for a bug where every turn's sources
    silently accreted every document ever referenced anywhere earlier in
    the same thread, regardless of what grounded the current answer.
    """
    messages = [
        # Turn 1: grounded in Vacation Policy.
        HumanMessage(content="How many vacation days do I get?"),
        AIMessage(content="", tool_calls=[]),
        ToolMessage(
            content="Title: Vacation Policy\n25 days of paid vacation.",
            tool_call_id="call-1",
            artifact=[Source(knowledge_base_id="kb-1", title="Vacation Policy", heading_path=None)],
        ),
        AIMessage(content="You get 25 days of paid vacation per year."),
        # Turn 2: unrelated small talk, no tool call at all.
        HumanMessage(content="How are you today?"),
        AIMessage(content="I'm doing well, thanks for asking!"),
    ]

    sources = extract_sources_from_messages(messages)

    assert sources == []


@pytest.mark.unit
def test_extract_sources_from_messages_tolerates_a_prior_turns_checkpoint_restored_artifact():
    """A prior turn's ToolMessage, once round-tripped through
    SqlAlchemyCheckpointSaver's JsonPlusSerializer, comes back with
    .artifact as a plain dict (no custom serializer is registered for
    Source), not a Source instance -- source.knowledge_base_id on it would
    raise AttributeError. Extraction must never touch a prior turn's
    messages at all, so this dict-shaped artifact must never be inspected.
    """
    messages = [
        HumanMessage(content="How many vacation days do I get?"),
        AIMessage(content="", tool_calls=[]),
        ToolMessage(
            content="Title: Vacation Policy\n25 days of paid vacation.",
            tool_call_id="call-1",
            # Simulates the shape a checkpoint restore actually produces.
            artifact=[
                {"knowledge_base_id": "kb-1", "title": "Vacation Policy", "heading_path": None}
            ],
        ),
        AIMessage(content="You get 25 days of paid vacation per year."),
        HumanMessage(content="How are you today?"),
        AIMessage(content="I'm doing well, thanks for asking!"),
    ]

    sources = extract_sources_from_messages(messages)

    assert sources == []


@pytest.mark.integration
async def test_chat_workflow_tool_call_routes_to_tool_and_grounds_final_answer(
    db_session, test_db_url, fake_keycloak_jwks_server, monkeypatch
):
    """A tool_calls response invokes the tool node, feeds the result back to
    the LLM, and the second LLM call sees the tool result in its message
    history -- against the real, compiled chat.yaml workflow.

    Marked integration: the tool calls a real, running doc-search MCP
    server over Streamable HTTP (see doc_search_helper.py), so this test
    needs a real subprocess and real Postgres.

    Invoked via graph.ainvoke(), matching the real call chain: the tool is
    async-only (see doc_search_client.make_search_knowledge_base_tool) and
    app.api.agents.chat drives the graph with ainvoke(), not invoke().
    """
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="test-user",
        title="Vacation Policy",
        content="Employees receive 25 days of paid vacation per year.",
    )
    db_session.add(kb)
    db_session.commit()
    embedding = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=generate_embedding(db_session, kb.content).vector,
    )
    db_session.add(embedding)
    db_session.commit()

    tool_call_message = AIMessage(
        content="",
        tool_calls=[
            ToolCall(name="search_knowledge_base", args={"query": "vacation days"}, id="call-1")
        ],
    )
    final_message = AIMessage(content="You get 25 days of paid vacation per year.")
    fake_llm = FakeChatModel(responses=[tool_call_message, final_message])
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: fake_llm)

    token = make_signed_token("test-user", FAKE_KEYCLOAK_PRIVATE_KEY)
    with running_doc_search_subprocess(
        test_db_url, fake_keycloak_jwks_server, _CHAT_WORKFLOW_TEST_PORT
    ) as mcp_url:
        graph = _compile_chat_workflow(db_session, token=token, mcp_url=mcp_url)
        thread_id = _new_thread(db_session)

        result = await graph.ainvoke(
            _initial_state("How many vacation days do I get?", thread_id),
            config={"configurable": {"thread_id": thread_id}},
        )

    assert fake_llm.call_count == 2
    messages = result["messages"]
    tool_messages = [m for m in messages if type(m).__name__ == "ToolMessage"]
    assert len(tool_messages) == 1
    assert "Vacation Policy" in tool_messages[0].content
    assert messages[-1].content == "You get 25 days of paid vacation per year."


@pytest.mark.integration
async def test_chat_workflow_stops_after_max_tool_iterations(
    db_session, test_db_url, fake_keycloak_jwks_server, monkeypatch
):
    """A model that keeps requesting tool calls is forced to END after a
    bounded number of rounds, rather than looping forever.

    Marked integration: a looping tool call is actually executed by the
    graph's ToolNode, which calls a real, running doc-search MCP server
    over Streamable HTTP (real Postgres + real subprocess).
    """
    looping_tool_call = AIMessage(
        content="",
        tool_calls=[
            ToolCall(name="search_knowledge_base", args={"query": "anything"}, id="call-loop")
        ],
    )
    fake_llm = FakeChatModel(responses=[looping_tool_call])
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: fake_llm)

    token = make_signed_token("test-user", FAKE_KEYCLOAK_PRIVATE_KEY)
    with running_doc_search_subprocess(
        test_db_url, fake_keycloak_jwks_server, _CHAT_WORKFLOW_TEST_PORT + 1
    ) as mcp_url:
        graph = _compile_chat_workflow(db_session, token=token, mcp_url=mcp_url)
        thread_id = _new_thread(db_session)

        result = await graph.ainvoke(
            _initial_state("Loop forever?", thread_id),
            config={"configurable": {"thread_id": thread_id}},
        )

    assert result is not None
    assert fake_llm.call_count <= 6
