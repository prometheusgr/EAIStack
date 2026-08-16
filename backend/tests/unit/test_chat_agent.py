"""Tests for the chat agent."""

import pytest

from app.agents.chat_agent import create_chat_agent


@pytest.mark.unit
def test_create_chat_agent_returns_runnable():
    """create_chat_agent() should return a compiled, runnable graph."""
    graph = create_chat_agent()
    assert graph is not None
    assert hasattr(graph, "invoke")


@pytest.mark.unit
def test_chat_agent_invoke_with_message(mock_llm):
    """Agent should accept a user message and return a response."""
    graph = create_chat_agent()

    state = {
        "user_message": "What is 2+2?",
        "thread_id": "test-thread-123",
        "tool_result": None,
        "response": None,
    }

    result = graph.invoke(state)

    assert result["response"] is not None
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0
    assert result["thread_id"] == "test-thread-123"


@pytest.mark.unit
def test_chat_agent_invoke_passes_through_thread_id(mock_llm):
    """Agent should pass through the thread_id unchanged."""
    graph = create_chat_agent()

    thread_id = "my-conversation-456"
    state = {
        "user_message": "Hello",
        "thread_id": thread_id,
        "tool_result": None,
        "response": None,
    }

    result = graph.invoke(state)

    assert result["thread_id"] == thread_id


@pytest.mark.unit
def test_chat_agent_includes_tool_call_node(mock_llm):
    """Agent graph should include a tool-calling node."""
    graph = create_chat_agent()

    state = {
        "user_message": "What is the current time?",
        "thread_id": "test-123",
        "tool_result": None,
        "response": None,
    }

    result = graph.invoke(state)

    # Should have a tool_result from the mocked tool
    assert result["tool_result"] is not None
    assert isinstance(result["tool_result"], str)

    # And a final response
    assert result["response"] is not None
