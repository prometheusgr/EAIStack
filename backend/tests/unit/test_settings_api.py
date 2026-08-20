"""Unit tests for the admin-only /api/settings endpoints - TDD discipline."""

import pytest

from app.core.auth import get_current_user
from app.main import app

ADMIN_USER = {
    "user_id": "admin-user-1",
    "username": "admin",
    "email": "admin@example.com",
    "name": "Admin User",
    "token": {"realm_access": {"roles": ["admin"]}},
}

NON_ADMIN_USER = {
    "user_id": "regular-user-1",
    "username": "regular",
    "email": "regular@example.com",
    "name": "Regular User",
    "token": {"realm_access": {"roles": ["offline_access"]}},
}


def _override_user(user: dict):
    def _override():
        return user

    return _override


@pytest.mark.unit
def test_get_settings_without_admin_role_returns_403(client):
    """A non-admin token should be rejected before any settings are returned."""
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings")

    app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.unit
def test_put_settings_without_admin_role_returns_403(client):
    """A non-admin token should be rejected on the write path too."""
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.put("/api/settings", json={"llm_provider": "llama-cpp"})

    app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.unit
def test_get_settings_as_admin_returns_env_defaults_when_no_db_override(client):
    """With no SystemSettings row yet, GET reflects the env-var defaults and
    reports every field as not DB-overridden.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["llm_provider"] == "fake"
    assert data["llm_provider_is_db_override"] is False
    assert data["embedding_provider"] == "fake"
    assert data["embedding_provider_is_db_override"] is False
    assert "llm" in data["available_providers"]
    assert "embedding" in data["available_providers"]


@pytest.mark.unit
def test_get_settings_never_includes_api_key(client):
    """llm_api_key must never appear in the response body, in any form."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings")

    app.dependency_overrides.clear()

    body_text = response.text
    assert "llm_api_key" not in body_text


@pytest.mark.unit
def test_put_settings_persists_and_subsequent_get_reflects_it(client):
    """PUT should create/update the SystemSettings row, and a following GET
    should reflect the new value with is_db_override flipped to True.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    put_response = client.put(
        "/api/settings",
        json={
            "llm_provider": "llama-cpp",
            "llm_url": "http://llama-server:8000/v1",
            "llm_model": "llama-3",
        },
    )
    assert put_response.status_code == 200

    get_response = client.get("/api/settings")

    app.dependency_overrides.clear()

    data = get_response.json()
    assert data["llm_provider"] == "llama-cpp"
    assert data["llm_provider_is_db_override"] is True
    assert data["llm_url"] == "http://llama-server:8000/v1"
    assert data["llm_model"] == "llama-3"
    # Embedding fields were not part of this PUT, so they stay on env defaults.
    assert data["embedding_provider_is_db_override"] is False


@pytest.mark.unit
def test_put_settings_response_never_includes_api_key(client):
    """The PUT response body must also never leak llm_api_key."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"llm_provider": "llama-cpp"})

    app.dependency_overrides.clear()

    assert "llm_api_key" not in response.text


@pytest.mark.unit
def test_put_settings_rejects_unknown_llm_provider(client):
    """An unrecognized llm_provider value should 400, not silently persist."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"llm_provider": "not-a-real-provider"})

    app.dependency_overrides.clear()

    assert response.status_code == 400


@pytest.mark.unit
def test_put_settings_rejects_unknown_embedding_provider(client):
    """An unrecognized embedding_provider value should 400, not silently persist."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"embedding_provider": "not-a-real-provider"})

    app.dependency_overrides.clear()

    assert response.status_code == 400


@pytest.mark.unit
def test_put_settings_with_no_fields_clears_all_overrides_back_to_env_defaults(client):
    """Omitting every field clears the row back to all-NULL, matching the
    nullable-column "fall back to env" semantics.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put(
        "/api/settings",
        json={"llm_provider": "llama-cpp", "llm_url": "http://llama-server:8000/v1"},
    )
    clear_response = client.put("/api/settings", json={})
    get_response = client.get("/api/settings")

    app.dependency_overrides.clear()

    assert clear_response.status_code == 200
    data = get_response.json()
    assert data["llm_provider"] == "fake"
    assert data["llm_provider_is_db_override"] is False
