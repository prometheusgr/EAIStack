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
from app.services.system_settings_service import NOT_PROVIDED, NotProvided

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


def _resolve_field(db_value: int | bool | None, env_default: int | bool | None):
    """Resolve one overridable retention field: the DB value if a row set it,
    else the env default.

    Must stay an `is not None` check, not a truthiness check: 0 hours
    ("purge immediately") and False ("don't clean up on logout") are both
    legitimate overrides that a truthiness test would silently discard and
    replace with the env default - the same trap documented on
    system_settings_service._resolve_field.
    """
    return db_value if db_value is not None else env_default


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
        conversation_retention_hours=_resolve_field(
            db_settings.conversation_retention_hours if db_settings else None,
            settings.session_ttl_hours,
        ),
        cleanup_on_logout=bool(
            _resolve_field(
                db_settings.cleanup_on_logout if db_settings else None,
                settings.session_cleanup_on_logout,
            )
        ),
        knowledge_base_purge_days=_resolve_field(
            db_settings.knowledge_base_purge_days if db_settings else None,
            settings.knowledge_base_purge_days,
        ),
        api_key_purge_days=_resolve_field(
            db_settings.api_key_purge_days if db_settings else None,
            settings.api_key_purge_days,
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
) -> int:
    """Hard-delete documents soft-deleted before the purge cutoff, along with
    their embeddings. Returns the number of documents purged.

    Only soft-deleted rows are eligible: a live document has no purge
    window however old it is. purge_after_days=None keeps soft-deleted rows
    forever, which is the behaviour before this phase.
    """
    if purge_after_days is None:
        return 0

    cutoff = (now - timedelta(days=purge_after_days)).replace(tzinfo=None)
    expired_ids = [
        row.id
        for row in db.query(KnowledgeBase.id)
        .filter(
            KnowledgeBase.deleted_at.is_not(None),
            KnowledgeBase.deleted_at < cutoff,
        )
        .all()
    ]
    if not expired_ids:
        return 0

    # Embeddings follow their parent document. Deleted explicitly for the
    # same reason checkpoints are - see _purge_threads_by_id.
    for start in range(0, len(expired_ids), batch_size):
        batch = expired_ids[start : start + batch_size]
        db.query(Embedding).filter(Embedding.doc_id.in_(batch)).delete(synchronize_session=False)
        db.flush()

    purged = _delete_in_batches(db, KnowledgeBase, expired_ids, batch_size)
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


def run_retention_sweep(db: Session, now: datetime) -> dict[str, int]:
    """Run every TTL-based purge under the currently effective policy.

    Returns per-store counts so the caller (the CronJob entrypoint) can log
    what was actually deleted rather than purging silently.

    Deliberately does not touch audit_logs: audit records are retained on an
    independent schedule (docs/SECURITY.md). No function called from here
    queries AuditLog at all, and AuditLogRepository has no delete method, so
    the exemption holds structurally rather than by convention.

    Does not commit; the caller owns the transaction.
    """
    config = resolve_retention_config(db)

    result = {
        "conversations": purge_expired_conversations(db, config.conversation_retention_hours, now),
        "knowledge_base": purge_expired_knowledge_base(db, config.knowledge_base_purge_days, now),
        "api_keys": purge_expired_api_keys(db, config.api_key_purge_days, now),
    }

    logger.info(
        "Retention sweep complete: %d conversation(s), %d document(s), %d API key(s) purged",
        result["conversations"],
        result["knowledge_base"],
        result["api_keys"],
    )
    return result
