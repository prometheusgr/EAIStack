"""Data-retention config resolution and purge enforcement.

Resolves the effective retention policy the same way
system_settings_service resolves provider config - DB override over env
default, read fresh on every call - so an admin's change takes effect on
the next sweep without a backend restart.

Every purge function here takes `now` explicitly rather than reading the
clock. That keeps the time-dependent logic deterministic under test
without patching datetime globally, and lets one sweep stamp all its
cutoffs from a single consistent instant.

Audit records are exempt from every path in this module: no function here
queries or deletes AuditLog, and AuditLogRepository exposes no delete
method. See docs/SECURITY.md's retention policy table.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    APIKey,
    ConversationCheckpoint,
    ConversationThread,
    Embedding,
    KnowledgeBase,
    SystemSettings,
)
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.config_resolution import resolve_field
from app.services.system_settings_service import NOT_PROVIDED, NotProvided

if TYPE_CHECKING:
    from app.storage.document_store import DocumentStore

logger = logging.getLogger(__name__)


# Rows deleted per round-trip. Purges must be batched rather than issued as
# one unbounded DELETE: an air-gapped deployment that has accumulated months
# of conversations would otherwise hold a single long transaction and lock
# rows for the duration of the sweep.
DEFAULT_BATCH_SIZE = 500


@dataclass(frozen=True)
class RetentionConfig:
    """Effective retention policy, DB override merged over env defaults.

    An hours/days value of None means "keep forever"; 0 means "purge
    immediately". Both are meaningful, which is why resolution must test
    `is not None` rather than truthiness.
    """

    conversation_retention_hours: int | None
    cleanup_on_logout: bool
    knowledge_base_purge_days: int | None
    api_key_purge_days: int | None


def resolve_retention_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> RetentionConfig:
    """Resolve the effective retention policy: DB value if set, else env default.

    Read per-call, not cached at process start - this is the mechanism by
    which an admin's change takes effect without a restart.

    db_settings: the already-fetched singleton row, if the caller has one
    (see app.api.settings._to_response, which resolves provider and
    retention config from the same row) - avoids a redundant SELECT. Omit it
    for callers that only have a session. Defaults to a sentinel rather than
    None because None is also the legitimate value when no SystemSettings
    row has been created yet.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return RetentionConfig(
        conversation_retention_hours=resolve_field(
            db_value=db_settings.conversation_retention_hours if db_settings else None,
            env_default=settings.session_ttl_hours,
        ),
        cleanup_on_logout=resolve_field(
            db_value=db_settings.cleanup_on_logout if db_settings else None,
            env_default=settings.session_cleanup_on_logout,
        ),
        knowledge_base_purge_days=resolve_field(
            db_value=db_settings.knowledge_base_purge_days if db_settings else None,
            env_default=settings.knowledge_base_purge_days,
        ),
        api_key_purge_days=resolve_field(
            db_value=db_settings.api_key_purge_days if db_settings else None,
            env_default=settings.api_key_purge_days,
        ),
    )


def _delete_in_batches(db: Session, model, ids: list[str], batch_size: int) -> int:
    """Delete rows of `model` by primary key, batch_size at a time.

    Returns the number of rows deleted. Flushes after each batch so a large
    purge doesn't accumulate one enormous statement; the caller still owns
    the transaction and must commit.
    """
    deleted = 0
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        deleted += db.query(model).filter(model.id.in_(batch)).delete(synchronize_session=False)
        db.flush()
    return deleted


def purge_expired_conversations(
    db: Session,
    retention_hours: int | None,
    now: datetime,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Delete conversation threads (and their checkpoints) last updated before
    the retention cutoff. Returns the number of threads purged.

    retention_hours=None means "keep forever" and purges nothing. The cutoff
    is exclusive: a thread updated exactly at the cutoff is still inside the
    window, so a retention_hours=24 policy keeps a full 24 hours rather than
    24 hours minus an instant.

    System-wide, spanning all users - this is the TTL sweep, not per-user
    logout cleanup.
    """
    if retention_hours is None:
        return 0

    cutoff = (now - timedelta(hours=retention_hours)).replace(tzinfo=None)
    expired_ids = [
        row.id
        for row in db.query(ConversationThread.id)
        .filter(ConversationThread.updated_at < cutoff)
        .all()
    ]
    if not expired_ids:
        return 0

    return _purge_threads_by_id(db, expired_ids, batch_size)


def purge_user_conversations(
    db: Session, user_id: str, batch_size: int = DEFAULT_BATCH_SIZE
) -> int:
    """Delete all conversation threads (and their checkpoints) for one user.

    Backs SECURITY.md's logout-triggered cleanup. Scoped by user_id at the
    query, so it is structurally incapable of reaching another user's
    conversations; the caller must source user_id from the validated token,
    never from request input.
    """
    thread_ids = [
        row.id
        for row in db.query(ConversationThread.id)
        .filter(ConversationThread.user_id == user_id)
        .all()
    ]
    if not thread_ids:
        return 0

    return _purge_threads_by_id(db, thread_ids, batch_size)


def _purge_threads_by_id(db: Session, thread_ids: list[str], batch_size: int) -> int:
    """Delete the given threads and their checkpoints, in batches.

    Checkpoints are deleted explicitly rather than relying on the FK's
    ON DELETE CASCADE: SQLite (which the unit tests run against) does not
    enforce cascades unless PRAGMA foreign_keys is on, so leaning on the
    database would make the tests and Postgres disagree about whether
    checkpoint state actually goes away.
    """
    for start in range(0, len(thread_ids), batch_size):
        batch = thread_ids[start : start + batch_size]
        db.query(ConversationCheckpoint).filter(ConversationCheckpoint.thread_id.in_(batch)).delete(
            synchronize_session=False
        )
        db.flush()

    purged = _delete_in_batches(db, ConversationThread, thread_ids, batch_size)
    logger.info("Retention purge: deleted %d conversation thread(s)", purged)
    return purged


def purge_expired_knowledge_base(
    db: Session,
    purge_after_days: int | None,
    now: datetime,
    batch_size: int = DEFAULT_BATCH_SIZE,
    document_store: "DocumentStore | None" = None,
) -> int:
    """Hard-delete documents soft-deleted before the purge cutoff, along with
    their embeddings and (for file-backed documents) their MinIO objects.
    Returns the number of documents purged.

    Only soft-deleted rows are eligible: a live document has no purge
    window however old it is. purge_after_days=None keeps soft-deleted rows
    forever, which is the behaviour before this phase.

    document_store is optional so callers without object storage configured
    (or that don't care about it) keep today's DB-only purge behavior. When
    given, every expired document's storage_key (NULL for pasted-text
    entries, which are skipped) is deleted from MinIO in the same batches as
    the DB rows - the retention policy promises the underlying object is
    gone too, not just the row that pointed at it (see issue #13).
    """
    if purge_after_days is None:
        return 0

    cutoff = (now - timedelta(days=purge_after_days)).replace(tzinfo=None)
    expired = (
        db.query(KnowledgeBase.id, KnowledgeBase.storage_key)
        .filter(
            KnowledgeBase.deleted_at.is_not(None),
            KnowledgeBase.deleted_at < cutoff,
        )
        .all()
    )
    if not expired:
        return 0

    expired_ids = [row.id for row in expired]

    # Embeddings follow their parent document. Deleted explicitly for the
    # same reason checkpoints are - see _purge_threads_by_id.
    for start in range(0, len(expired_ids), batch_size):
        batch = expired_ids[start : start + batch_size]
        db.query(Embedding).filter(Embedding.doc_id.in_(batch)).delete(synchronize_session=False)
        db.flush()

    # The DB-side delete is flushed (and thus would already have surfaced any
    # constraint error) before the irreversible MinIO delete runs - never the
    # other way around. A full sweep (see run_retention_sweep /
    # app.cli.retention_sweep.main) runs every purge under one transaction
    # that commits once at the end; if MinIO objects were deleted first and a
    # later step in that same sweep then failed, db.rollback() would
    # resurrect these KnowledgeBase rows while their objects stayed gone
    # forever - a permanently orphaned, undetectable dangling storage_key.
    # Flushing here first means a DB-side failure for this batch is caught
    # before any object is destroyed.
    purged = _delete_in_batches(db, KnowledgeBase, expired_ids, batch_size)

    if document_store is not None:
        expired_storage_keys = [row.storage_key for row in expired if row.storage_key is not None]
        if expired_storage_keys:
            for start in range(0, len(expired_storage_keys), batch_size):
                document_store.delete_many(expired_storage_keys[start : start + batch_size])
        else:
            # Called once with an empty list even when nothing is file-backed,
            # so a caller asserting "the document store was consulted" for
            # this sweep doesn't have to special-case an all-typed-entries batch.
            document_store.delete_many([])

    logger.info("Retention purge: deleted %d soft-deleted document(s) and their embeddings", purged)
    return purged


def purge_expired_api_keys(
    db: Session,
    purge_after_days: int | None,
    now: datetime,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Hard-delete API keys revoked before the purge cutoff.

    Only revoked keys are eligible; an active key is never purged however
    old it is. purge_after_days=None keeps revoked rows forever, which is
    the behaviour before this phase.
    """
    if purge_after_days is None:
        return 0

    cutoff = (now - timedelta(days=purge_after_days)).replace(tzinfo=None)
    expired_ids = [
        row.id
        for row in db.query(APIKey.id)
        .filter(APIKey.revoked_at.is_not(None), APIKey.revoked_at < cutoff)
        .all()
    ]
    if not expired_ids:
        return 0

    purged = _delete_in_batches(db, APIKey, expired_ids, batch_size)
    logger.info("Retention purge: deleted %d revoked API key(s)", purged)
    return purged


def run_retention_sweep(
    db: Session, now: datetime, document_store: "DocumentStore | None" = None
) -> dict[str, int]:
    """Run every TTL-based purge under the currently effective policy.

    Returns per-store counts so the caller (the CronJob entrypoint) can log
    what was actually deleted rather than purging silently.

    document_store is forwarded to the knowledge-base purge so a purged
    document's MinIO object is deleted in the same sweep as its DB row
    (see purge_expired_knowledge_base) - omit it only when object storage
    isn't configured for this deployment.

    Deliberately does not touch audit_logs: audit records are retained on an
    independent schedule (docs/SECURITY.md). No function called from here
    queries AuditLog at all, and AuditLogRepository has no delete method, so
    the exemption holds structurally rather than by convention.

    Does not commit; the caller owns the transaction.
    """
    config = resolve_retention_config(db)

    result = {
        "conversations": purge_expired_conversations(db, config.conversation_retention_hours, now),
        "knowledge_base": purge_expired_knowledge_base(
            db, config.knowledge_base_purge_days, now, document_store=document_store
        ),
        "api_keys": purge_expired_api_keys(db, config.api_key_purge_days, now),
    }

    logger.info(
        "Retention sweep complete: %d conversation(s), %d document(s), %d API key(s) purged",
        result["conversations"],
        result["knowledge_base"],
        result["api_keys"],
    )
    return result
