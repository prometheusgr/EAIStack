"""Tests for the backend's MCP client wrapper around the doc-search server.

Unit-marked tests here cover error handling with the doc-search server
unreachable (no real network call succeeds, no live server needed).
Integration-marked tests (tests/integration/test_mcp_client.py) run a real
doc-search server and assert the same title/excerpt/user-scoping behavior
backend/tests/unit/test_tools.py asserted before the extraction — this is a
structural move, not a behavior change.
"""

import pytest

from app.mcp_client import make_search_knowledge_base_tool


@pytest.mark.unit
def test_search_knowledge_base_tool_reports_clear_error_when_server_unreachable():
    """A connection failure surfaces as a clear string result, not a raised
    exception that would crash the agent's tool-call round-trip — the LLM
    still needs a ToolMessage to continue the conversation.
    """
    tool = make_search_knowledge_base_tool(
        token="some.jwt.token", mcp_url="http://localhost:1/mcp"
    )

    result = tool.invoke({"query": "anything"})

    assert isinstance(result, str)
    assert "error" in result.lower() or "unavailable" in result.lower()


@pytest.mark.unit
def test_search_knowledge_base_tool_has_same_name_and_schema_as_before():
    """The tool's public contract (name, args) must be unchanged so
    chat_agent.py's routing and existing tool-call tests keep working.
    """
    tool = make_search_knowledge_base_tool(token="some.jwt.token", mcp_url="http://localhost:1/mcp")

    assert tool.name == "search_knowledge_base"
    schema_fields = tool.args_schema.model_fields
    assert "query" in schema_fields
    assert "top_k" in schema_fields
