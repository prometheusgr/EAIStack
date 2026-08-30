"""Tests for the backend's MCP client wrapper around the doc-search server.

Unit-marked tests here cover error handling with the doc-search server
unreachable (no real network call succeeds, no live server needed).
Integration-marked tests (tests/integration/test_mcp_client.py) run a real
doc-search server and assert the same title/excerpt/user-scoping behavior
backend/tests/unit/test_tools.py asserted before the extraction — this is a
structural move, not a behavior change.
"""

import pytest

from app.mcp_client import Source, make_search_knowledge_base_tool
from app.mcp_client.doc_search_client import _extract_sources


@pytest.mark.unit
async def test_search_knowledge_base_tool_reports_clear_error_when_server_unreachable():
    """A connection failure surfaces as a clear string result, not a raised
    exception that would crash the agent's tool-call round-trip — the LLM
    still needs a ToolMessage to continue the conversation.

    The tool is async-only (see make_search_knowledge_base_tool's
    docstring): it's invoked via ainvoke(), matching how LangGraph's
    ToolNode calls it in the real, fully-async call chain from
    app.api.agents.chat down through create_chat_agent.
    """
    tool = make_search_knowledge_base_tool(token="some.jwt.token", mcp_url="http://localhost:1/mcp")

    result = await tool.ainvoke({"query": "anything"})

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


class _FakeCallToolResult:
    """Stand-in for mcp.types.CallToolResult, carrying just the
    structuredContent attribute _extract_sources reads.
    """

    def __init__(self, structured_content):
        self.structuredContent = structured_content


@pytest.mark.unit
def test_extract_sources_parses_structured_content_into_source_objects():
    """doc-search's structuredContent.sources list (knowledge_base_id/title/
    heading_path dicts) becomes a list of Source dataclass instances — see
    issue #19.
    """
    result = _FakeCallToolResult(
        {
            "sources": [
                {"knowledge_base_id": "kb-1", "title": "Vacation Policy", "heading_path": None},
                {
                    "knowledge_base_id": "kb-2",
                    "title": "Deployment Guide",
                    "heading_path": "TLS > Certificate rotation",
                },
            ]
        }
    )

    sources = _extract_sources(result)

    assert sources == [
        Source(knowledge_base_id="kb-1", title="Vacation Policy", heading_path=None),
        Source(
            knowledge_base_id="kb-2",
            title="Deployment Guide",
            heading_path="TLS > Certificate rotation",
        ),
    ]


@pytest.mark.unit
def test_extract_sources_returns_empty_list_when_structured_content_missing():
    """A result with no structuredContent at all (an older/misbehaving
    server) degrades to no sources rather than raising.
    """
    result = _FakeCallToolResult(None)

    assert _extract_sources(result) == []


@pytest.mark.unit
def test_extract_sources_skips_malformed_entries_without_raising():
    """A version-skewed doc-search deployment that drops or renames a
    required field on one entry must not crash the whole tool call --
    that malformed entry is skipped, and any well-formed entries alongside
    it still come through. This is a cross-process, independently
    deployable boundary (see _extract_sources's docstring), so a shape
    mismatch here must degrade, not raise.
    """
    result = _FakeCallToolResult(
        {
            "sources": [
                {"title": "Missing ID"},  # no knowledge_base_id
                {"knowledge_base_id": "kb-2"},  # no title
                {"knowledge_base_id": "kb-3", "title": "Well-Formed Entry", "heading_path": None},
            ]
        }
    )

    sources = _extract_sources(result)

    assert sources == [
        Source(knowledge_base_id="kb-3", title="Well-Formed Entry", heading_path=None)
    ]


@pytest.mark.unit
async def test_search_knowledge_base_tool_returns_empty_sources_when_server_unreachable():
    """The unreachable-server fallback (see the error-handling test above)
    must still satisfy response_format="content_and_artifact"'s two-tuple
    contract: empty sources, not a crash building the ToolMessage.

    Invoked via a ToolCall dict (not a bare {"query": ...} args dict), the
    same shape LangGraph's ToolNode actually uses: only a call carrying a
    tool_call_id causes LangChain to construct a real ToolMessage and
    populate .artifact (see langchain_core.tools.base._format_output --
    tool_call_id=None returns the bare content string, skipping artifact
    construction entirely, which would make this test unable to catch a
    broken two-tuple return even if the fallback stopped returning one).
    """
    tool = make_search_knowledge_base_tool(token="some.jwt.token", mcp_url="http://localhost:1/mcp")

    tool_message = await tool.ainvoke(
        {
            "name": "search_knowledge_base",
            "args": {"query": "anything"},
            "id": "call-1",
            "type": "tool_call",
        }
    )

    assert isinstance(tool_message.content, str)
    assert "unavailable" in tool_message.content.lower()
    assert tool_message.artifact == []
