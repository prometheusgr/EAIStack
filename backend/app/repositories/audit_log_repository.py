"""Repository for AuditLog data access."""

from datetime import datetime

from sqlalchemy import func
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

    def count_by_action_and_value_since(self, action: str, *, since: datetime) -> dict[str, int]:
        """Count entries for one action at/after a cutoff, grouped by
        new_value.

        Built for issue #48's admin dashboard, which needs per-pattern
        guardrail.input_rejected trip counts over a recent window (new_value
        holds the pattern/reason that tripped -- see
        chat_guardrail_service.check_input_guardrail). A dedicated,
        action-filtered aggregation query rather than aggregating over
        list_recent(): that method has no action filter, so once enough
        other audit-event types accumulate, the most recent rows it returns
        could easily contain few or none of the action being counted --
        silently undercounting rather than raising.

        A None new_value groups under the string "unknown" rather than being
        dropped, since count_by_action_and_value_since is only currently
        called for guardrail.input_rejected, whose new_value is always
        populated -- Python's dict groups None and "unknown" identically for
        that caller's purposes, but a defined key here keeps the return type
        exactly dict[str, int], not dict[str | None, int].
        """
        rows = (
            self.db.query(AuditLog.new_value, func.count(AuditLog.id))
            .filter(AuditLog.action == action, AuditLog.created_at >= since.replace(tzinfo=None))
            .group_by(AuditLog.new_value)
            .all()
        )
        return {(new_value or "unknown"): count for new_value, count in rows}
