"""Integration tests for the backend's MCP client against a real,
running doc-search server (its own subprocess, own venv, same Postgres).

Proves the same behavior contract backend/tests/unit/test_tools.py asserted
before search_knowledge_base was extracted into its own MCP server: same
title/excerpt formatting, same "no matches" message, same per-user scoping —
now exercised over a real network hop with real token verification, instead
of a Python closure.

See doc_search_helper.py for why doc-search runs as a genuine subprocess
rather than being imported into the backend's own process.

The tool is async-only (see make_search_knowledge_base_tool's docstring), so
these tests await ainvoke() — the same entry point LangGraph's ToolNode uses
in the real, fully-async chain from app.api.agents.chat downward. There is no
sync entry point to test.
"""

from uuid import uuid4

import pytest

from app.mcp_client import make_search_knowledge_base_tool
from tests.conftest import FAKE_KEYCLOAK_PRIVATE_KEY
from tests.integration.doc_search_helper import (
    make_signed_token,
    running_doc_search_subprocess,
)

TEST_PORT = 8198


def _seed_document(db_session, user_id: str, title: str, content: str) -> None:
    from app.db.models import Embedding, KnowledgeBase
    from app.services import generate_embedding

    kb = KnowledgeBase(id=str(uuid4()), user_id=user_id, title=title, content=content)
    db_session.add(kb)
    db_session.commit()

    embedding = Embedding(
        id=str(uuid4()), doc_id=kb.id, embedding=generate_embedding(db_session, content).vector
    )
    db_session.add(embedding)
    db_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_knowledge_base_tool_returns_matching_document_over_real_mcp(
    db_session, test_db_url, fake_keycloak_jwks_server
):
    """Same behavior as the old in-process tool: a matching query returns
    the document's title and content excerpt, now over a real subprocess.
    """
    _seed_document(
        db_session,
        user_id="user-a",
        title="Vacation Policy",
        content="Employees receive 25 days of paid vacation per year.",
    )
    token = make_signed_token("user-a", FAKE_KEYCLOAK_PRIVATE_KEY)

    with running_doc_search_subprocess(
        test_db_url, fake_keycloak_jwks_server, TEST_PORT
    ) as mcp_url:
        tool = make_search_knowledge_base_tool(token=token, mcp_url=mcp_url)
        result = await tool.ainvoke({"query": "vacation days"})

    assert "Vacation Policy" in result
    assert "25 days of paid vacation" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_knowledge_base_tool_is_scoped_to_the_forwarded_token(
    db_session, test_db_url, fake_keycloak_jwks_server
):
    """The tool only ever returns documents owned by the user whose token was
    forwarded — never documents seeded under a different user_id, even
    though this now happens over a real network hop rather than a closure.
    """
    _seed_document(
        db_session,
        user_id="user-b",
        title="User B Confidential Doc",
        content="This document belongs only to user B.",
    )
    token = make_signed_token("user-a", FAKE_KEYCLOAK_PRIVATE_KEY)

    with running_doc_search_subprocess(
        test_db_url, fake_keycloak_jwks_server, TEST_PORT
    ) as mcp_url:
        tool = make_search_knowledge_base_tool(token=token, mcp_url=mcp_url)
        result = await tool.ainvoke({"query": "confidential"})

    assert "User B Confidential Doc" not in result
    assert "belongs only to user B" not in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_knowledge_base_tool_returns_empty_message_when_no_documents(
    db_session, test_db_url, fake_keycloak_jwks_server
):
    """A clear, non-crashing message is returned for a user with no documents."""
    token = make_signed_token("user-with-no-docs", FAKE_KEYCLOAK_PRIVATE_KEY)

    with running_doc_search_subprocess(
        test_db_url, fake_keycloak_jwks_server, TEST_PORT
    ) as mcp_url:
        tool = make_search_knowledge_base_tool(token=token, mcp_url=mcp_url)
        result = await tool.ainvoke({"query": "anything"})

    assert isinstance(result, str)
    assert len(result) > 0
    assert "Vacation Policy" not in result
