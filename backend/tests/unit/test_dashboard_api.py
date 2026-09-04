"""Unit tests for the admin-only GET /api/settings/dashboard endpoint (issue #48) - TDD discipline."""

import pytest

from app.core.auth import get_current_user
from app.main import app
from app.repositories import AuditLogRepository
from app.services.rate_limiter_service import reset_rate_limit_state

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


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets():
    """Rate-limit bucket state is a process-global dict (see
    app.services.rate_limiter_service) - must not leak between tests.
    """
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


@pytest.mark.unit
def test_dashboard_endpoint_is_admin_only(client):
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings/dashboard")

    app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.unit
def test_dashboard_endpoint_reports_rate_limit_status(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings/dashboard")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    rate_limit = response.json()["rate_limit"]
    assert rate_limit["active_bucket_count"] == 0
    assert isinstance(rate_limit["enabled"], bool)


@pytest.mark.unit
def test_dashboard_endpoint_reports_guardrail_trip_counts_from_the_audit_trail(client, db_session):
    """A real guardrail.input_rejected entry must be reflected in the
    dashboard's per-pattern counts -- proving the endpoint reads real audit
    data, not a placeholder.
    """
    from app.db.models import utc_now

    AuditLogRepository(db_session).record(
        actor_user_id="user-1",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="sql_injection",
        now=utc_now(),
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings/dashboard")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    guardrails = response.json()["guardrails"]
    assert guardrails["input_rejected_counts_by_pattern"] == {"sql_injection": 1}
    assert guardrails["output_redacted_count"] == 0


@pytest.mark.unit
def test_dashboard_endpoint_reports_tracing_status_with_phoenix_link(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings/dashboard")

    app.dependency_overrides.clear()

    tracing = response.json()["tracing"]
    assert tracing["process_actually_configured"] is False
    assert isinstance(tracing["db_desired_enabled"], bool)
    assert tracing["phoenix_ui_url"].startswith("http")
