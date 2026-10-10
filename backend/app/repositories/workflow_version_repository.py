"""Repositories for the versioned workflow store (issue #83)."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import ChatTurnVersion, WorkflowActiveVersion, WorkflowVersion
from app.workflows.version_chain import compute_chain_hash, compute_content_hash


class WorkflowVersionRepository:
    """Append-only store of workflow versions.

    Deliberately exposes no update or delete method - the same structural
    guarantee AuditLogRepository gives the audit trail, asserted by a test
    on this class's public surface. A version is the record of exactly
    what a workflow said when it answered a chat turn, so nothing in the
    application can rewrite one. Sequence numbers and hashes are computed
    here rather than accepted from callers, so no caller can forge a
    version's place in the chain.

    Not user-scoped: workflows are deployment-wide configuration, and every
    read path is admin-only (require_admin) or the chat endpoint resolving
    the active version - the same footing as SystemSettingsRepository.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def add(
        self,
        *,
        workflow_name: str,
        yaml_text: str,
        source: str,
        author_user_id: str,
        change_note: str,
        parent_version_id: str | None,
        now: datetime,
    ) -> WorkflowVersion:
        """Append the next version of workflow_name.

        Does not commit; the caller owns the transaction.
        """
        previous = self.latest_for_workflow(workflow_name)
        sequence = previous.sequence + 1 if previous else 1
        prev_chain_hash = previous.chain_hash if previous else None
        created_at = now.replace(tzinfo=None)
        content_hash = compute_content_hash(yaml_text)

        version = WorkflowVersion(
            workflow_name=workflow_name,
            sequence=sequence,
            yaml_text=yaml_text,
            content_hash=content_hash,
            prev_chain_hash=prev_chain_hash,
            chain_hash=compute_chain_hash(
                prev_chain_hash=prev_chain_hash,
                workflow_name=workflow_name,
                sequence=sequence,
                content_hash=content_hash,
                author_user_id=author_user_id,
                change_note=change_note,
                created_at=created_at,
            ),
            parent_version_id=parent_version_id,
            source=source,
            author_user_id=author_user_id,
            change_note=change_note,
            created_at=created_at,
        )
        self.db.add(version)
        self.db.flush()
        return version

    def get(self, version_id: str) -> WorkflowVersion | None:
        """Fetch one version by ID, or None."""
        return self.db.get(WorkflowVersion, version_id)

    def latest_for_workflow(self, workflow_name: str) -> WorkflowVersion | None:
        """The highest-sequence version of workflow_name, or None."""
        return (
            self.db.query(WorkflowVersion)
            .filter(WorkflowVersion.workflow_name == workflow_name)
            .order_by(WorkflowVersion.sequence.desc())
            .first()
        )

    def latest_builtin_for_workflow(self, workflow_name: str) -> WorkflowVersion | None:
        """The most recently synced built-in version of workflow_name, or None."""
        return (
            self.db.query(WorkflowVersion)
            .filter(
                WorkflowVersion.workflow_name == workflow_name,
                WorkflowVersion.source == "builtin",
            )
            .order_by(WorkflowVersion.sequence.desc())
            .first()
        )

    def list_for_workflow(self, workflow_name: str) -> list[WorkflowVersion]:
        """Every version of workflow_name, newest first."""
        return (
            self.db.query(WorkflowVersion)
            .filter(WorkflowVersion.workflow_name == workflow_name)
            .order_by(WorkflowVersion.sequence.desc())
            .all()
        )

    def list_workflow_names(self) -> list[str]:
        """Every workflow name with at least one version, sorted."""
        rows = (
            self.db.query(WorkflowVersion.workflow_name)
            .distinct()
            .order_by(WorkflowVersion.workflow_name)
            .all()
        )
        return [row.workflow_name for row in rows]


class WorkflowActiveVersionRepository:
    """The per-workflow "currently published" pointer.

    Mutable by nature - publishing *is* moving it. app.services.
    workflow_service is the only caller of set_active, and always records
    the move in audit_logs in the same transaction.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get_active_version_id(self, workflow_name: str) -> str | None:
        """The published version ID for workflow_name, or None."""
        pointer = self.db.get(WorkflowActiveVersion, workflow_name)
        return pointer.version_id if pointer else None

    def set_active(
        self, *, workflow_name: str, version_id: str, updated_by: str, now: datetime
    ) -> None:
        """Point workflow_name at version_id. Does not commit."""
        pointer = self.db.get(WorkflowActiveVersion, workflow_name)
        if pointer is None:
            pointer = WorkflowActiveVersion(workflow_name=workflow_name)
            self.db.add(pointer)
        pointer.version_id = version_id
        pointer.updated_by = updated_by
        pointer.updated_at = now.replace(tzinfo=None)
        self.db.flush()


class ChatTurnVersionRepository:
    """Insert-only record of which workflow version answered each chat turn.

    Purged only by the retention sweep's own window (see
    app.services.retention_service.purge_expired_chat_turn_versions),
    never by application code.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def record(
        self,
        *,
        user_id: str,
        thread_id: str,
        workflow_name: str,
        workflow_version_id: str,
        is_test_run: bool,
        now: datetime,
    ) -> ChatTurnVersion:
        """Record one chat turn's workflow version. Does not commit."""
        turn = ChatTurnVersion(
            user_id=user_id,
            thread_id=thread_id,
            workflow_name=workflow_name,
            workflow_version_id=workflow_version_id,
            is_test_run=is_test_run,
            created_at=now.replace(tzinfo=None),
        )
        self.db.add(turn)
        self.db.flush()
        return turn
