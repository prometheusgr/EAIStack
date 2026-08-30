"""Tests for the agents API endpoint."""

import uuid
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolCall

from app.core.auth import get_current_user
from app.core.llm_client import FakeChatModel
from app.main import app


@pytest.mark.unit
def test_chat_endpoint_no_auth_returns_403(client):
    """POST /api/agents/chat without auth should return 403."""
    response = client.post("/api/agents/chat", json={"message": "Hello"})
    assert response.status_code == 403


@pytest.mark.unit
def test_chat_endpoint_malformed_auth_header_returns_403(client):
    """POST /api/agents/chat with malformed auth header should return 403."""
    response = client.post(
        "/api/agents/chat",
        json={"message": "Hello"},
        headers={"Authorization": "NotBearer token"},
    )
    # HTTPBearer expects "Bearer <token>" format; malformed header is not a bearer token
    assert response.status_code == 403


@pytest.mark.unit
def test_chat_endpoint_authenticated_returns_200(client):
    """POST /api/agents/chat with valid auth should return 200."""
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
        "access_token": "fake-access-token",
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post("/api/agents/chat", json={"message": "What is 2+2?"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 0


@pytest.mark.unit
def test_chat_endpoint_returns_thread_id(client):
    """POST /api/agents/chat should return thread_id."""
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
        "access_token": "fake-access-token",
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post("/api/agents/chat", json={"message": "Hello"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "thread_id" in data
    assert isinstance(data["thread_id"], str)
    assert len(data["thread_id"]) > 0


@pytest.mark.unit
def test_chat_endpoint_generates_thread_id_if_absent(client):
    """POST /api/agents/chat should generate thread_id if not provided."""
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
        "access_token": "fake-access-token",
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post("/api/agents/chat", json={"message": "Hello"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    # Should be a valid UUID string
    try:
        uuid.UUID(data["thread_id"])
    except ValueError:
        pytest.fail(f"thread_id is not a valid UUID: {data['thread_id']}")


@pytest.mark.unit
def test_chat_endpoint_preserves_thread_id_when_caller_owns_it(client):
    """POST /api/agents/chat should preserve a thread_id the caller already owns.

    An arbitrary, never-before-seen thread_id is NOT preserved: it isn't
    trusted, since a client can never legitimately hold a thread_id it
    wasn't issued by a prior response to this same endpoint (see
    test_chat_endpoint_rejects_thread_id_owned_by_different_user). This
    replaces the old behavior of echoing back any client-supplied string
    verbatim, which was the ownership gap this phase closes.
    """
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
        "access_token": "fake-access-token",
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    first_response = client.post("/api/agents/chat", json={"message": "Hello"})
    owned_thread_id = first_response.json()["thread_id"]

    second_response = client.post(
        "/api/agents/chat", json={"message": "Again", "thread_id": owned_thread_id}
    )

    app.dependency_overrides.clear()

    assert second_response.status_code == 200
    assert second_response.json()["thread_id"] == owned_thread_id


@pytest.mark.unit
def test_chat_endpoint_mints_new_thread_id_for_unrecognized_thread_id(client):
    """POST /api/agents/chat should mint a fresh thread_id for one it doesn't recognize,
    rather than trusting an arbitrary client-supplied string.
    """
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
        "access_token": "fake-access-token",
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    thread_id = "my-custom-thread-456"
    response = client.post("/api/agents/chat", json={"message": "Hello", "thread_id": thread_id})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] != thread_id


@pytest.mark.unit
def test_chat_endpoint_rejects_thread_id_owned_by_different_user(client):
    """POST /api/agents/chat must not resume or reveal another user's thread
    when supplied their thread_id.
    """
    user_a = {
        "user_id": "user-a",
        "username": "usera",
        "email": "usera@example.com",
        "name": "User A",
        "token": {},
        "access_token": "fake-access-token",
    }
    user_b = {
        "user_id": "user-b",
        "username": "userb",
        "email": "userb@example.com",
        "name": "User B",
        "token": {},
        "access_token": "fake-access-token",
    }

    def as_user_a():
        return user_a

    app.dependency_overrides[get_current_user] = as_user_a
    user_a_response = client.post(
        "/api/agents/chat", json={"message": "This is user A's secret question."}
    )
    user_a_thread_id = user_a_response.json()["thread_id"]

    def as_user_b():
        return user_b

    app.dependency_overrides[get_current_user] = as_user_b
    user_b_response = client.post(
        "/api/agents/chat",
        json={"message": "Hello from B", "thread_id": user_a_thread_id},
    )
    user_b_thread_id = user_b_response.json()["thread_id"]

    history_response = client.get(f"/api/agents/threads/{user_b_thread_id}")

    app.dependency_overrides.clear()

    assert user_b_thread_id != user_a_thread_id
    assert history_response.status_code == 200
    history_texts = [m["text"] for m in history_response.json()["messages"]]
    assert "This is user A's secret question." not in history_texts


@pytest.mark.unit
def test_chat_endpoint_response_shape(client):
    """POST /api/agents/chat response should match ChatResponse schema."""
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
        "access_token": "fake-access-token",
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post("/api/agents/chat", json={"message": "What is AI?"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()

    # Validate schema
    assert set(data.keys()) == {"response", "thread_id", "sources"}
    assert isinstance(data["response"], str)
    assert isinstance(data["thread_id"], str)
    assert data["sources"] == []


@pytest.mark.unit
def test_chat_endpoint_with_valid_auth(client, mock_keycloak_token):
    """POST /api/agents/chat with valid auth should work end-to-end.

    This test verifies that the chat endpoint correctly:
    1. Accepts a Bearer token in the Authorization header
    2. Validates the token (mocked)
    3. Extracts user info from the token
    4. Returns a valid chat response
    """
    fake_user = {
        "user_id": mock_keycloak_token["sub"],
        "username": mock_keycloak_token["preferred_username"],
        "email": mock_keycloak_token["email"],
        "name": mock_keycloak_token["name"],
        "token": mock_keycloak_token,
        "access_token": "fake-access-token",
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post(
        "/api/agents/chat",
        json={"message": "What is 2+2?"},
        headers={"Authorization": "Bearer valid-jwt-token"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert isinstance(data["response"], str)
    assert "thread_id" in data
    assert isinstance(data["thread_id"], str)


@pytest.mark.unit
def test_chat_endpoint_token_validation_error_returns_401(client):
    """POST /api/agents/chat with invalid token should return 401.

    This test simulates what happens when Keycloak can't validate the token.
    For real deployments, this means the token is malformed, expired, or
    signed by a different Keycloak instance.
    """
    from fastapi import HTTPException

    def override_get_current_user():
        raise HTTPException(status_code=401, detail="Invalid token")

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post(
        "/api/agents/chat",
        json={"message": "What is 2+2?"},
        headers={"Authorization": "Bearer invalid-token"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 401


@pytest.mark.unit
def test_chat_endpoint_tool_call_does_not_hit_nested_asyncio_run_under_real_event_loop(
    client, monkeypatch, caplog
):
    """A tool-calling turn must not crash when the endpoint is exercised the
    way it actually runs in production: on FastAPI's live event loop, not
    from a synchronous pytest function.

    Regression test for a bug where search_knowledge_base's implementation
    called asyncio.run() to bridge into the async MCP client. asyncio.run()
    raises RuntimeError when it's already inside a running loop -- which
    every real request is, since async def chat() runs on the ASGI event
    loop. tests/unit/test_chat_agent.py and the rest of this file call
    graph.invoke()/client.post() from plain sync test functions, which have
    no event loop running and so never trigger this failure mode; using
    httpx.AsyncClient against the ASGI app (rather than starlette's
    TestClient) is what puts a real loop underneath the request, matching
    production.

    The doc-search server at doc_search_mcp_url isn't actually running in
    this test, so the tool call is expected to fail and fall back to its
    "currently unavailable" string either way -- that fallback string alone
    can't distinguish a real network failure from the asyncio.run() bug, so
    this test inspects the logged exception's type instead. Before the fix:
    doc_search_client logs the swallowed exception as RuntimeError(
    "asyncio.run() cannot be called from a running event loop"), not the
    connection error a reader would expect. After the fix: the tool awaits
    the MCP client directly (no asyncio.run()), so the logged exception is
    the real connection failure, never a RuntimeError about a running loop.
    """
    tool_call_message = AIMessage(
        content="",
        tool_calls=[
            ToolCall(name="search_knowledge_base", args={"query": "vacation days"}, id="call-1")
        ],
    )
    final_message = AIMessage(content="Here is what I found.")
    fake_llm = FakeChatModel(responses=[tool_call_message, final_message])
    monkeypatch.setattr("app.agents.chat_agent.get_llm_client", lambda db: fake_llm)

    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
        "access_token": "fake-access-token",
    }
    app.dependency_overrides[get_current_user] = lambda: fake_user

    with caplog.at_level("ERROR", logger="app.mcp_client.doc_search_client"):
        response = client.post(
            "/api/agents/chat", json={"message": "How many vacation days do I get?"}
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_llm.call_count == 2

    doc_search_failures = [
        record
        for record in caplog.records
        if record.name == "app.mcp_client.doc_search_client" and record.exc_info
    ]
    assert len(doc_search_failures) == 1, "expected exactly one logged doc-search call failure"
    exc_type = doc_search_failures[0].exc_info[0]
    assert exc_type is not RuntimeError, (
        "doc-search call failed with RuntimeError, the signature of asyncio.run() being "
        "invoked from an already-running event loop -- the real cause (a connection "
        "failure to the unreachable MCP URL) is being masked"
    )


@pytest.mark.integration
def test_chat_endpoint_returns_sources_grounding_the_answer(
    client, db_session, test_db_url, fake_keycloak_jwks_server, monkeypatch
):
    """POST /api/agents/chat's response includes which knowledge-base
    document(s) grounded the answer, end-to-end through the real doc-search
    MCP server -- the full slice for issue #19.
    """
    from app.core.config import settings
    from app.db.models import Embedding, KnowledgeBase
    from app.services import generate_embedding
    from tests.conftest import FAKE_KEYCLOAK_PRIVATE_KEY
    from tests.integration.doc_search_helper import (
        make_signed_token,
        running_doc_search_subprocess,
    )

    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="test-user-123",
        title="Vacation Policy",
        content="Employees receive 25 days of paid vacation per year.",
    )
    db_session.add(kb)
    db_session.commit()
    db_session.add(
        Embedding(
            id=str(uuid4()),
            doc_id=kb.id,
            embedding=generate_embedding(db_session, kb.content).vector,
        )
    )
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

    token = make_signed_token("test-user-123", FAKE_KEYCLOAK_PRIVATE_KEY)
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
        "access_token": token,
    }
    app.dependency_overrides[get_current_user] = lambda: fake_user

    with running_doc_search_subprocess(test_db_url, fake_keycloak_jwks_server, 8197) as mcp_url:
        monkeypatch.setattr(settings, "doc_search_mcp_url", mcp_url)
        response = client.post(
            "/api/agents/chat", json={"message": "How many vacation days do I get?"}
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["sources"] == [
        {"knowledge_base_id": kb.id, "title": "Vacation Policy", "heading_path": None}
    ]


def _login_as(user_id: str) -> dict:
    """Build a fake user dict and register it as the get_current_user override."""
    fake_user = {
        "user_id": user_id,
        "username": user_id,
        "email": f"{user_id}@example.com",
        "name": user_id,
        "token": {},
        "access_token": "fake-access-token",
    }
    app.dependency_overrides[get_current_user] = lambda: fake_user
    return fake_user


@pytest.mark.unit
def test_get_threads_timestamps_are_serialized_as_utc(client):
    """GET /api/agents/threads must serialize created_at/updated_at with an
    explicit UTC offset, not a bare ISO string.

    ConversationThread's timestamp columns hold naive datetimes (see
    app.db.models.utc_now), which Pydantic serializes as ISO 8601 with no
    offset by default - e.g. "2026-08-21T17:09:00". A JS Date parses a bare
    datetime string as local time, not UTC, so every timestamp the frontend
    renders would be off by the viewer's UTC offset. The 'Z' suffix (or a
    '+00:00' offset) is what tells the client which timezone the string is
    already in.
    """
    _login_as("user-a")
    client.post("/api/agents/chat", json={"message": "Hello"})

    response = client.get("/api/agents/threads")
    app.dependency_overrides.clear()

    thread = response.json()["threads"][0]
    assert thread["created_at"].endswith("Z") or "+" in thread["created_at"][10:]
    assert thread["updated_at"].endswith("Z") or "+" in thread["updated_at"][10:]


@pytest.mark.unit
def test_get_threads_returns_only_callers_threads(client):
    """GET /api/agents/threads should list only the authenticated user's threads."""
    _login_as("user-a")
    thread_response = client.post("/api/agents/chat", json={"message": "Hello"})
    own_thread_id = thread_response.json()["thread_id"]

    _login_as("user-b")
    client.post("/api/agents/chat", json={"message": "Hello from B"})

    _login_as("user-a")
    response = client.get("/api/agents/threads")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    thread_ids = [t["id"] for t in response.json()["threads"]]
    assert thread_ids == [own_thread_id]


@pytest.mark.unit
def test_get_thread_history_returns_404_for_nonexistent_thread(client):
    """GET /api/agents/threads/{thread_id} should 404 for an unknown thread_id."""
    _login_as("user-a")

    response = client.get("/api/agents/threads/does-not-exist")

    app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.unit
def test_get_thread_history_returns_404_for_other_users_thread(client):
    """GET /api/agents/threads/{thread_id} should 404 (not 403) for a thread
    that exists but belongs to another user.
    """
    _login_as("user-a")
    thread_response = client.post("/api/agents/chat", json={"message": "Hello"})
    thread_id = thread_response.json()["thread_id"]

    _login_as("user-b")
    response = client.get(f"/api/agents/threads/{thread_id}")

    app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.unit
def test_get_threads_orders_by_most_recently_active_not_most_recently_created(client):
    """GET /api/agents/threads must reorder a thread to the front after a new
    message, not just after it's first created.

    Regression test: ConversationThread.updated_at has no onupdate trigger
    that a chat turn fires (only ConversationCheckpoint is written on a
    follow-up turn), so without an explicit touch() the older thread would
    incorrectly stay ordered ahead of the one just used.
    """
    _login_as("user-a")
    older_thread_id = client.post("/api/agents/chat", json={"message": "First"}).json()["thread_id"]
    newer_thread_id = client.post("/api/agents/chat", json={"message": "Second"}).json()[
        "thread_id"
    ]
    assert older_thread_id != newer_thread_id

    # Reactivate the older thread with a follow-up message.
    client.post(
        "/api/agents/chat", json={"message": "Back to the first", "thread_id": older_thread_id}
    )

    response = client.get("/api/agents/threads")
    app.dependency_overrides.clear()

    thread_ids = [t["id"] for t in response.json()["threads"]]
    assert thread_ids == [older_thread_id, newer_thread_id]


@pytest.mark.unit
def test_get_thread_history_returns_200_with_messages_for_owned_thread(client):
    """GET /api/agents/threads/{thread_id} should return the thread's messages
    for its owner.
    """
    _login_as("user-a")
    chat_response = client.post("/api/agents/chat", json={"message": "What is 2+2?"})
    thread_id = chat_response.json()["thread_id"]
    agent_reply = chat_response.json()["response"]

    response = client.get(f"/api/agents/threads/{thread_id}")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == thread_id
    texts = [m["text"] for m in data["messages"]]
    assert "What is 2+2?" in texts
    assert agent_reply in texts
