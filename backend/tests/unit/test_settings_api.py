"""Unit tests for the admin-only /api/settings endpoints - TDD discipline."""

import pytest

from app.core.auth import get_current_user
from app.main import app
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services import available_provider_options

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
def test_put_settings_with_empty_string_url_reports_override_true_and_resolves_empty(client):
    """An empty-string llm_url (e.g. selecting the 'fake' provider, whose URL
    template is "") is a deliberate override, not an unset field. The
    is_db_override flag and the resolved value must agree: both should treat
    "" as overridden, not fall back to the env default.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    put_response = client.put(
        "/api/settings",
        json={"llm_provider": "fake", "llm_url": "", "llm_model": ""},
    )

    app.dependency_overrides.clear()

    assert put_response.status_code == 200
    data = put_response.json()
    assert data["llm_url"] == ""
    assert data["llm_url_is_db_override"] is True
    assert data["llm_model"] == ""
    assert data["llm_model_is_db_override"] is True


@pytest.mark.unit
def test_get_settings_fetches_the_settings_row_exactly_once(client, mocker):
    """_to_response resolves both llm and embedding config from the same
    singleton row. It must fetch that row once and reuse it for both
    resolvers, not once directly plus once inside each resolver (3 identical
    SELECTs per request otherwise).
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    get_spy = mocker.spy(SystemSettingsRepository, "get")
    response = client.get("/api/settings")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert get_spy.call_count == 1


@pytest.mark.unit
def test_put_settings_fetches_the_settings_row_exactly_once(client, mocker):
    """Same one-fetch expectation applies to PUT, whose response is built by
    the same _to_response helper after the upsert.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    get_spy = mocker.spy(SystemSettingsRepository, "get")
    response = client.put("/api/settings", json={"llm_provider": "llama-cpp"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    # upsert() also calls get() once internally (to check create-vs-update),
    # so PUT's total is 2: one from upsert, one from _to_response — not 4.
    assert get_spy.call_count == 2


@pytest.mark.unit
def test_put_settings_rejects_empty_url_for_openai_compatible_provider(client):
    """openai-compatible has no detected default URL, so an empty llm_url
    would leave the client with nowhere to send requests — reject at write
    time rather than persisting a value that breaks the next chat call.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put(
        "/api/settings",
        json={"llm_provider": "openai-compatible", "llm_url": ""},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 400


@pytest.mark.unit
def test_put_settings_accepts_empty_url_for_fake_provider(client):
    """The 'fake' provider's URL template is legitimately "" (see
    available_provider_options) — it must not be rejected by the
    required-URL check.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put(
        "/api/settings",
        json={"llm_provider": "fake", "llm_url": ""},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200


@pytest.mark.unit
def test_put_settings_accepts_empty_url_for_llama_cpp_when_provider_unchanged(client):
    """llama-cpp has a detected default URL (from available_provider_options),
    so omitting/clearing llm_url is fine — it falls back to that default via
    resolve_llm_config, not to an empty string.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put(
        "/api/settings",
        json={"llm_provider": "llama-cpp"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200


@pytest.mark.unit
def test_put_settings_all_available_providers_are_accepted(client):
    """Every provider name available_provider_options() advertises to the
    settings screen must be accepted by update_settings — the two lists must
    not be able to drift apart.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    options = available_provider_options()
    for option in options["llm"]:
        url = "http://example:8000/v1" if option["requires_manual_entry"] else option["url"]
        response = client.put(
            "/api/settings",
            json={"llm_provider": option["provider"], "llm_url": url},
        )
        assert response.status_code == 200, f"llm provider {option['provider']} was rejected"

    for option in options["embedding"]:
        url = "http://example:8000/v1" if option["requires_manual_entry"] else option["url"]
        response = client.put(
            "/api/settings",
            json={"embedding_provider": option["provider"], "embedding_url": url},
        )
        assert response.status_code == 200, f"embedding provider {option['provider']} was rejected"

    app.dependency_overrides.clear()


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
