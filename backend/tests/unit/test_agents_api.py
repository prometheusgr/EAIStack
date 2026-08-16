"""Tests for the agents API endpoint."""

import uuid

import pytest

from app.core.auth import get_current_user
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
def test_chat_endpoint_preserves_thread_id(client):
    """POST /api/agents/chat should preserve provided thread_id."""
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    thread_id = "my-custom-thread-456"
    response = client.post("/api/agents/chat", json={"message": "Hello", "thread_id": thread_id})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == thread_id


@pytest.mark.unit
def test_chat_endpoint_response_shape(client):
    """POST /api/agents/chat response should match ChatResponse schema."""
    fake_user = {
        "user_id": "test-user-123",
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "token": {},
    }

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.post("/api/agents/chat", json={"message": "What is AI?"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()

    # Validate schema
    assert set(data.keys()) == {"response", "thread_id"}
    assert isinstance(data["response"], str)
    assert isinstance(data["thread_id"], str)
