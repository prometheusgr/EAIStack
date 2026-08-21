"""Repository for AuditLog data access."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import AuditLog


class AuditLogRepository:
    """Append-only repository for the audit trail.

    Deliberately exposes no update or delete method. This is the
    code-level enforcement of docs/SECURITY.md's guarantee that audit
    records survive every retention purge: a purge path cannot delete
    audit history through this repository because there is no method to
    call, and app.services.retention_service never queries AuditLog at
    all. Enforced structurally rather than by convention, and covered by
    a test asserting this class's public surface.

    Not user-scoped: actor_user_id records who made a change, not who
    owns the row, so the usual per-user read filtering does not apply.
    Reads are admin-only, gated at the endpoint by require_admin.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def record(
        self,
        *,
        actor_user_id: str,
        action: str,
        field_name: str,
        old_value: str | None,
        new_value: str | None,
        now: datetime,
    ) -> AuditLog:
        """Append one audit entry.

        old_value is None when the field had no DB override before the
        change - distinct from the string "None", so the trail can tell
        "was using the env default" from "was explicitly set to None".

        now is passed in rather than read from the clock so callers
        writing several entries for one change stamp them identically,
        and so tests are deterministic without patching datetime.

        Does not commit; the caller owns the transaction.
        """
        entry = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            created_at=now.replace(tzinfo=None),
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def list_recent(self, limit: int = 100) -> list[AuditLog]:
        """Fetch the most recent audit entries, newest first."""
        return self.db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
