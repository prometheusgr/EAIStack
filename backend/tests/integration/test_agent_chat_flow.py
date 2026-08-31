"""Integration tests for the chat agent flow."""

from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolCall

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.llm_client import FakeChatModel
from app.db.models import Embedding, KnowledgeBase
from app.main import app
from app.services import generate_embedding
from tests.conftest import FAKE_KEYCLOAK_PRIVATE_KEY
from tests.integration.doc_search_helper import make_signed_token, running_doc_search_subprocess


@pytest.mark.integration
def test_agent_chat_flow_happy_path(client):
    """Happy-path integration test: authenticate, send message, get response.

    Takes the shared `client` fixture rather than building a bare
    TestClient(app): the fixture overrides get_db to the isolated test
    database. Without it this test runs against whatever database the
    developer's environment points at, so a runtime provider override stored
    in that database's system_settings row (an admin can set one through the
    Settings screen) would silently decide which LLM this test calls.
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

    response = client.post(
        "/api/agents/chat",
        json={"message": "What time is it?"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 0
    assert "thread_id" in data
    assert isinstance(data["thread_id"], str)


@pytest.mark.integration
def test_chat_endpoint_returns_sources_grounding_the_answer(
    client, db_session, test_db_url, fake_keycloak_jwks_server, monkeypatch
):
    """POST /api/agents/chat's response includes which knowledge-base
    document(s) grounded the answer, end-to-end through the real doc-search
    MCP server -- the full slice for issue #19.
    """
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


@pytest.mark.integration
def test_chat_endpoint_second_turn_on_same_thread_does_not_leak_or_crash_on_prior_sources(
    client, db_session, test_db_url, fake_keycloak_jwks_server, monkeypatch
):
    """Regression test: a second message on a thread whose first turn called
    search_knowledge_base must not crash, and must not resurface the first
    turn's source when the second turn doesn't call the tool itself.

    This exercises the real production failure mode the unit-level
    extract_sources_from_messages tests can only simulate: the first turn's
    ToolMessage is persisted via SqlAlchemyCheckpointSaver and reloaded from
    Postgres for the second turn's graph.ainvoke() call, so its .artifact
    comes back as a plain dict (langgraph's JsonPlusSerializer has no custom
    serializer registered for the Source dataclass) rather than a Source
    instance -- extract_sources_from_messages must never touch it.
    """
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
    turn_1_final = AIMessage(content="You get 25 days of paid vacation per year.")
    turn_2_final = AIMessage(content="I'm doing well, thanks for asking!")
    fake_llm = FakeChatModel(responses=[tool_call_message, turn_1_final, turn_2_final])
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

    with running_doc_search_subprocess(test_db_url, fake_keycloak_jwks_server, 8202) as mcp_url:
        monkeypatch.setattr(settings, "doc_search_mcp_url", mcp_url)

        first_response = client.post(
            "/api/agents/chat", json={"message": "How many vacation days do I get?"}
        )
        thread_id = first_response.json()["thread_id"]

        second_response = client.post(
            "/api/agents/chat",
            json={"message": "How are you today?", "thread_id": thread_id},
        )

    app.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert first_response.json()["sources"] == [
        {"knowledge_base_id": kb.id, "title": "Vacation Policy", "heading_path": None}
    ]

    assert second_response.status_code == 200
    assert second_response.json()["sources"] == []
