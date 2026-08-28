"""Unit tests for retention config resolution and purge enforcement - TDD discipline.

Time is injected as an explicit `now` argument throughout: no datetime
patching, so these tests are deterministic without mocking anything that
isn't a real boundary (per AGENTS.md).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import (
    APIKey,
    AuditLog,
    ConversationCheckpoint,
    ConversationThread,
    Embedding,
    KnowledgeBase,
    SystemSettings,
)
from app.services.retention_service import (
    purge_expired_api_keys,
    purge_expired_conversations,
    purge_expired_knowledge_base,
    purge_user_conversations,
    resolve_retention_config,
    run_retention_sweep,
)

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


def _naive(moment: datetime) -> datetime:
    """Strip tzinfo to match how DateTime columns round-trip in this schema."""
    return moment.replace(tzinfo=None)


def _make_thread(db, user_id: str, updated_at: datetime) -> ConversationThread:
    thread = ConversationThread(
        user_id=user_id, created_at=_naive(updated_at), updated_at=_naive(updated_at)
    )
    db.add(thread)
    db.flush()
    db.add(
        ConversationCheckpoint(
            thread_id=thread.id,
            checkpoint=b"state",
            checkpoint_metadata=b"meta",
            created_at=_naive(updated_at),
            updated_at=_naive(updated_at),
        )
    )
    db.flush()
    return thread


def _make_audit_entry(db) -> AuditLog:
    entry = AuditLog(
        actor_user_id="admin-1",
        action="retention.update",
        field_name="conversation_retention_hours",
        old_value=None,
        new_value="24",
        created_at=_naive(NOW - timedelta(days=3650)),
    )
    db.add(entry)
    db.flush()
    return entry


# --- Config resolution (DB override over env default) ------------------------


@pytest.mark.unit
def test_resolve_retention_falls_back_to_env_defaults_when_no_db_row(db_session):
    """With no SystemSettings row, retention comes from env-level config."""
    config = resolve_retention_config(db_session)

    assert config.conversation_retention_hours == 24
    assert config.cleanup_on_logout is True


@pytest.mark.unit
def test_resolve_retention_prefers_db_override(db_session):
    """A DB override wins over the env default - the no-restart mechanism."""
    db_session.add(
        SystemSettings(id="default", conversation_retention_hours=72, updated_by="admin-1")
    )
    db_session.commit()

    config = resolve_retention_config(db_session)

    assert config.conversation_retention_hours == 72


@pytest.mark.unit
def test_resolve_retention_zero_override_is_honoured_not_treated_as_unset(db_session):
    """0 is a meaningful override (purge immediately), not a falsy "not set".

    Guards the same trap as _resolve_field's `is not None` check in
    system_settings_service: a truthiness test would silently discard this.
    """
    db_session.add(
        SystemSettings(id="default", conversation_retention_hours=0, updated_by="admin-1")
    )
    db_session.commit()

    config = resolve_retention_config(db_session)

    assert config.conversation_retention_hours == 0


# --- TTL sweep: conversations ------------------------------------------------


@pytest.mark.unit
def test_conversation_inside_retention_window_survives(db_session):
    """Data inside the window must not be touched."""
    thread = _make_thread(db_session, "user-1", NOW - timedelta(hours=23))
    db_session.commit()

    purge_expired_conversations(db_session, retention_hours=24, now=NOW)
    db_session.commit()

    assert db_session.query(ConversationThread).filter_by(id=thread.id).first() is not None


@pytest.mark.unit
def test_conversation_outside_retention_window_is_purged(db_session):
    """Data past the window is deleted, along with its checkpoint."""
    thread_id = _make_thread(db_session, "user-1", NOW - timedelta(hours=25)).id
    db_session.commit()

    purged = purge_expired_conversations(db_session, retention_hours=24, now=NOW)
    db_session.commit()

    assert purged == 1
    assert db_session.query(ConversationThread).filter_by(id=thread_id).first() is None
    assert db_session.query(ConversationCheckpoint).filter_by(thread_id=thread_id).first() is None


@pytest.mark.unit
def test_conversation_exactly_at_cutoff_survives(db_session):
    """The boundary is exclusive: exactly-at-the-cutoff data is still inside the window."""
    thread = _make_thread(db_session, "user-1", NOW - timedelta(hours=24))
    db_session.commit()

    purge_expired_conversations(db_session, retention_hours=24, now=NOW)
    db_session.commit()

    assert db_session.query(ConversationThread).filter_by(id=thread.id).first() is not None


@pytest.mark.unit
def test_conversation_purge_is_disabled_when_retention_is_none(db_session):
    """retention_hours=None means "keep forever" - nothing is purged, however old."""
    thread = _make_thread(db_session, "user-1", NOW - timedelta(days=365))
    db_session.commit()

    purged = purge_expired_conversations(db_session, retention_hours=None, now=NOW)
    db_session.commit()

    assert purged == 0
    assert db_session.query(ConversationThread).filter_by(id=thread.id).first() is not None


@pytest.mark.unit
def test_conversation_purge_batches_rather_than_one_unbounded_delete(db_session):
    """Purges must be batched (safety requirement), and still delete everything expired."""
    for _ in range(5):
        _make_thread(db_session, "user-1", NOW - timedelta(hours=48))
    db_session.commit()

    purged = purge_expired_conversations(db_session, retention_hours=24, now=NOW, batch_size=2)
    db_session.commit()

    assert purged == 5
    assert db_session.query(ConversationThread).count() == 0


@pytest.mark.unit
def test_conversation_purge_spans_users(db_session):
    """The TTL sweep is system-wide, not scoped to one user."""
    _make_thread(db_session, "user-1", NOW - timedelta(hours=48))
    _make_thread(db_session, "user-2", NOW - timedelta(hours=48))
    fresh = _make_thread(db_session, "user-3", NOW - timedelta(hours=1))
    db_session.commit()

    purged = purge_expired_conversations(db_session, retention_hours=24, now=NOW)
    db_session.commit()

    assert purged == 2
    assert db_session.query(ConversationThread).one().id == fresh.id


# --- Logout-triggered purge --------------------------------------------------


@pytest.mark.unit
def test_logout_purge_deletes_only_that_users_conversations(db_session):
    """Logout cleanup must never reach another user's data."""
    mine_id = _make_thread(db_session, "user-1", NOW - timedelta(hours=1)).id
    theirs_id = _make_thread(db_session, "user-2", NOW - timedelta(hours=1)).id
    db_session.commit()

    purged = purge_user_conversations(db_session, user_id="user-1")
    db_session.commit()

    assert purged == 1
    assert db_session.query(ConversationThread).filter_by(id=mine_id).first() is None
    assert db_session.query(ConversationThread).filter_by(id=theirs_id).first() is not None


@pytest.mark.unit
def test_logout_purge_removes_checkpoints_too(db_session):
    """Deleting a thread must not orphan its checkpoint state."""
    thread_id = _make_thread(db_session, "user-1", NOW - timedelta(hours=1)).id
    db_session.commit()

    purge_user_conversations(db_session, user_id="user-1")
    db_session.commit()

    assert db_session.query(ConversationCheckpoint).filter_by(thread_id=thread_id).first() is None


# --- Purge windows: knowledge base / embeddings ------------------------------


@pytest.mark.unit
def test_soft_deleted_document_inside_purge_window_survives(db_session):
    """A recently soft-deleted doc is still recoverable inside its window."""
    doc = KnowledgeBase(
        user_id="user-1",
        title="Doc",
        content="Body",
        deleted_at=_naive(NOW - timedelta(days=29)),
    )
    db_session.add(doc)
    db_session.commit()

    purge_expired_knowledge_base(db_session, purge_after_days=30, now=NOW)
    db_session.commit()

    assert db_session.query(KnowledgeBase).filter_by(id=doc.id).first() is not None


@pytest.mark.unit
def test_soft_deleted_document_outside_purge_window_is_hard_deleted(db_session):
    """Past its window, a soft-deleted doc is really removed."""
    doc = KnowledgeBase(
        user_id="user-1",
        title="Doc",
        content="Body",
        deleted_at=_naive(NOW - timedelta(days=31)),
    )
    db_session.add(doc)
    db_session.commit()
    doc_id = doc.id

    purged = purge_expired_knowledge_base(db_session, purge_after_days=30, now=NOW)
    db_session.commit()

    assert purged == 1
    assert db_session.query(KnowledgeBase).filter_by(id=doc_id).first() is None


@pytest.mark.unit
def test_purging_a_document_also_purges_its_embeddings(db_session):
    """Embeddings follow their parent document - no orphaned vectors."""
    doc = KnowledgeBase(
        user_id="user-1",
        title="Doc",
        content="Body",
        deleted_at=_naive(NOW - timedelta(days=31)),
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(Embedding(doc_id=doc.id, embedding=[0.1] * 768))
    db_session.commit()
    doc_id = doc.id

    purge_expired_knowledge_base(db_session, purge_after_days=30, now=NOW)
    db_session.commit()

    assert db_session.query(Embedding).filter_by(doc_id=doc_id).first() is None


@pytest.mark.unit
def test_purging_a_file_backed_document_deletes_its_minio_object(db_session):
    """Test: purging a soft-deleted, file-backed document also deletes its
    MinIO object - the part issue #13 calls out as most likely to be
    missed. If the object survives, it is now an orphan no retention
    policy covers, which is a silent data-retention violation.
    """
    from unittest.mock import MagicMock

    doc = KnowledgeBase(
        user_id="user-1",
        title="spec.pdf",
        content="Extracted text",
        storage_key="user-1/doc-1/spec.pdf",
        original_filename="spec.pdf",
        content_type="application/pdf",
        deleted_at=_naive(NOW - timedelta(days=31)),
    )
    db_session.add(doc)
    db_session.commit()

    document_store = MagicMock()
    purged = purge_expired_knowledge_base(
        db_session, purge_after_days=30, now=NOW, document_store=document_store
    )
    db_session.commit()

    assert purged == 1
    document_store.delete_many.assert_called_once_with(["user-1/doc-1/spec.pdf"])


@pytest.mark.unit
def test_minio_delete_is_not_left_dangling_by_a_downstream_sweep_failure(db_session):
    """Test: the irreversible MinIO delete must not happen until the DB-side
    deletion for that same batch is already flushed and durable within the
    transaction. A retention sweep runs every purge under one transaction
    (see app.cli.retention_sweep.main, which commits once at the end) - if
    a later step in the same sweep fails and the caller rolls back, a
    KnowledgeBase row whose MinIO object was already deleted would be
    "resurrected" by the rollback while its object is gone forever: a
    permanently orphaned, undetectable dangling reference.
    Ordering the DB delete (flushed) before the MinIO delete closes this:
    if the DB side were going to fail (e.g. a constraint violation), it
    surfaces before the irreversible object delete ever happens. This test
    asserts that ordering directly by recording each side's call order,
    rather than only asserting the happy-path end state.
    """
    from unittest.mock import MagicMock

    doc = KnowledgeBase(
        user_id="user-1",
        title="spec.pdf",
        content="Extracted text",
        storage_key="user-1/doc-1/spec.pdf",
        original_filename="spec.pdf",
        content_type="application/pdf",
        deleted_at=_naive(NOW - timedelta(days=31)),
    )
    db_session.add(doc)
    db_session.commit()
    doc_id = doc.id

    call_order: list[str] = []

    def _record_db_state_at_minio_delete(storage_keys):
        # At the moment the irreversible MinIO delete fires, the KnowledgeBase
        # row it corresponds to must already be gone from the session (flushed),
        # so a query issued right now proves the DB side is already committed
        # to deleting it - not merely scheduled to delete it later.
        call_order.append("minio_delete")
        still_present = db_session.query(KnowledgeBase).filter_by(id=doc_id).first()
        assert still_present is None, (
            "MinIO object deleted before the corresponding DB row was flushed - "
            "a downstream rollback would resurrect a row pointing at a deleted object"
        )

    document_store = MagicMock()
    document_store.delete_many.side_effect = _record_db_state_at_minio_delete

    purge_expired_knowledge_base(
        db_session, purge_after_days=30, now=NOW, document_store=document_store
    )

    assert call_order == ["minio_delete"]


@pytest.mark.unit
def test_purging_typed_entries_does_not_call_document_store(db_session):
    """Test: a pasted-text (non-file-backed) document has no storage_key, so
    purging it must not call the document store with a None key.
    """
    from unittest.mock import MagicMock

    doc = KnowledgeBase(
        user_id="user-1",
        title="Typed note",
        content="Just typed text",
        deleted_at=_naive(NOW - timedelta(days=31)),
    )
    db_session.add(doc)
    db_session.commit()

    document_store = MagicMock()
    purge_expired_knowledge_base(
        db_session, purge_after_days=30, now=NOW, document_store=document_store
    )
    db_session.commit()

    document_store.delete_many.assert_called_once_with([])


@pytest.mark.unit
def test_purge_knowledge_base_without_document_store_still_purges_db_rows(db_session):
    """Test: document_store is optional - callers that don't care about
    object storage (or don't have one configured) still get the DB-row
    purge behavior unchanged.
    """
    doc = KnowledgeBase(
        user_id="user-1",
        title="Doc",
        content="Body",
        deleted_at=_naive(NOW - timedelta(days=31)),
    )
    db_session.add(doc)
    db_session.commit()
    doc_id = doc.id

    purged = purge_expired_knowledge_base(db_session, purge_after_days=30, now=NOW)
    db_session.commit()

    assert purged == 1
    assert db_session.query(KnowledgeBase).filter_by(id=doc_id).first() is None


@pytest.mark.unit
def test_live_document_is_never_purged_however_old(db_session):
    """Only soft-deleted docs are eligible; a live doc has no purge window."""
    doc = KnowledgeBase(
        user_id="user-1",
        title="Doc",
        content="Body",
        created_at=_naive(NOW - timedelta(days=3650)),
        deleted_at=None,
    )
    db_session.add(doc)
    db_session.commit()

    purged = purge_expired_knowledge_base(db_session, purge_after_days=30, now=NOW)
    db_session.commit()

    assert purged == 0
    assert db_session.query(KnowledgeBase).filter_by(id=doc.id).first() is not None


# --- Purge windows: revoked API keys -----------------------------------------


@pytest.mark.unit
def test_revoked_api_key_inside_purge_window_survives(db_session):
    key = APIKey(
        user_id="user-1",
        name="k",
        provider="openai",
        secret_value="s",
        revoked_at=_naive(NOW - timedelta(days=29)),
    )
    db_session.add(key)
    db_session.commit()

    purge_expired_api_keys(db_session, purge_after_days=30, now=NOW)
    db_session.commit()

    assert db_session.query(APIKey).filter_by(id=key.id).first() is not None


@pytest.mark.unit
def test_revoked_api_key_outside_purge_window_is_deleted(db_session):
    key = APIKey(
        user_id="user-1",
        name="k",
        provider="openai",
        secret_value="s",
        revoked_at=_naive(NOW - timedelta(days=31)),
    )
    db_session.add(key)
    db_session.commit()
    key_id = key.id

    purged = purge_expired_api_keys(db_session, purge_after_days=30, now=NOW)
    db_session.commit()

    assert purged == 1
    assert db_session.query(APIKey).filter_by(id=key_id).first() is None


@pytest.mark.unit
def test_active_api_key_is_never_purged(db_session):
    """An un-revoked key has no purge window, however old it is."""
    key = APIKey(
        user_id="user-1",
        name="k",
        provider="openai",
        secret_value="s",
        created_at=_naive(NOW - timedelta(days=3650)),
        revoked_at=None,
    )
    db_session.add(key)
    db_session.commit()

    purged = purge_expired_api_keys(db_session, purge_after_days=30, now=NOW)
    db_session.commit()

    assert purged == 0
    assert db_session.query(APIKey).filter_by(id=key.id).first() is not None


# --- Audit records are exempt from every purge path --------------------------


@pytest.mark.unit
def test_conversation_ttl_sweep_never_deletes_audit_records(db_session):
    audit = _make_audit_entry(db_session)
    _make_thread(db_session, "user-1", NOW - timedelta(days=365))
    db_session.commit()

    purge_expired_conversations(db_session, retention_hours=1, now=NOW)
    db_session.commit()

    assert db_session.query(AuditLog).filter_by(id=audit.id).first() is not None


@pytest.mark.unit
def test_logout_purge_never_deletes_audit_records(db_session):
    audit = _make_audit_entry(db_session)
    _make_thread(db_session, "user-1", NOW - timedelta(hours=1))
    db_session.commit()

    purge_user_conversations(db_session, user_id="admin-1")
    purge_user_conversations(db_session, user_id="user-1")
    db_session.commit()

    assert db_session.query(AuditLog).filter_by(id=audit.id).first() is not None


@pytest.mark.unit
def test_knowledge_base_purge_never_deletes_audit_records(db_session):
    audit = _make_audit_entry(db_session)
    db_session.commit()

    purge_expired_knowledge_base(db_session, purge_after_days=0, now=NOW)
    db_session.commit()

    assert db_session.query(AuditLog).filter_by(id=audit.id).first() is not None


@pytest.mark.unit
def test_api_key_purge_never_deletes_audit_records(db_session):
    audit = _make_audit_entry(db_session)
    db_session.commit()

    purge_expired_api_keys(db_session, purge_after_days=0, now=NOW)
    db_session.commit()

    assert db_session.query(AuditLog).filter_by(id=audit.id).first() is not None


@pytest.mark.unit
def test_full_sweep_with_most_aggressive_settings_never_deletes_audit_records(db_session):
    """The strongest end-to-end statement of the exemption: every purge path
    runs at its most aggressive setting and audit history is still intact.
    """
    audit = _make_audit_entry(db_session)
    _make_thread(db_session, "user-1", NOW - timedelta(days=365))
    doc = KnowledgeBase(
        user_id="user-1",
        title="Doc",
        content="Body",
        deleted_at=_naive(NOW - timedelta(days=365)),
    )
    db_session.add(doc)
    db_session.add(
        APIKey(
            user_id="user-1",
            name="k",
            provider="openai",
            secret_value="s",
            revoked_at=_naive(NOW - timedelta(days=365)),
        )
    )
    db_session.commit()

    run_retention_sweep(db_session, now=NOW)
    db_session.commit()

    assert db_session.query(ConversationThread).count() == 0
    assert db_session.query(KnowledgeBase).count() == 0
    assert db_session.query(APIKey).count() == 0
    assert db_session.query(AuditLog).filter_by(id=audit.id).first() is not None


@pytest.mark.unit
def test_full_sweep_forwards_document_store_to_knowledge_base_purge(db_session):
    """Test: run_retention_sweep() passes its document_store through to the
    knowledge-base purge, so the CronJob entrypoint's object deletion isn't
    silently dropped by the top-level orchestrator.
    """
    from unittest.mock import MagicMock

    doc = KnowledgeBase(
        user_id="user-1",
        title="spec.pdf",
        content="Extracted text",
        storage_key="user-1/doc-1/spec.pdf",
        deleted_at=_naive(NOW - timedelta(days=365)),
    )
    db_session.add(doc)
    db_session.commit()

    document_store = MagicMock()
    run_retention_sweep(db_session, now=NOW, document_store=document_store)
    db_session.commit()

    document_store.delete_many.assert_called_once_with(["user-1/doc-1/spec.pdf"])


@pytest.mark.unit
def test_sweep_reports_what_it_purged_per_store(db_session):
    """The sweep is logged/observable: it reports counts per store rather than
    silently deleting (safety requirement: purges must be logged).
    """
    _make_thread(db_session, "user-1", NOW - timedelta(days=365))
    db_session.add(
        KnowledgeBase(
            user_id="user-1",
            title="Doc",
            content="Body",
            deleted_at=_naive(NOW - timedelta(days=365)),
        )
    )
    db_session.commit()

    result = run_retention_sweep(db_session, now=NOW)
    db_session.commit()

    assert result["conversations"] == 1
    assert result["knowledge_base"] == 1
    assert result["api_keys"] == 0
