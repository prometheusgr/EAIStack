"""Unit tests for AuditLog persistence and the append-only repository - TDD discipline.

AuditLog is the first audit record in the system. Its defining property is
that it is append-only from the application's point of view: nothing in
app code may update or delete a row, and no retention purge may ever
remove one (see docs/SECURITY.md - audit records are deliberately exempt
from session cleanup and retained on an independent schedule).
"""

from datetime import datetime, timezone

import pytest

from app.db.models import AuditLog
from app.repositories import AuditLogRepository

FIXED_NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_record_persists_who_changed_what_and_when(db_session):
    """A retention change must be attributable: actor, action, field, old/new values."""
    repo = AuditLogRepository(db_session)

    repo.record(
        actor_user_id="admin-1",
        action="retention.update",
        field_name="conversation_retention_hours",
        old_value="72",
        new_value="24",
        now=FIXED_NOW,
    )
    db_session.commit()

    entries = db_session.query(AuditLog).all()
    assert len(entries) == 1
    assert entries[0].actor_user_id == "admin-1"
    assert entries[0].action == "retention.update"
    assert entries[0].field_name == "conversation_retention_hours"
    assert entries[0].old_value == "72"
    assert entries[0].new_value == "24"
    assert entries[0].created_at == FIXED_NOW.replace(tzinfo=None)


@pytest.mark.unit
def test_record_stores_null_old_value_when_field_was_env_default(db_session):
    """Clearing/setting a field that had no DB override records old_value as NULL,
    distinguishing "was unset" from "was the string 'None'".
    """
    repo = AuditLogRepository(db_session)

    repo.record(
        actor_user_id="admin-1",
        action="retention.update",
        field_name="conversation_retention_hours",
        old_value=None,
        new_value="12",
        now=FIXED_NOW,
    )
    db_session.commit()

    entry = db_session.query(AuditLog).one()
    assert entry.old_value is None
    assert entry.new_value == "12"


@pytest.mark.unit
def test_record_appends_rather_than_overwriting(db_session):
    """Two changes to the same field produce two rows - history is never collapsed."""
    repo = AuditLogRepository(db_session)

    repo.record(
        actor_user_id="admin-1",
        action="retention.update",
        field_name="conversation_retention_hours",
        old_value=None,
        new_value="72",
        now=FIXED_NOW,
    )
    repo.record(
        actor_user_id="admin-2",
        action="retention.update",
        field_name="conversation_retention_hours",
        old_value="72",
        new_value="24",
        now=FIXED_NOW,
    )
    db_session.commit()

    entries = db_session.query(AuditLog).order_by(AuditLog.created_at).all()
    assert len(entries) == 2
    assert {e.actor_user_id for e in entries} == {"admin-1", "admin-2"}


@pytest.mark.unit
def test_repository_exposes_no_delete_or_update_method(db_session):
    """The repository must be structurally incapable of removing audit history.

    This is the code-level enforcement of SECURITY.md's "audit logs are NOT
    deleted" guarantee: there is no method to call, so no purge path can
    accidentally acquire one.
    """
    repo = AuditLogRepository(db_session)

    public_methods = {name for name in dir(repo) if not name.startswith("_")}

    assert public_methods == {"db", "record", "list_recent", "count_by_action_and_value_since"}


@pytest.mark.unit
def test_list_recent_returns_newest_first(db_session):
    """The audit trail is read newest-first, the order an admin reviewing it wants."""
    repo = AuditLogRepository(db_session)

    repo.record(
        actor_user_id="admin-1",
        action="retention.update",
        field_name="conversation_retention_hours",
        old_value=None,
        new_value="72",
        now=datetime(2026, 8, 20, 9, 0, 0, tzinfo=timezone.utc),
    )
    repo.record(
        actor_user_id="admin-2",
        action="retention.update",
        field_name="api_key_purge_days",
        old_value=None,
        new_value="30",
        now=datetime(2026, 8, 21, 9, 0, 0, tzinfo=timezone.utc),
    )
    db_session.commit()

    entries = repo.list_recent(limit=10)

    assert [e.field_name for e in entries] == [
        "api_key_purge_days",
        "conversation_retention_hours",
    ]


@pytest.mark.unit
def test_count_by_action_and_value_since_groups_and_counts_matching_action(db_session):
    """Issue #48's dashboard needs per-pattern trip counts for
    guardrail.input_rejected, grouped by new_value (the pattern/reason that
    tripped, per chat_guardrail_service.check_input_guardrail). Unrelated
    actions must not pollute the count -- list_recent(limit=100) can't
    guarantee this once other audit-event types are mixed in, which is why
    this is a dedicated, action-filtered query rather than client-side
    aggregation over list_recent.
    """
    repo = AuditLogRepository(db_session)
    since = datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc)

    repo.record(
        actor_user_id="user-1",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="sql_injection",
        now=datetime(2026, 8, 21, 9, 0, 0, tzinfo=timezone.utc),
    )
    repo.record(
        actor_user_id="user-2",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="sql_injection",
        now=datetime(2026, 8, 21, 10, 0, 0, tzinfo=timezone.utc),
    )
    repo.record(
        actor_user_id="user-3",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="instruction_override",
        now=datetime(2026, 8, 21, 11, 0, 0, tzinfo=timezone.utc),
    )
    # A different action entirely -- must not be counted or grouped in.
    repo.record(
        actor_user_id="admin-1",
        action="retention.update",
        field_name="conversation_retention_hours",
        old_value="72",
        new_value="24",
        now=datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc),
    )
    db_session.commit()

    counts = repo.count_by_action_and_value_since("guardrail.input_rejected", since=since)

    assert counts == {"sql_injection": 2, "instruction_override": 1}


@pytest.mark.unit
def test_count_by_action_and_value_since_excludes_entries_before_the_cutoff(db_session):
    repo = AuditLogRepository(db_session)
    since = datetime(2026, 8, 21, 0, 0, 0, tzinfo=timezone.utc)

    repo.record(
        actor_user_id="user-1",
        action="guardrail.input_rejected",
        field_name="message",
        old_value=None,
        new_value="sql_injection",
        now=datetime(2026, 8, 20, 23, 59, 59, tzinfo=timezone.utc),
    )
    db_session.commit()

    counts = repo.count_by_action_and_value_since("guardrail.input_rejected", since=since)

    assert counts == {}
