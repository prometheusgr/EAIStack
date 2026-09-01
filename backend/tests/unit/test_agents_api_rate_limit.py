"""Tests for rate-limit enforcement on POST /api/agents/chat.

Separate file from test_agents_api.py/test_agents_api_guardrails.py, per
this repo's existing convention of one file per concern within
tests/unit/.
"""

import pytest

from app.core.auth import get_current_user
from app.db.models import SystemSettings
from app.main import app
from app.repositories import AuditLogRepository
from app.repositories.system_settings_repository import SystemSettingsRepository

# Bucket state is reset automatically before/after every test by the
# autouse _reset_rate_limit_state fixture in tests/conftest.py.


def _login_as(user_id: str) -> dict:
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


def _set_chat_capacity(db_session, capacity: int) -> None:
    db_session.add(
        SystemSettings(
            id="default",
            rate_limit_chat_capacity=capacity,
            rate_limit_chat_refill_per_minute=1,
            updated_by="admin-1",
        )
    )
    db_session.commit()


@pytest.mark.unit
def test_chat_endpoint_returns_429_after_capacity_exhausted(client, db_session):
    _set_chat_capacity(db_session, capacity=1)
    _login_as("user-a")

    client.post("/api/agents/chat", json={"message": "hello"})
    response = client.post("/api/agents/chat", json={"message": "hello again"})

    app.dependency_overrides.clear()

    assert response.status_code == 429
    assert response.json()["detail"] == "rate_limit_exceeded"


@pytest.mark.unit
def test_chat_endpoint_429_response_includes_retry_after_header(client, db_session):
    _set_chat_capacity(db_session, capacity=1)
    _login_as("user-a")

    client.post("/api/agents/chat", json={"message": "hello"})
    response = client.post("/api/agents/chat", json={"message": "hello again"})

    app.dependency_overrides.clear()

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.unit
def test_chat_endpoint_rate_limit_is_scoped_per_user_not_global(client, db_session):
    """One user exhausting their bucket must not 429 another user."""
    _set_chat_capacity(db_session, capacity=1)

    _login_as("user-a")
    client.post("/api/agents/chat", json={"message": "hello"})
    exhausted_response = client.post("/api/agents/chat", json={"message": "hello again"})

    _login_as("user-b")
    other_user_response = client.post("/api/agents/chat", json={"message": "hello"})

    app.dependency_overrides.clear()

    assert exhausted_response.status_code == 429
    assert other_user_response.status_code == 200


@pytest.mark.unit
def test_chat_endpoint_does_not_audit_log_a_rate_limit_trip(client, db_session):
    """A 429 trip is an operational signal, not a compliance-relevant
    event like a guardrail rejection -- see docs/SECURITY.md's
    rate-limiting section for the full rationale. No AuditLog entry should
    be written for the trip itself (config *changes* are audited
    separately, in test_settings_api.py).
    """
    _set_chat_capacity(db_session, capacity=1)
    _login_as("user-a")

    client.post("/api/agents/chat", json={"message": "hello"})
    client.post("/api/agents/chat", json={"message": "hello again"})  # trips the limit

    app.dependency_overrides.clear()

    entries = [e for e in AuditLogRepository(db_session).list_recent() if "rate_limit" in e.action]
    assert entries == []


@pytest.mark.unit
def test_chat_endpoint_shares_one_system_settings_fetch_between_rate_limit_and_guardrail(
    client, db_session, monkeypatch
):
    """Rate-limit config and guardrail config both read the same singleton
    SystemSettings row - chat() must fetch it once and share it between
    both resolvers, the same way app.api.settings._to_response does for
    every resolver, rather than each resolver issuing its own SELECT.

    A successful chat request also triggers one further, independent
    SystemSettings SELECT inside create_chat_agent -> get_llm_client's own
    provider-config resolution (app.services.system_settings_service) -
    a separate, pre-existing resolution path this test does not touch.
    So the assertion is call_count == 2 (one shared fetch for rate-limit +
    guardrail, one for the LLM client), not 1 - proving chat() itself
    stopped doubling its own fetch without over-asserting on a call site
    outside this endpoint's responsibility.
    """
    _login_as("user-a")

    call_count = 0
    original_get = SystemSettingsRepository.get

    def counting_get(self):
        nonlocal call_count
        call_count += 1
        return original_get(self)

    monkeypatch.setattr(SystemSettingsRepository, "get", counting_get)

    response = client.post("/api/agents/chat", json={"message": "hello"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert call_count == 2
