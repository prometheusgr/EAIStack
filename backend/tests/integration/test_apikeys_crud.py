"""Integration tests for API Keys CRUD endpoints.

Auth is stubbed through FastAPI's app.dependency_overrides rather than
unittest.mock.patch on app.api.apikeys.get_current_user. Patching that module
attribute has no effect: FastAPI resolves Depends(get_current_user) into each
route's dependency graph at import time, so the route keeps calling the
original function and every request 403s on real token verification. The
override registry is the supported seam, and is what
tests/integration/test_agent_chat_flow.py already uses.
"""

from contextlib import contextmanager

import pytest

from app.core.auth import get_current_user
from app.main import app


@contextmanager
def _authenticated_as(user: dict):
    """Make the API treat every request in the block as coming from `user`."""
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.integration
def test_create_apikey_endpoint(client, db_session, mock_keycloak_token):
    """Test: POST /api/apikeys creates a key and returns masked secret."""
    user_id = mock_keycloak_token["sub"]

    authenticated_user = {
        "user_id": user_id,
        "username": "testuser",
        "email": "testuser@example.com",
        "name": "Test User",
        "token": mock_keycloak_token,
    }

    with _authenticated_as(authenticated_user):
        payload = {
            "name": "OpenAI API Key",
            "provider": "openai",
            "secret_value": "sk-proj-1234567890abcdefghij",
        }

        response = client.post("/api/apikeys", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "OpenAI API Key"
        assert data["provider"] == "openai"
        assert "secret_value_masked" in data
        assert "1234567890" not in data["secret_value_masked"]
        assert data["user_id"] == user_id

        # Verify it's actually in the database
        from app.db.models import APIKey

        key = db_session.query(APIKey).filter_by(user_id=user_id).first()
        assert key is not None
        assert key.name == "OpenAI API Key"


@pytest.mark.integration
def test_list_apikeys_user_isolation(client, db_session, mock_keycloak_token):
    """Test: GET /api/apikeys returns only the current user's keys."""
    user_a_id = "user-a-123"
    user_b_id = "user-b-456"

    # Insert keys for both users
    from app.db.models import APIKey

    key_a = APIKey(
        id="key-a-1",
        user_id=user_a_id,
        name="User A Key",
        provider="openai",
        secret_value="secret-a",
    )
    key_b = APIKey(
        id="key-b-1",
        user_id=user_b_id,
        name="User B Key",
        provider="anthropic",
        secret_value="secret-b",
    )
    db_session.add_all([key_a, key_b])
    db_session.commit()

    # List as user A
    token_a = {**mock_keycloak_token, "sub": user_a_id}

    user_a = {
        "user_id": user_a_id,
        "username": "usera",
        "email": "usera@example.com",
        "name": "User A",
        "token": token_a,
    }

    with _authenticated_as(user_a):
        response = client.get("/api/apikeys")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "User A Key"
        assert data[0]["user_id"] == user_a_id


@pytest.mark.integration
def test_get_apikey_detail_masked(client, db_session, mock_keycloak_token):
    """Test: GET /api/apikeys/{id} returns masked secret."""
    user_id = mock_keycloak_token["sub"]

    # Insert a key
    from app.db.models import APIKey

    key = APIKey(
        id="key-test-1",
        user_id=user_id,
        name="My Key",
        provider="openai",
        secret_value="sk-proj-very-long-secret-value-here",
    )
    db_session.add(key)
    db_session.commit()

    authenticated_user = {
        "user_id": user_id,
        "username": "testuser",
        "email": "testuser@example.com",
        "name": "Test User",
        "token": mock_keycloak_token,
    }

    with _authenticated_as(authenticated_user):
        response = client.get("/api/apikeys/key-test-1")
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "My Key"
        assert "secret_value_masked" in data
        assert "very-long-secret" not in data["secret_value_masked"]


@pytest.mark.integration
def test_update_apikey_name_only(client, db_session, mock_keycloak_token):
    """Test: PUT /api/apikeys/{id} updates name, secret stays immutable."""
    user_id = mock_keycloak_token["sub"]

    from app.db.models import APIKey

    key = APIKey(
        id="key-update-1",
        user_id=user_id,
        name="Original Name",
        provider="openai",
        secret_value="sk-proj-original-secret",
    )
    db_session.add(key)
    db_session.commit()

    authenticated_user = {
        "user_id": user_id,
        "username": "testuser",
        "email": "testuser@example.com",
        "name": "Test User",
        "token": mock_keycloak_token,
    }

    with _authenticated_as(authenticated_user):
        # provider is required by APIKeyUpdate; secret_value is not part of
        # that schema at all, and is sent here to prove it cannot be used to
        # overwrite the stored secret.
        payload = {
            "name": "Updated Name",
            "provider": "openai",
            "secret_value": "sk-proj-new-secret",
        }
        response = client.put("/api/apikeys/key-update-1", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

        # Verify secret didn't change
        refreshed = db_session.query(APIKey).filter_by(id="key-update-1").first()
        assert refreshed.secret_value == "sk-proj-original-secret"


@pytest.mark.integration
def test_revoke_apikey_endpoint(client, db_session, mock_keycloak_token):
    """Test: DELETE /api/apikeys/{id} sets revoked_at, excludes from list."""
    user_id = mock_keycloak_token["sub"]

    from app.db.models import APIKey

    key = APIKey(
        id="key-revoke-1",
        user_id=user_id,
        name="To Revoke",
        provider="openai",
        secret_value="sk-proj-secret",
    )
    db_session.add(key)
    db_session.commit()

    authenticated_user = {
        "user_id": user_id,
        "username": "testuser",
        "email": "testuser@example.com",
        "name": "Test User",
        "token": mock_keycloak_token,
    }

    with _authenticated_as(authenticated_user):
        # Revoke
        response = client.delete("/api/apikeys/key-revoke-1")
        assert response.status_code == 200
        data = response.json()
        assert data["revoked_at"] is not None

        # Verify it's not in list
        response = client.get("/api/apikeys")
        keys = response.json()
        assert len(keys) == 0


@pytest.mark.integration
def test_access_other_users_key_denied(client, db_session, mock_keycloak_token):
    """Test: Cannot access or modify another user's key."""
    user_a_id = "user-a"
    user_b_id = "user-b"

    # Create key for user A
    from app.db.models import APIKey

    key = APIKey(
        id="key-other-user",
        user_id=user_a_id,
        name="User A's Secret",
        provider="openai",
        secret_value="sk-proj-secret",
    )
    db_session.add(key)
    db_session.commit()

    # Try to access as user B
    token_b = {**mock_keycloak_token, "sub": user_b_id}

    user_b = {
        "user_id": user_b_id,
        "username": "userb",
        "email": "userb@example.com",
        "name": "User B",
        "token": token_b,
    }

    with _authenticated_as(user_b):
        response = client.get("/api/apikeys/key-other-user")
        assert response.status_code == 404
