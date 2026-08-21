"""Unit tests for the admin-only retention settings on /api/settings - TDD discipline."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.auth import get_current_user
from app.db.models import AuditLog, ConversationCheckpoint, ConversationThread
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
def test_get_settings_reports_retention_env_defaults(client):
    """Retention fields follow the same resolved-value + is_db_override shape
    as the existing provider fields.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.get("/api/settings")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_retention_hours"] == 24
    assert data["conversation_retention_hours_is_db_override"] is False
    assert data["cleanup_on_logout"] is True
    assert data["cleanup_on_logout_is_db_override"] is False
    assert data["knowledge_base_purge_days"] == 30
    assert data["api_key_purge_days"] == 30


@pytest.mark.unit
def test_admin_can_override_conversation_retention(client, db_session):
    """The core requirement: an admin changes retention and it takes effect
    immediately, with no backend restart.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"conversation_retention_hours": 72})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_retention_hours"] == 72
    assert data["conversation_retention_hours_is_db_override"] is True


@pytest.mark.unit
def test_non_admin_cannot_change_retention(client):
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.put("/api/settings", json={"conversation_retention_hours": 1})

    app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.unit
def test_retention_change_is_recorded_in_the_audit_log(client, db_session):
    """Safety requirement: every retention change records who, when, old and new."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"conversation_retention_hours": 72})

    app.dependency_overrides.clear()

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.field_name == "conversation_retention_hours")
        .one()
    )
    assert entry.actor_user_id == "admin-user-1"
    assert entry.action == "retention.update"
    assert entry.old_value is None
    assert entry.new_value == "72"


@pytest.mark.unit
def test_shortening_retention_records_old_and_new_values(client, db_session):
    """The old value must be captured before the write, so the trail shows the
    actual transition (72 -> 24), not just the final state.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"conversation_retention_hours": 72})
    client.put("/api/settings", json={"conversation_retention_hours": 24})

    app.dependency_overrides.clear()

    entries = (
        db_session.query(AuditLog)
        .filter(AuditLog.field_name == "conversation_retention_hours")
        .order_by(AuditLog.created_at)
        .all()
    )
    assert [(e.old_value, e.new_value) for e in entries] == [(None, "72"), ("72", "24")]


@pytest.mark.unit
def test_unchanged_retention_field_produces_no_audit_record(client, db_session):
    """Saving the settings form without touching retention must not fabricate
    an audit record - the trail records changes, not saves.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"conversation_retention_hours": 72})
    client.put("/api/settings", json={"conversation_retention_hours": 72})

    app.dependency_overrides.clear()

    entries = (
        db_session.query(AuditLog)
        .filter(AuditLog.field_name == "conversation_retention_hours")
        .all()
    )
    assert len(entries) == 1


@pytest.mark.unit
def test_provider_only_change_still_records_no_retention_audit(client, db_session):
    """Changing an LLM provider is not a retention change."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"llm_provider": "fake"})

    app.dependency_overrides.clear()

    assert db_session.query(AuditLog).count() == 0


@pytest.mark.unit
def test_negative_retention_is_rejected(client):
    """A negative window is meaningless and would purge everything; reject it
    at the boundary rather than storing it.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    response = client.put("/api/settings", json={"conversation_retention_hours": -1})

    app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.unit
def test_clearing_retention_override_falls_back_to_env_default(client):
    """Omitting the field clears back to the env default, matching the
    nullable-column semantics the provider fields already use.
    """
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"conversation_retention_hours": 72})
    response = client.put("/api/settings", json={})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_retention_hours"] == 24
    assert data["conversation_retention_hours_is_db_override"] is False


@pytest.mark.unit
def test_new_retention_setting_takes_effect_without_restart(client, db_session):
    """End-to-end proof of the no-restart requirement: after the admin shortens
    the window, a sweep resolving config from the DB purges accordingly.
    """
    from app.services.retention_service import run_retention_sweep

    now = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    stale = now - timedelta(hours=5)
    thread = ConversationThread(
        user_id="user-1",
        created_at=stale.replace(tzinfo=None),
        updated_at=stale.replace(tzinfo=None),
    )
    db_session.add(thread)
    db_session.flush()
    db_session.add(
        ConversationCheckpoint(thread_id=thread.id, checkpoint=b"s", checkpoint_metadata=b"m")
    )
    db_session.commit()
    thread_id = thread.id

    # Under the 24h env default this thread is still inside the window.
    run_retention_sweep(db_session, now=now)
    db_session.commit()
    assert db_session.query(ConversationThread).filter_by(id=thread_id).first() is not None

    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)
    client.put("/api/settings", json={"conversation_retention_hours": 1})
    app.dependency_overrides.clear()

    run_retention_sweep(db_session, now=now)
    db_session.commit()

    assert db_session.query(ConversationThread).filter_by(id=thread_id).first() is None


@pytest.mark.unit
def test_audit_log_endpoint_returns_retention_history_to_admin(client, db_session):
    """An admin can read the audit trail - otherwise recording it is pointless."""
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    client.put("/api/settings", json={"conversation_retention_hours": 72})
    response = client.get("/api/settings/audit")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["field_name"] == "conversation_retention_hours"
    assert entries[0]["new_value"] == "72"
    assert entries[0]["actor_user_id"] == "admin-user-1"


@pytest.mark.unit
def test_audit_log_endpoint_is_admin_only(client):
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings/audit")

    app.dependency_overrides.clear()

    assert response.status_code == 403
