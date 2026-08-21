"""Tests for the chat agent."""

from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolCall

from app.agents.chat_agent import create_chat_agent
from app.core.llm_client import FakeChatModel
from app.db.models import Embedding, KnowledgeBase
from app.repositories import ThreadRepository
from app.services import generate_embedding


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


@pytest.mark.unit
def test_create_chat_agent_returns_runnable(db_session):
    """create_chat_agent() should return a compiled, runnable graph."""
    graph = create_chat_agent(db=db_session, user_id="test-user")
    assert graph is not None
    assert hasattr(graph, "invoke")


@pytest.mark.unit
def test_chat_agent_invoke_with_message(db_session, monkeypatch):
    """Agent should accept a user message and return a response, with no tool calls."""
    monkeypatch.setattr(
        "app.agents.chat_agent.get_llm_client",
        lambda db: FakeChatModel(response="4"),
    )
    graph = create_chat_agent(db=db_session, user_id="test-user")
    thread_id = _new_thread(db_session)

    state = {
        "messages": [HumanMessage(content="What is 2+2?")],
        "thread_id": thread_id,
        "user_id": "test-user",
    }

    result = graph.invoke(state, config={"configurable": {"thread_id": thread_id}})

    final_message = result["messages"][-1]
    assert isinstance(final_message, AIMessage)
    assert final_message.content == "4"
    assert result["thread_id"] == thread_id


@pytest.mark.unit
def test_conversation_persists_across_two_invokes_same_thread_same_user(db_session, monkeypatch):
    """A second invoke on the same thread_id sees the first turn's messages."""
    fake_llm = FakeChatModel(responses=[AIMessage(content="4"), AIMessage(content="Yes, 2+2=4.")])
    monkeypatch.setattr("app.agents.chat_agent.get_llm_client", lambda db: fake_llm)
    thread_id = _new_thread(db_session)
    config = {"configurable": {"thread_id": thread_id}}

    first_graph = create_chat_agent(db=db_session, user_id="test-user")
    first_graph.invoke(
        {
            "messages": [HumanMessage(content="What is 2+2?")],
            "thread_id": thread_id,
            "user_id": "test-user",
        },
        config=config,
    )
    db_session.commit()

    second_graph = create_chat_agent(db=db_session, user_id="test-user")
    result = second_graph.invoke(
        {
            "messages": [HumanMessage(content="Are you sure?")],
            "thread_id": thread_id,
            "user_id": "test-user",
        },
        config=config,
    )

    contents = [m.content for m in result["messages"]]
    assert "What is 2+2?" in contents
    assert "4" in contents
    assert "Are you sure?" in contents
    assert contents[-1] == "Yes, 2+2=4."


@pytest.mark.unit
def test_chat_agent_invoke_passes_through_thread_id(db_session, monkeypatch):
    """Agent should pass through the thread_id unchanged."""
    monkeypatch.setattr(
        "app.agents.chat_agent.get_llm_client",
        lambda db: FakeChatModel(),
    )
    graph = create_chat_agent(db=db_session, user_id="test-user")
    thread_id = _new_thread(db_session)

    state = {
        "messages": [HumanMessage(content="Hello")],
        "thread_id": thread_id,
        "user_id": "test-user",
    }

    result = graph.invoke(state, config={"configurable": {"thread_id": thread_id}})

    assert result["thread_id"] == thread_id


@pytest.mark.unit
def test_chat_agent_plain_response_skips_tool_node(db_session, monkeypatch):
    """A response with no tool_calls routes straight to END without invoking the tool."""
    fake_llm = FakeChatModel(response="No tool needed here.")
    monkeypatch.setattr("app.agents.chat_agent.get_llm_client", lambda db: fake_llm)
    graph = create_chat_agent(db=db_session, user_id="test-user")
    thread_id = _new_thread(db_session)

    state = {
        "messages": [HumanMessage(content="Hello")],
        "thread_id": thread_id,
        "user_id": "test-user",
    }

    result = graph.invoke(state, config={"configurable": {"thread_id": thread_id}})

    assert fake_llm.call_count == 1
    messages = result["messages"]
    assert isinstance(messages[-1], AIMessage)
    assert messages[-1].content == "No tool needed here."


@pytest.mark.integration
def test_chat_agent_tool_call_routes_to_tool_and_grounds_final_answer(db_session, monkeypatch):
    """A tool_calls response invokes the tool node, feeds the result back to the LLM,
    and the second LLM call sees the tool result in its message history.
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
    monkeypatch.setattr("app.agents.chat_agent.get_llm_client", lambda db: fake_llm)

    graph = create_chat_agent(db=db_session, user_id="test-user")
    thread_id = _new_thread(db_session)
    state = {
        "messages": [HumanMessage(content="How many vacation days do I get?")],
        "thread_id": thread_id,
        "user_id": "test-user",
    }

    result = graph.invoke(state, config={"configurable": {"thread_id": thread_id}})

    assert fake_llm.call_count == 2
    messages = result["messages"]
    tool_messages = [m for m in messages if type(m).__name__ == "ToolMessage"]
    assert len(tool_messages) == 1
    assert "Vacation Policy" in tool_messages[0].content
    assert messages[-1].content == "You get 25 days of paid vacation per year."


@pytest.mark.integration
def test_chat_agent_stops_after_max_tool_iterations(db_session, monkeypatch):
    """A model that keeps requesting tool calls is forced to END after a bounded
    number of rounds, rather than looping forever.

    Marked integration: a looping tool call is actually executed by the graph's
    ToolNode, which runs search_knowledge_base against pgvector's cosine
    distance operator (real Postgres only, see test_embedding_repository.py).
    """
    looping_tool_call = AIMessage(
        content="",
        tool_calls=[
            ToolCall(name="search_knowledge_base", args={"query": "anything"}, id="call-loop")
        ],
    )
    fake_llm = FakeChatModel(responses=[looping_tool_call])
    monkeypatch.setattr("app.agents.chat_agent.get_llm_client", lambda db: fake_llm)

    graph = create_chat_agent(db=db_session, user_id="test-user")
    thread_id = _new_thread(db_session)
    state = {
        "messages": [HumanMessage(content="Loop forever?")],
        "thread_id": thread_id,
        "user_id": "test-user",
    }

    result = graph.invoke(state, config={"configurable": {"thread_id": thread_id}})

    assert result is not None
    assert fake_llm.call_count <= 6
