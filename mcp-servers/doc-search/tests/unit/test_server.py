"""End-to-end tests for the doc-search MCP server over real Streamable HTTP.

Marked integration: exercises a real running server (uvicorn, in a background
thread) and real Postgres via db_session's testcontainer, mirroring the same
"integration" constraint as test_search.py.

These are the critical isolation tests for the whole Phase 3 design: a
request must carry a Keycloak access token (never a bare user_id), the
server verifies it independently, and cross-user document access never
happens even when two users' tokens are both valid.
"""

import threading
import time
from contextlib import contextmanager

import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import to_base64url_uint
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.models import Embedding, KnowledgeBase
from app.search import generate_query_embedding

TEST_PORT = 8199


def _make_signed_token(claims: dict, kid: str = "test-key") -> tuple[str, dict]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
    public_numbers = public_key.public_numbers()
    jwks = {
        "keys": [
            {
                "kid": kid,
                "kty": "RSA",
                "use": "sig",
                "n": to_base64url_uint(public_numbers.n).decode("utf-8"),
                "e": to_base64url_uint(public_numbers.e).decode("utf-8"),
            }
        ]
    }
    return token, jwks


def _valid_token_for(user_id: str) -> str:
    token, _jwks = _make_signed_token(
        {
            "sub": user_id,
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )
    return token


@contextmanager
def _running_server(monkeypatch_jwks, db_url: str):
    """Run the real doc-search Streamable HTTP app in a background thread."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.db as app_db
    from app.server import build_app

    engine = create_engine(db_url)
    app_db.engine = engine
    app_db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    asgi_app = build_app()
    config = uvicorn.Config(asgi_app, host="127.0.0.1", port=TEST_PORT, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        yield f"http://127.0.0.1:{TEST_PORT}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def jwks_mock(monkeypatch):
    """Patch app.auth.get_keycloak_jwks to return the JWKS for our test keys.

    Each call to _make_signed_token generates a fresh keypair, so the mock is
    set to return whatever JWKS the test most recently generated via a mutable
    holder the test can update.
    """
    holder: dict = {"jwks": {"keys": []}}

    async def _fake_get_jwks():
        return holder["jwks"]

    monkeypatch.setattr("app.auth.get_keycloak_jwks", _fake_get_jwks)
    return holder


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_via_real_http_with_valid_token_returns_matches(
    db_session, test_db_url, jwks_mock
):
    """A valid token's user sees their own seeded document via a real MCP
    tool call over Streamable HTTP.
    """
    kb = KnowledgeBase(
        id="kb-1", user_id="user-a", title="Vacation Policy", content="25 days of paid vacation."
    )
    db_session.add(kb)
    db_session.commit()
    db_session.add(
        Embedding(
            id="emb-1", doc_id=kb.id, embedding=generate_query_embedding(db_session, kb.content)
        )
    )
    db_session.commit()

    token, jwks = _make_signed_token(
        {
            "sub": "user-a",
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )
    jwks_mock["jwks"] = jwks

    with _running_server(jwks_mock, test_db_url) as url:
        async with streamablehttp_client(url, headers={"Authorization": f"Bearer {token}"}) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "search_knowledge_base", {"query": "vacation days"}
                )

        text = result.content[0].text
        assert "Vacation Policy" in text
        assert "25 days of paid vacation" in text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_via_real_http_rejects_missing_token(db_session, test_db_url, jwks_mock):
    """A request with no Authorization header is rejected before any tool runs."""
    with _running_server(jwks_mock, test_db_url) as url:
        with pytest.raises(Exception):
            async with streamablehttp_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.call_tool("search_knowledge_base", {"query": "anything"})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_via_real_http_rejects_expired_token(db_session, test_db_url, jwks_mock):
    """An expired token is rejected, not silently treated as anonymous."""
    token, jwks = _make_signed_token(
        {
            "sub": "user-a",
            "aud": "eaistack-web",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        }
    )
    jwks_mock["jwks"] = jwks

    with _running_server(jwks_mock, test_db_url) as url:
        with pytest.raises(Exception):
            async with streamablehttp_client(url, headers={"Authorization": f"Bearer {token}"}) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await session.call_tool("search_knowledge_base", {"query": "anything"})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_via_real_http_never_crosses_user_boundary(db_session, test_db_url, jwks_mock):
    """User B's valid token must never surface User A's documents, even
    though both tokens are independently valid and verified.
    """
    kb_a = KnowledgeBase(
        id="kb-a", user_id="user-a", title="User A Secret", content="Only user A should see this."
    )
    db_session.add(kb_a)
    db_session.commit()
    db_session.add(
        Embedding(
            id="emb-a", doc_id=kb_a.id, embedding=generate_query_embedding(db_session, kb_a.content)
        )
    )
    db_session.commit()

    token_b, jwks = _make_signed_token(
        {
            "sub": "user-b",
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )
    jwks_mock["jwks"] = jwks

    with _running_server(jwks_mock, test_db_url) as url:
        async with streamablehttp_client(url, headers={"Authorization": f"Bearer {token_b}"}) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("search_knowledge_base", {"query": "secret"})

        text = result.content[0].text
        assert "User A Secret" not in text
        assert "Only user A should see this" not in text
