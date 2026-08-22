"""Integration tests for the chat agent flow."""

import pytest

from app.core.auth import get_current_user
from app.main import app


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
