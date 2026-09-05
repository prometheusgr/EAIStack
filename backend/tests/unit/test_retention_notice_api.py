"""Unit tests for GET /api/settings/retention-notice (issue #49) - TDD discipline.

Retention windows were already fully admin-configurable via
app.services.retention_service, but no ordinary (non-admin) user of the chat
UI had any way to see how long their own data is kept - that visibility was
previously admin-only, via GET /api/settings. This endpoint exposes the same
*resolved* (not raw DB-nullable) values to any authenticated user, plus
whether the fork wants the notice shown at all.
"""

import pytest

from app.core.auth import get_current_user
from app.db.models import SystemSettings
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
def test_non_admin_user_can_read_retention_notice(client):
    """The core requirement: an ordinary chat user (not just an admin) can
    read the effective retention policy - this was previously reachable
    only via the admin-gated GET /api/settings.
    """
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings/retention-notice")

    app.dependency_overrides.clear()

    assert response.status_code == 200


@pytest.mark.unit
def test_retention_notice_reports_env_defaults_when_no_override(client):
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings/retention-notice")

    app.dependency_overrides.clear()

    data = response.json()
    assert data["conversation_retention_hours"] == 24
    assert data["cleanup_on_logout"] is True
    assert data["notice_enabled"] is True


@pytest.mark.unit
def test_retention_notice_reflects_admin_db_override(client, db_session):
    """The effective (resolved) value, not the raw admin-editable default -
    if an admin has shortened the window, a chat user must see the real
    number, not the env default.
    """
    db_session.add(
        SystemSettings(id="default", conversation_retention_hours=2, updated_by="admin-1")
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings/retention-notice")

    app.dependency_overrides.clear()

    assert response.json()["conversation_retention_hours"] == 2


@pytest.mark.unit
def test_retention_notice_reports_keep_forever_as_null(client, db_session, monkeypatch):
    """None ("keep forever") must round-trip as JSON null, not be coerced
    into a truthy/falsy number that would misrepresent the policy.

    A DB row value of None means "no override" (falls back to the env
    default), per AGENTS.md's Retention Field Semantics -- so "keep
    forever" is exercised here via the env default itself being None, the
    same way it's genuinely reached in a real deployment that sets
    SESSION_TTL_HOURS unset.
    """
    from app.core.config import settings as env_settings

    monkeypatch.setattr(env_settings, "session_ttl_hours", None)

    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings/retention-notice")

    app.dependency_overrides.clear()

    assert response.json()["conversation_retention_hours"] is None


@pytest.mark.unit
def test_retention_notice_can_be_disabled_by_admin_config(client, db_session):
    """A fork can turn the notice off entirely (e.g. retention is "keep
    forever" everywhere and the notice would be uninteresting) - the
    default stays on (see the env-default test above), but an explicit
    override must be honored.
    """
    db_session.add(
        SystemSettings(id="default", retention_notice_enabled=False, updated_by="admin-1")
    )
    db_session.commit()

    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings/retention-notice")

    app.dependency_overrides.clear()

    assert response.json()["notice_enabled"] is False


@pytest.mark.unit
def test_unauthenticated_request_is_rejected(client):
    """No dependency override -- the real get_current_user dependency must
    still require a token; this endpoint is authenticated, just not
    admin-gated.
    """
    response = client.get("/api/settings/retention-notice")

    assert response.status_code in (401, 403)


@pytest.mark.unit
def test_admin_can_set_retention_notice_enabled_via_update_settings(client):
    """The admin-configurable on/off switch lives on the same PUT
    /api/settings the rest of the retention config uses, matching every
    other *_enabled toggle's pattern (guardrails, tracing, rate limiting,
    audit log UI).
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"retention_notice_enabled": False})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["retention_notice_enabled"] is False
    assert data["retention_notice_enabled_is_db_override"] is True


@pytest.mark.unit
def test_retention_notice_config_change_is_audit_logged(client, db_session):
    from app.db.models import AuditLog

    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"retention_notice_enabled": False})

    app.dependency_overrides.clear()

    entry = (
        db_session.query(AuditLog).filter(AuditLog.field_name == "retention_notice_enabled").one()
    )
    assert entry.action == "retention_notice.config_update"
    assert entry.old_value is None
    assert entry.new_value == "False"
