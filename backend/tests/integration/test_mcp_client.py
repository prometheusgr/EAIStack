"""Integration tests for the backend's MCP client against a real,
running doc-search server (its own subprocess, own venv, same Postgres).

Proves the same behavior contract backend/tests/unit/test_tools.py asserted
before search_knowledge_base was extracted into its own MCP server: same
title/excerpt formatting, same "no matches" message, same per-user scoping —
now exercised over a real network hop with real token verification, instead
of a Python closure.

doc-search runs as a genuine subprocess in its own venv (not imported into
the backend's process) — this mirrors the production topology (separate
pods, separate dependency sets) rather than blurring the boundary Phase 3 is
otherwise establishing between the two services. Requires
mcp-servers/doc-search's venv to already be set up (see its README.md),
the same prerequisite backend/integration tests already have for the
backend's own venv.
"""

import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import pytest

from app.mcp_client import make_search_knowledge_base_tool

TEST_PORT = 8198
DOC_SEARCH_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "doc-search"
DOC_SEARCH_PYTHON = DOC_SEARCH_DIR / (
    "venv/Scripts/python.exe" if sys.platform == "win32" else "venv/bin/python"
)


def _make_signed_token(user_id: str) -> str:
    """Sign a token with fake_keycloak_jwks_server's fixed test keypair, so
    the doc-search subprocess (pointed at that fixture's JWKS URL) can
    verify it against a real, network-reachable JWKS endpoint.
    """
    from tests.conftest import FAKE_KEYCLOAK_PRIVATE_KEY

    return jwt.encode(
        {
            "sub": user_id,
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        FAKE_KEYCLOAK_PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": "backend-integration-test-key"},
    )


@contextmanager
def _running_doc_search_subprocess(database_url: str, keycloak_jwks_url: str):
    """Start doc-search as a real subprocess pointed at the given Postgres
    and a JWKS URL the test controls (a throwaway local HTTP server serving
    a fixed keypair's JWKS — see conftest.fake_keycloak_jwks_server).
    """
    if not DOC_SEARCH_PYTHON.exists():
        pytest.skip(
            f"doc-search venv not found at {DOC_SEARCH_PYTHON}; "
            "run `pip install -e '.[dev]'` in mcp-servers/doc-search first"
        )

    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "KEYCLOAK_URL": keycloak_jwks_url,
        "KEYCLOAK_REALM": "eaistack",
        "PORT": str(TEST_PORT),
    }
    process = subprocess.Popen(
        [
            str(DOC_SEARCH_PYTHON),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(TEST_PORT),
            "--log-level",
            "warning",
        ],
        cwd=str(DOC_SEARCH_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 15
        mcp_url = f"http://127.0.0.1:{TEST_PORT}/mcp"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read().decode(errors="replace") if process.stdout else ""
                raise RuntimeError(f"doc-search subprocess exited early:\n{output}")
            try:
                httpx.get(f"http://127.0.0.1:{TEST_PORT}/", timeout=0.5)
                break
            except httpx.TransportError:
                time.sleep(0.2)
        else:
            output = process.stdout.read().decode(errors="replace") if process.stdout else ""
            raise RuntimeError(f"doc-search subprocess never became reachable:\n{output}")
        yield mcp_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


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
def test_search_knowledge_base_tool_returns_matching_document_over_real_mcp(
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
    token = _make_signed_token("user-a")

    with _running_doc_search_subprocess(test_db_url, fake_keycloak_jwks_server) as mcp_url:
        tool = make_search_knowledge_base_tool(token=token, mcp_url=mcp_url)
        result = tool.invoke({"query": "vacation days"})

    assert "Vacation Policy" in result
    assert "25 days of paid vacation" in result


@pytest.mark.integration
def test_search_knowledge_base_tool_is_scoped_to_the_forwarded_token(
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
    token = _make_signed_token("user-a")

    with _running_doc_search_subprocess(test_db_url, fake_keycloak_jwks_server) as mcp_url:
        tool = make_search_knowledge_base_tool(token=token, mcp_url=mcp_url)
        result = tool.invoke({"query": "confidential"})

    assert "User B Confidential Doc" not in result
    assert "belongs only to user B" not in result


@pytest.mark.integration
def test_search_knowledge_base_tool_returns_empty_message_when_no_documents(
    db_session, test_db_url, fake_keycloak_jwks_server
):
    """A clear, non-crashing message is returned for a user with no documents."""
    token = _make_signed_token("user-with-no-docs")

    with _running_doc_search_subprocess(test_db_url, fake_keycloak_jwks_server) as mcp_url:
        tool = make_search_knowledge_base_tool(token=token, mcp_url=mcp_url)
        result = tool.invoke({"query": "anything"})

    assert isinstance(result, str)
    assert len(result) > 0
    assert "Vacation Policy" not in result
