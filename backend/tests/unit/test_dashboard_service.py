"""Unit tests for the admin dashboard's aggregation service - TDD discipline.

Covers issue #48: a single admin-only screen showing rate-limit bucket
state, guardrail trip counts, and tracing status, each backed by a real data
path (no mocked/placeholder tiles) -- see resolve_dashboard_status's
docstring for how each tile's data source was chosen.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.core.tracing import configure_tracing
from app.repositories import AuditLogRepository
from app.services.dashboard_service import resolve_dashboard_status
from app.services.rate_limiter_service import reset_rate_limit_state

FIXED_NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _reset_shared_state():
    """Both rate-limit bucket state and tracing's module-level configured
    flag are process-global, so tests must not leak into each other -- same
    fixtures test_rate_limiter_service.py and test_tracing.py already use
    individually; this module exercises both through one service.
    """
    reset_rate_limit_state()
    import app.core.tracing as tracing_module

    tracing_module._configured = False
    yield
    reset_rate_limit_state()
    tracing_module._configured = False


@pytest.mark.unit
def test_resolve_dashboard_status_reports_zero_active_buckets_when_none_tracked(db_session):
    status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.rate_limit.active_bucket_count == 0


@pytest.mark.unit
def test_resolve_dashboard_status_reports_rate_limit_enabled_state(db_session):
    status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.rate_limit.enabled == settings.rate_limit_enabled


@pytest.mark.unit
def test_resolve_dashboard_status_counts_guardrail_trips_by_pattern_in_the_recent_window(
    db_session,
):
    repo = AuditLogRepository(db_session)
    repo.record(
        actor_user_id="user-1",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="sql_injection",
        now=FIXED_NOW - timedelta(hours=1),
    )
    repo.record(
        actor_user_id="user-2",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="sql_injection",
        now=FIXED_NOW - timedelta(hours=2),
    )
    repo.record(
        actor_user_id="user-3",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="instruction_override",
        now=FIXED_NOW - timedelta(minutes=30),
    )
    db_session.commit()

    status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.guardrails.input_rejected_counts_by_pattern == {
        "sql_injection": 2,
        "instruction_override": 1,
    }


@pytest.mark.unit
def test_resolve_dashboard_status_excludes_guardrail_trips_outside_the_recent_window(db_session):
    repo = AuditLogRepository(db_session)
    repo.record(
        actor_user_id="user-1",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="sql_injection",
        now=FIXED_NOW - timedelta(days=2),
    )
    db_session.commit()

    status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.guardrails.input_rejected_counts_by_pattern == {}


@pytest.mark.unit
def test_resolve_dashboard_status_counts_output_redactions_in_the_recent_window(db_session):
    repo = AuditLogRepository(db_session)
    repo.record(
        actor_user_id="user-1",
        action="guardrail.output_redacted",
        field_name="response",
        old_value=None,
        new_value="thread-1",
        now=FIXED_NOW - timedelta(hours=1),
    )
    db_session.commit()

    status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.guardrails.output_redacted_count == 1


@pytest.mark.unit
def test_resolve_dashboard_status_tracing_reflects_db_desired_and_process_actual_state(
    db_session,
):
    """The two are independent axes and can diverge -- an admin's DB
    override takes effect only after the next backend restart (see
    app.core.tracing.configure_tracing's docstring). Neither value is
    derived from the other.
    """
    status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.tracing.db_desired_enabled == settings.tracing_enabled
    assert status.tracing.process_actually_configured is False

    with (
        patch("phoenix.otel.register", return_value=MagicMock()),
        patch("openinference.instrumentation.langchain.LangChainInstrumentor"),
    ):
        configure_tracing(settings, enabled=True)

    status_after = resolve_dashboard_status(db_session, now=FIXED_NOW)
    assert status_after.tracing.process_actually_configured is True


@pytest.mark.unit
def test_resolve_dashboard_status_includes_the_phoenix_ui_url(db_session):
    status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.tracing.phoenix_ui_url == settings.tracing_ui_url


@pytest.mark.unit
def test_resolve_dashboard_status_keycloak_console_url_falls_back_to_keycloak_url(db_session):
    """No override configured -- issue #40's User Management nav link should
    still resolve to something an admin's browser can load, not blank."""
    with patch.object(settings, "keycloak_console_url", None):
        status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.keycloak_console_url == settings.keycloak_url


@pytest.mark.unit
def test_resolve_dashboard_status_keycloak_console_url_uses_override_when_set(db_session):
    with patch.object(settings, "keycloak_console_url", "https://keycloak.example.com"):
        status = resolve_dashboard_status(db_session, now=FIXED_NOW)

    assert status.keycloak_console_url == "https://keycloak.example.com"
