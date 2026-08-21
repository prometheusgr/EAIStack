"""Unit tests for logout-triggered conversation cleanup - TDD discipline.

SECURITY.md's Option 1: when SESSION_CLEANUP_ON_LOGOUT is on, logging out
purges that user's conversation state. The endpoint must only ever be able
to purge the caller's own data.
"""

import pytest

from app.core.auth import get_current_user
from app.db.models import AuditLog, ConversationCheckpoint, ConversationThread, SystemSettings
from app.main import app

USER = {
    "user_id": "user-1",
    "username": "user1",
    "email": "user1@example.com",
    "name": "User One",
    "token": {"realm_access": {"roles": []}},
}


def _override_user(user: dict):
    def _override():
        return user

    return _override


def _add_thread(db, user_id: str) -> ConversationThread:
    thread = ConversationThread(user_id=user_id)
    db.add(thread)
    db.flush()
    db.add(ConversationCheckpoint(thread_id=thread.id, checkpoint=b"s", checkpoint_metadata=b"m"))
    db.flush()
    return thread


@pytest.mark.unit
def test_logout_purges_callers_conversations_when_enabled(client, db_session):
    thread_id = _add_thread(db_session, "user-1").id
    db_session.commit()

    app.dependency_overrides[get_current_user] = _override_user(USER)
    response = client.post("/api/auth/logout")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["purged_conversations"] == 1
    assert db_session.query(ConversationThread).filter_by(id=thread_id).first() is None


@pytest.mark.unit
def test_logout_never_purges_another_users_conversations(client, db_session):
    """Isolation: the endpoint derives user_id from the token, never the body."""
    mine_id = _add_thread(db_session, "user-1").id
    theirs_id = _add_thread(db_session, "user-2").id
    db_session.commit()

    app.dependency_overrides[get_current_user] = _override_user(USER)
    client.post("/api/auth/logout")
    app.dependency_overrides.clear()

    assert db_session.query(ConversationThread).filter_by(id=mine_id).first() is None
    assert db_session.query(ConversationThread).filter_by(id=theirs_id).first() is not None


@pytest.mark.unit
def test_logout_keeps_conversations_when_cleanup_is_disabled(client, db_session):
    """With cleanup_on_logout overridden off, logout leaves history intact."""
    db_session.add(SystemSettings(id="default", cleanup_on_logout=False, updated_by="admin-1"))
    thread = _add_thread(db_session, "user-1")
    db_session.commit()

    app.dependency_overrides[get_current_user] = _override_user(USER)
    response = client.post("/api/auth/logout")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["purged_conversations"] == 0
    assert db_session.query(ConversationThread).filter_by(id=thread.id).first() is not None


@pytest.mark.unit
def test_logout_requires_authentication(client):
    """No token, no purge - the endpoint must not be callable anonymously."""
    response = client.post("/api/auth/logout")

    assert response.status_code in (401, 403)


@pytest.mark.unit
def test_logout_never_deletes_audit_records(client, db_session):
    audit = AuditLog(
        actor_user_id="user-1",
        action="retention.update",
        field_name="conversation_retention_hours",
        old_value=None,
        new_value="24",
    )
    db_session.add(audit)
    _add_thread(db_session, "user-1")
    db_session.commit()

    app.dependency_overrides[get_current_user] = _override_user(USER)
    client.post("/api/auth/logout")
    app.dependency_overrides.clear()

    assert db_session.query(AuditLog).filter_by(id=audit.id).first() is not None
