"""Repository for ConversationCheckpoint data access."""

from sqlalchemy.orm import Session

from app.db.models import ConversationCheckpoint


class CheckpointRepository:
    """Repository for storing the latest LangGraph checkpoint per thread.

    Used only by app.agents.checkpointer.SqlAlchemyCheckpointSaver - never
    called directly from API code. Thread ownership is verified upstream
    by ThreadRepository before a thread_id ever reaches this repository.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get(self, thread_id: str) -> ConversationCheckpoint | None:
        """Fetch the latest checkpoint for a thread, or None if it has none yet."""
        return (
            self.db.query(ConversationCheckpoint)
            .filter(ConversationCheckpoint.thread_id == thread_id)
            .first()
        )

    def upsert(self, thread_id: str, checkpoint: bytes, metadata: bytes) -> ConversationCheckpoint:
        """Create or overwrite the single checkpoint row for a thread.

        checkpoint/metadata are opaque serialized bytes produced by the
        caller (SqlAlchemyCheckpointSaver's serde) - this repository
        never inspects their contents.

        Only the latest checkpoint per thread is kept (Phase 4a scope is
        conversation resume, not time-travel/replay), so this always
        replaces rather than appends.

        Does not commit; the caller owns the transaction.
        """
        existing = self.get(thread_id)
        if existing is not None:
            existing.checkpoint = checkpoint
            existing.checkpoint_metadata = metadata
            self.db.flush()
            return existing

        row = ConversationCheckpoint(
            thread_id=thread_id, checkpoint=checkpoint, checkpoint_metadata=metadata
        )
        self.db.add(row)
        self.db.flush()
        return row
