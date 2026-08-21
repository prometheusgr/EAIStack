"""Repository for ConversationThread data access."""

from sqlalchemy.orm import Session

from app.db.models import ConversationThread


class ThreadRepository:
    """Repository for querying and managing conversation thread ownership.

    This is the single structural place a thread_id is checked against
    a user_id. No endpoint or agent code may resolve a thread_id to
    checkpoint state without going through get_or_create_owned or
    get_by_id_for_user first - see app.agents.tools for the same
    closure-over-user_id reasoning applied to knowledge-base search.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get_or_create_owned(self, thread_id: str | None, user_id: str) -> ConversationThread:
        """Resolve a thread_id to a thread owned by user_id, minting a new one if needed.

        Returns the existing thread when thread_id is set and owned by
        user_id. Otherwise - thread_id is None, unknown, or owned by a
        different user - creates and returns a brand-new thread owned by
        user_id. A client can never legitimately hold another user's
        thread_id, so silently minting a fresh one rather than erroring
        self-heals stale client state without ever granting access to
        someone else's conversation.

        Does not commit; the caller owns the transaction.
        """
        if thread_id is not None:
            existing = self.get_by_id_for_user(thread_id, user_id)
            if existing is not None:
                return existing

        thread = ConversationThread(user_id=user_id)
        self.db.add(thread)
        self.db.flush()
        return thread

    def get_by_id_for_user(self, thread_id: str, user_id: str) -> ConversationThread | None:
        """Fetch a single thread by ID, verifying user ownership.

        Returns None if not found or not owned by user_id.
        """
        return (
            self.db.query(ConversationThread)
            .filter(
                ConversationThread.id == thread_id,
                ConversationThread.user_id == user_id,
            )
            .first()
        )

    def list_for_user(self, user_id: str) -> list[ConversationThread]:
        """Fetch all threads for a user, most recently updated first."""
        return (
            self.db.query(ConversationThread)
            .filter(ConversationThread.user_id == user_id)
            .order_by(ConversationThread.updated_at.desc())
            .all()
        )
