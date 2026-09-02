"""Unit tests for the admin-only /api/settings endpoints - TDD discipline."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.auth import get_current_user
from app.core.config import settings
from app.main import app
from app.repositories import AuditLogRepository, GuardrailPatternRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services import available_provider_options
from app.services.provider_probe_service import ProviderProbeResult

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


# --- POST /api/settings/test-connection --------------------------------------


@pytest.mark.unit
def test_test_connection_without_admin_role_returns_403(client):
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.post("/api/settings/test-connection", json={"url": "http://x:8000/v1"})

    app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.unit
def test_test_connection_returns_probe_result_on_success(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    with patch(
        "app.api.settings.probe_provider",
        new=AsyncMock(
            return_value=ProviderProbeResult(
                ok=True, models=["llama-3-8b", "nomic-embed"], error=None
            )
        ),
    ):
        response = client.post(
            "/api/settings/test-connection", json={"url": "http://llama-server:8000/v1"}
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["models"] == ["llama-3-8b", "nomic-embed"]
    assert data["error"] is None


@pytest.mark.unit
def test_test_connection_returns_200_with_ok_false_on_probe_failure(client):
    """A failed probe is a diagnostic result, not a request error -- the
    frontend should never have to special-case HTTP status vs. body to
    render the same "connection failed" state.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    with patch(
        "app.api.settings.probe_provider",
        new=AsyncMock(
            return_value=ProviderProbeResult(
                ok=False, models=[], error="Could not reach http://x:8000/v1: connection refused"
            )
        ),
    ):
        response = client.post("/api/settings/test-connection", json={"url": "http://x:8000/v1"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["models"] == []
    assert "connection refused" in data["error"]


@pytest.mark.unit
def test_put_settings_response_never_includes_api_key(client):
    """The PUT response body must also never leak llm_api_key."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"llm_provider": "llama-cpp"})

    app.dependency_overrides.clear()

    assert "llm_api_key" not in response.text


@pytest.mark.unit
def test_put_settings_rejects_unknown_llm_provider(client):
    """An unrecognized llm_provider value should 400, not silently persist.

    Also asserts on `message`: the Settings screen's toast reads only
    ApiErrorImpl.message (never the machine-readable `detail`), so a
    response missing `message` reaches the admin as a blank toast — the
    same contract agents.py's guardrail/rate-limit 400s already follow.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"llm_provider": "not-a-real-provider"})

    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "not-a-real-provider" in response.json()["message"]


@pytest.mark.unit
def test_put_settings_rejects_unknown_embedding_provider(client):
    """An unrecognized embedding_provider value should 400, not silently persist."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"embedding_provider": "not-a-real-provider"})

    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "not-a-real-provider" in response.json()["message"]


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
    assert "openai-compatible" in response.json()["message"]


@pytest.mark.unit
def test_put_settings_rejects_empty_url_for_openai_compatible_embedding_provider(client):
    """Same rejection as the LLM-provider case above, for the embedding side
    -- this branch had no dedicated test before.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put(
        "/api/settings",
        json={"embedding_provider": "llama-cpp", "embedding_url": ""},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "llama-cpp" in response.json()["message"]


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


@pytest.mark.unit
def test_available_provider_options_suggests_this_deployment_s_configured_urls(monkeypatch):
    """The "detected" URLs must come from this deployment's own env config.

    The catalog is what the Settings screen offers an admin as the URL for a
    provider. Hardcoding docker-compose's service DNS names made that offer
    wrong on any deployment that names its services differently (K3s uses
    eaistack-embedding-server, per infra/k3s/doc-search-deployment.yaml), so
    an admin picking "detected" from the dropdown would persist a hostname
    unresolvable in their own cluster — overriding, via the DB row, the very
    env var that deployment had set correctly.
    """
    monkeypatch.setattr(settings, "llm_provider", "llama-cpp")
    monkeypatch.setattr(settings, "llm_url", "http://eaistack-llama-server:8000/v1")
    monkeypatch.setattr(settings, "embedding_provider", "llama-cpp")
    monkeypatch.setattr(settings, "embedding_url", "http://eaistack-embedding-server:8000/v1")

    options = available_provider_options()

    llm_llama = next(o for o in options["llm"] if o["provider"] == "llama-cpp")
    embedding_llama = next(o for o in options["embedding"] if o["provider"] == "llama-cpp")

    assert llm_llama["url"] == "http://eaistack-llama-server:8000/v1"
    assert embedding_llama["url"] == "http://eaistack-embedding-server:8000/v1"


@pytest.mark.unit
def test_available_provider_options_leaves_non_detected_providers_without_a_url(monkeypatch):
    """Only the configured provider is offered this deployment's URL.

    "fake" needs no URL, and a provider this deployment did not configure
    has no known address here — neither should be pre-filled from llm_url,
    which describes only the endpoint llm_provider names.
    """
    monkeypatch.setattr(settings, "llm_provider", "llama-cpp")
    monkeypatch.setattr(settings, "llm_url", "http://eaistack-llama-server:8000/v1")

    options = available_provider_options()

    assert next(o for o in options["llm"] if o["provider"] == "fake")["url"] == ""
    assert next(o for o in options["llm"] if o["provider"] == "openai-compatible")["url"] == ""


@pytest.mark.unit
def test_available_provider_options_suggests_configured_url_for_a_remote_llm(monkeypatch):
    """A deployment whose LLM is a hosted endpoint, not a local llama-server.

    There may be no llama.cpp pod at all — LLM_URL can point at Azure
    OpenAI, Bedrock, or any OpenAI-compatible gateway. The configured URL
    must then be offered against the provider that deployment actually set
    (openai-compatible), and must NOT be offered as the llama-cpp default:
    labelling a hosted endpoint "llama-server, detected" would be plainly
    wrong, and would invite an admin to save a remote URL under a provider
    that is not what their deployment runs.
    """
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_url", "https://example.openai.azure.com/openai/v1")

    options = available_provider_options()

    openai_option = next(o for o in options["llm"] if o["provider"] == "openai-compatible")
    llama_option = next(o for o in options["llm"] if o["provider"] == "llama-cpp")

    assert openai_option["url"] == "https://example.openai.azure.com/openai/v1"
    assert llama_option["url"] == ""


@pytest.mark.unit
def test_available_provider_options_marks_only_the_configured_provider_as_detected(monkeypatch):
    """ "Detected" means "this is what your deployment is configured to use".

    It is a claim about configuration, so exactly the configured provider may
    carry it — otherwise the screen tells a llama-cpp deployment that a
    hosted endpoint was detected, or vice versa.
    """
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_url", "https://example.openai.azure.com/openai/v1")

    options = available_provider_options()

    detected = [o["provider"] for o in options["llm"] if "detected" in o["label"]]
    assert detected == ["openai-compatible"]


@pytest.mark.unit
def test_available_provider_options_never_suggests_a_url_for_fake(monkeypatch):
    """The fake provider is in-process; a URL for it is meaningless."""
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(settings, "llm_url", "https://example.openai.azure.com/openai/v1")

    options = available_provider_options()

    assert next(o for o in options["llm"] if o["provider"] == "fake")["url"] == ""


# --- Guardrail config (issue #16) ---------------------------------------------


@pytest.mark.unit
def test_get_settings_includes_guardrail_fields_with_env_defaults(client):
    """With no SystemSettings row, GET reflects env-level guardrail
    defaults and reports every guardrail field as not DB-overridden.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["max_input_length"] == settings.guardrail_max_input_length
    assert data["max_input_length_is_db_override"] is False
    assert data["guardrails_input_enabled"] is True
    assert data["guardrails_input_enabled_is_db_override"] is False
    assert data["guardrails_output_enabled"] is True
    assert data["guardrails_output_enabled_is_db_override"] is False
    assert isinstance(data["guardrail_patterns"], list)
    assert len(data["guardrail_patterns"]) > 0


@pytest.mark.unit
def test_put_settings_updates_guardrail_fields_and_get_reflects_override(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    put_response = client.put(
        "/api/settings",
        json={
            "max_input_length": 500,
            "guardrails_input_enabled": False,
            "guardrails_output_enabled": False,
        },
    )
    assert put_response.status_code == 200

    get_response = client.get("/api/settings")

    app.dependency_overrides.clear()

    data = get_response.json()
    assert data["max_input_length"] == 500
    assert data["max_input_length_is_db_override"] is True
    assert data["guardrails_input_enabled"] is False
    assert data["guardrails_input_enabled_is_db_override"] is True
    assert data["guardrails_output_enabled"] is False
    assert data["guardrails_output_enabled_is_db_override"] is True


@pytest.mark.unit
def test_put_settings_max_input_length_over_ceiling_returns_422(client):
    """8001 exceeds MAX_INPUT_LENGTH_CEILING -- rejected by Pydantic
    validation before it ever reaches the service/DB layer.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"max_input_length": 8001})

    app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.unit
def test_put_settings_max_input_length_below_one_returns_422(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"max_input_length": 0})

    app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.unit
def test_put_settings_records_guardrail_config_update_audit_entries_only_for_changed_fields(
    client, db_session
):
    """Mirrors the retention audit test: re-saving settings without
    touching guardrail fields must not fabricate audit entries, and a
    changed field is recorded under the "guardrail.config_update" action.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"guardrails_input_enabled": False})
    client.put("/api/settings", json={"guardrails_input_enabled": False})  # unchanged re-save

    app.dependency_overrides.clear()

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "guardrail.config_update"
    ]
    assert len(entries) == 1
    assert entries[0].field_name == "guardrails_input_enabled"
    assert entries[0].old_value is None
    assert entries[0].new_value == "False"


@pytest.mark.unit
def test_put_settings_guardrail_audit_entry_records_actual_transition(client, db_session):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"max_input_length": 500})
    client.put("/api/settings", json={"max_input_length": 250})

    app.dependency_overrides.clear()

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "guardrail.config_update" and e.field_name == "max_input_length"
    ]
    # Newest first: the second PUT (500 -> 250) then the first (None -> 500).
    assert entries[0].old_value == "500"
    assert entries[0].new_value == "250"
    assert entries[1].old_value is None
    assert entries[1].new_value == "500"


# --- Tracing config (issue #4) ------------------------------------------------


@pytest.mark.unit
def test_get_settings_includes_tracing_field_with_env_default(client):
    """With no SystemSettings row, GET reflects the env-level
    tracing_enabled default and reports it as not DB-overridden.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["tracing_enabled"] == settings.tracing_enabled
    assert data["tracing_enabled_is_db_override"] is False


@pytest.mark.unit
def test_put_settings_updates_tracing_field_and_get_reflects_override(client):
    """PUT should persist a tracing_enabled override, and a following GET
    should reflect it with is_db_override flipped to True -- the same
    round trip every other overridable field goes through, even though
    (unlike them) this one requires a backend restart to actually take
    effect on the running tracer.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    put_response = client.put("/api/settings", json={"tracing_enabled": True})
    assert put_response.status_code == 200

    get_response = client.get("/api/settings")

    app.dependency_overrides.clear()

    data = get_response.json()
    assert data["tracing_enabled"] is True
    assert data["tracing_enabled_is_db_override"] is True


@pytest.mark.unit
def test_put_settings_records_tracing_config_update_audit_entries_only_for_changed_fields(
    client, db_session
):
    """Mirrors the guardrail audit test: re-saving settings without
    touching tracing_enabled must not fabricate audit entries, and a
    changed field is recorded under the "tracing.config_update" action.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"tracing_enabled": True})
    client.put("/api/settings", json={"tracing_enabled": True})  # unchanged re-save

    app.dependency_overrides.clear()

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "tracing.config_update"
    ]
    assert len(entries) == 1
    assert entries[0].field_name == "tracing_enabled"
    assert entries[0].old_value is None
    assert entries[0].new_value == "True"


@pytest.mark.unit
def test_put_settings_tracing_audit_entry_records_actual_transition(client, db_session):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"tracing_enabled": True})
    client.put("/api/settings", json={"tracing_enabled": False})

    app.dependency_overrides.clear()

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "tracing.config_update" and e.field_name == "tracing_enabled"
    ]
    # Newest first: the second PUT (True -> False) then the first (None -> True).
    assert entries[0].old_value == "True"
    assert entries[0].new_value == "False"
    assert entries[1].old_value is None
    assert entries[1].new_value == "True"


# --- Rate limiting (issue #25) -------------------------------------------------


@pytest.mark.unit
def test_get_settings_includes_rate_limit_fields_with_env_defaults(client):
    """With no SystemSettings row, GET reflects the env-level rate-limit
    defaults and reports every field as not DB-overridden.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["rate_limit_enabled"] == settings.rate_limit_enabled
    assert data["rate_limit_enabled_is_db_override"] is False
    assert data["rate_limit_chat_capacity"] == settings.rate_limit_chat_capacity
    assert data["rate_limit_chat_capacity_is_db_override"] is False
    assert data["rate_limit_chat_refill_per_minute"] == settings.rate_limit_chat_refill_per_minute
    assert data["rate_limit_chat_refill_per_minute_is_db_override"] is False
    assert data["rate_limit_auth_capacity"] == settings.rate_limit_auth_capacity
    assert data["rate_limit_auth_capacity_is_db_override"] is False
    assert data["rate_limit_auth_refill_per_minute"] == settings.rate_limit_auth_refill_per_minute
    assert data["rate_limit_auth_refill_per_minute_is_db_override"] is False


@pytest.mark.unit
def test_put_settings_updates_rate_limit_fields_and_get_reflects_override(client):
    """PUT should persist rate-limit overrides, and a following GET should
    reflect them with is_db_override flipped to True -- the same round trip
    every other overridable field goes through.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    put_response = client.put(
        "/api/settings",
        json={
            "rate_limit_enabled": False,
            "rate_limit_chat_capacity": 3,
            "rate_limit_chat_refill_per_minute": 2,
            "rate_limit_auth_capacity": 5,
            "rate_limit_auth_refill_per_minute": 4,
        },
    )
    assert put_response.status_code == 200

    get_response = client.get("/api/settings")

    app.dependency_overrides.clear()

    data = get_response.json()
    assert data["rate_limit_enabled"] is False
    assert data["rate_limit_enabled_is_db_override"] is True
    assert data["rate_limit_chat_capacity"] == 3
    assert data["rate_limit_chat_capacity_is_db_override"] is True
    assert data["rate_limit_chat_refill_per_minute"] == 2
    assert data["rate_limit_chat_refill_per_minute_is_db_override"] is True
    assert data["rate_limit_auth_capacity"] == 5
    assert data["rate_limit_auth_capacity_is_db_override"] is True
    assert data["rate_limit_auth_refill_per_minute"] == 4
    assert data["rate_limit_auth_refill_per_minute_is_db_override"] is True


@pytest.mark.unit
def test_put_settings_rate_limit_capacity_below_one_returns_422(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"rate_limit_chat_capacity": 0})

    app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.unit
def test_put_settings_records_rate_limit_config_update_audit_entries_only_for_changed_fields(
    client, db_session
):
    """Mirrors the tracing audit test: re-saving settings without touching
    the rate-limit fields must not fabricate audit entries, and a changed
    field is recorded under the "rate_limit.config_update" action.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"rate_limit_chat_capacity": 5})
    client.put("/api/settings", json={"rate_limit_chat_capacity": 5})  # unchanged re-save

    app.dependency_overrides.clear()

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "rate_limit.config_update"
    ]
    assert len(entries) == 1
    assert entries[0].field_name == "rate_limit_chat_capacity"
    assert entries[0].old_value is None
    assert entries[0].new_value == "5"


@pytest.mark.unit
def test_put_settings_rate_limit_audit_entry_records_actual_transition(client, db_session):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"rate_limit_chat_capacity": 5})
    client.put("/api/settings", json={"rate_limit_chat_capacity": 8})

    app.dependency_overrides.clear()

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "rate_limit.config_update" and e.field_name == "rate_limit_chat_capacity"
    ]
    # Newest first: the second PUT (5 -> 8) then the first (None -> 5).
    assert entries[0].old_value == "5"
    assert entries[0].new_value == "8"
    assert entries[1].old_value is None
    assert entries[1].new_value == "5"


# --- Guardrail pattern endpoints (issue #16) ----------------------------------


@pytest.mark.unit
def test_create_guardrail_pattern_happy_path(client, db_session):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.post(
        "/api/settings/guardrail-patterns",
        json={"label": "Leak the secret sauce", "pattern_text": "leak the secret sauce"},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "custom"
    assert data["label"] == "Leak the secret sauce"
    assert data["pattern_text"] == "leak the secret sauce"
    assert data["enabled"] is True

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "guardrail.pattern_update"
    ]
    assert len(entries) == 1
    assert entries[0].field_name == data["id"]
    assert entries[0].old_value is None
    assert entries[0].new_value == "leak the secret sauce"


@pytest.mark.unit
def test_toggle_guardrail_pattern_happy_path(client, db_session):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    create_response = client.post(
        "/api/settings/guardrail-patterns",
        json={"label": "Custom phrase", "pattern_text": "custom phrase"},
    )
    pattern_id = create_response.json()["id"]

    toggle_response = client.put(
        f"/api/settings/guardrail-patterns/{pattern_id}", json={"enabled": False}
    )

    app.dependency_overrides.clear()

    assert toggle_response.status_code == 200
    assert toggle_response.json()["enabled"] is False

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "guardrail.pattern_update" and e.field_name == pattern_id
    ]
    assert entries[0].old_value == "enabled"
    assert entries[0].new_value == "disabled"


@pytest.mark.unit
def test_toggle_guardrail_pattern_unknown_id_returns_404(client):
    """Also asserts on `message`: the Settings screen's toast reads only
    ApiErrorImpl.message, so a response missing it reaches the admin as a
    blank toast (see test_put_settings_rejects_unknown_llm_provider).
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put(
        "/api/settings/guardrail-patterns/does-not-exist", json={"enabled": False}
    )

    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["message"]


@pytest.mark.unit
def test_toggle_guardrail_pattern_can_toggle_a_built_in_pattern(client, db_session):
    """Built-in patterns can be toggled (only deletion is refused)."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    # GET seeds the built-in rows.
    client.get("/api/settings")
    built_in_id = GuardrailPatternRepository(db_session).list_all()[0].id

    response = client.put(
        f"/api/settings/guardrail-patterns/{built_in_id}", json={"enabled": False}
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["enabled"] is False


@pytest.mark.unit
def test_delete_guardrail_pattern_happy_path(client, db_session):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    create_response = client.post(
        "/api/settings/guardrail-patterns",
        json={"label": "Custom phrase", "pattern_text": "custom phrase"},
    )
    pattern_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/settings/guardrail-patterns/{pattern_id}")

    app.dependency_overrides.clear()

    assert delete_response.status_code == 204
    assert GuardrailPatternRepository(db_session).get(pattern_id) is None

    entries = [
        e
        for e in AuditLogRepository(db_session).list_recent()
        if e.action == "guardrail.pattern_update" and e.field_name == pattern_id
    ]
    assert entries[0].old_value == "custom phrase"
    assert entries[0].new_value is None


@pytest.mark.unit
def test_delete_guardrail_pattern_unknown_id_returns_404(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.delete("/api/settings/guardrail-patterns/does-not-exist")

    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["message"]


@pytest.mark.unit
def test_delete_guardrail_pattern_refuses_a_built_in_pattern(client, db_session):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.get("/api/settings")  # seeds built-ins
    built_in_id = GuardrailPatternRepository(db_session).list_all()[0].id

    response = client.delete(f"/api/settings/guardrail-patterns/{built_in_id}")

    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["message"]
    assert GuardrailPatternRepository(db_session).get(built_in_id) is not None


@pytest.mark.unit
def test_guardrail_pattern_endpoints_require_admin(client):
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    create_response = client.post(
        "/api/settings/guardrail-patterns",
        json={"label": "Custom phrase", "pattern_text": "custom phrase"},
    )
    toggle_response = client.put(
        "/api/settings/guardrail-patterns/some-id", json={"enabled": False}
    )
    delete_response = client.delete("/api/settings/guardrail-patterns/some-id")

    app.dependency_overrides.clear()

    assert create_response.status_code == 403
    assert toggle_response.status_code == 403
    assert delete_response.status_code == 403
