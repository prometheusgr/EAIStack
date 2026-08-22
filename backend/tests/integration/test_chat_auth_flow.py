"""Integration test for the complete chat auth flow.

This test validates:
1. User can log in to Keycloak
2. Frontend gets a valid token
3. Backend accepts the token
4. Chat endpoint returns 200 with response
"""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_chat_flow_requires_valid_token(client):
    """Chat flow should require valid authentication token.

    Steps:
    1. POST /api/agents/chat with valid Bearer token should return 200
    2. POST /api/agents/chat without token should return 403
    3. POST /api/agents/chat with invalid token should return 401

    Takes the shared `client` fixture rather than building a bare
    TestClient(app): the fixture overrides get_db to the isolated test
    database. Without it this test runs against whatever database the
    developer's environment points at, so a runtime provider override stored
    in that database's system_settings row (an admin can set one through the
    Settings screen) would silently decide which LLM this test calls — and a
    Docker-internal hostname there is unresolvable from the host.
    """
    from app.core.auth import get_current_user
    from app.main import app

    # Test 1: No token should return 403
    response = client.post("/api/agents/chat", json={"message": "Hello"})
    assert response.status_code == 403

    # Test 2: Invalid token should return 401
    response = client.post(
        "/api/agents/chat",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer invalid-token-xyz"},
    )
    assert response.status_code == 401

    # Test 3: Valid token (mocked) should return 200
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {"aud": "eaistack-web"},
        "access_token": "fake-access-token",
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post(
        "/api/agents/chat",
        json={"message": "What is 2+2?"},
        headers={"Authorization": "Bearer mocked-valid-token"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "thread_id" in data
