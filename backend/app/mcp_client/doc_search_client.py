"""Backend-side MCP client for the doc-search server.

Replaces the in-process search_knowledge_base tool (formerly
app.agents.tools.make_search_knowledge_base_tool) with a call over
Streamable HTTP to the standalone doc-search MCP server (mcp-servers/
doc-search), so the same search logic can run as its own K8s pod.

Isolation: the caller's own Keycloak access token is forwarded as a Bearer
header on every call — never a bare user_id — so doc-search can
independently verify it against Keycloak's JWKS rather than trusting an
identity claim handed to it by this service. Never log the token: every
hop that carries it is a place a stolen credential becomes usable, and
logging is the easiest way to accidentally widen that further.
"""

import logging
from datetime import timedelta

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MCP_CALL_TIMEOUT = timedelta(seconds=30)


class _SearchKnowledgeBaseInput(BaseModel):
    """Arguments the model may supply when calling search_knowledge_base.

    Identical to the pre-extraction schema (app.agents.tools) so
    chat_agent.py's routing and existing tool-call behavior are unaffected
    by where the tool's logic actually runs.
    """

    query: str = Field(..., description="The search query, in natural language.")
    top_k: int = Field(default=5, description="Maximum number of documents to return.")


async def _open_doc_search_session(token: str, mcp_url: str, query: str, top_k: int):
    """Open the Streamable HTTP connection, do the MCP handshake, and call the
    tool. This is the actual system boundary (network I/O to another
    service) — the only part of a doc-search call that can fail for reasons
    outside this codebase's control, and so the only part whose exceptions
    should be caught and turned into the agent's "unavailable" fallback.
    """
    async with streamablehttp_client(mcp_url, headers={"Authorization": f"Bearer {token}"}) as (
        read,
        write,
        _get_session_id,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(
                "search_knowledge_base",
                {"query": query, "top_k": top_k},
                read_timeout_seconds=MCP_CALL_TIMEOUT,
            )


def _render_search_result(result) -> str:
    """Extract the text content doc-search returned.

    Deliberately outside the network try/except: a bug here (e.g. an
    unexpected content block shape) is a parsing defect in this codebase,
    not a network failure, and per AGENTS.md's "error handling only at
    system boundaries" should raise and surface distinguishably rather than
    being reported to the model as an identical-looking "server
    unavailable" fallback.
    """
    return "".join(block.text for block in result.content if hasattr(block, "text"))


def make_search_knowledge_base_tool(token: str, mcp_url: str) -> StructuredTool:
    """Build a search_knowledge_base tool bound to one user's forwarded token.

    token and mcp_url are closed over rather than exposed as model-supplied
    arguments, for the same reason the pre-extraction tool closed over
    user_id and db: letting the model choose its own credentials or target
    server would be a session-isolation hole.

    Declared as an async-only tool (coroutine=, no func=): the whole call
    chain from the FastAPI endpoint down through LangGraph's ToolNode is
    async (see app.agents.chat_agent.create_chat_agent and
    app.api.agents.chat), so the tool can await the MCP client directly.
    There is no sync entry point to fall back to, and none is needed —
    a sync-only caller would be a bug in the caller, not something this
    tool should paper over by bridging event loops itself.
    """

    async def search_knowledge_base(query: str, top_k: int = 5) -> str:
        try:
            result = await _open_doc_search_session(token, mcp_url, query, top_k)
        except Exception:
            logger.exception("doc-search MCP call failed")
            return (
                "The knowledge base search is currently unavailable due to an "
                "internal error. Answer using only what you already know, and "
                "let the user know document search wasn't available."
            )
        return _render_search_result(result)

    return StructuredTool.from_function(
        coroutine=search_knowledge_base,
        name="search_knowledge_base",
        description=(
            "Search the user's personal knowledge base for documents relevant to a "
            "query. Use this whenever answering the question requires specific facts, "
            "policies, or content that may have been uploaded by the user rather than "
            "general knowledge. Returns the title and a content excerpt for each "
            "matching document, or a message saying nothing matched."
        ),
        args_schema=_SearchKnowledgeBaseInput,
    )
