"""Repository for KnowledgeBase data access."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Embedding, KnowledgeBase


class KnowledgeBaseRepository:
    """Repository for querying and managing knowledge base entries."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get_by_user(self, user_id: str) -> list[KnowledgeBase]:
        """Fetch all active knowledge base entries for a user.

        Excludes soft-deleted entries.
        """
        return (
            self.db.query(KnowledgeBase)
            .filter(
                KnowledgeBase.user_id == user_id,
                KnowledgeBase.deleted_at.is_(None),
            )
            .all()
        )

    def get_by_id(self, kb_id: str, user_id: str) -> KnowledgeBase | None:
        """Fetch a single active knowledge base entry, verifying user ownership.

        Returns None if not found, not owned by the user, or soft-deleted.
        """
        return (
            self.db.query(KnowledgeBase)
            .filter(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.user_id == user_id,
                KnowledgeBase.deleted_at.is_(None),
            )
            .first()
        )

    def create(self, kb: KnowledgeBase) -> KnowledgeBase:
        """Persist a new knowledge base entry.

        Does not commit; the caller owns the transaction.
        """
        self.db.add(kb)
        self.db.flush()
        return kb

    def update(self, kb: KnowledgeBase, title: str, content: str, metadata: dict) -> KnowledgeBase:
        """Update an active knowledge base entry's fields.

        Does not commit; the caller owns the transaction.
        """
        kb.title = title
        kb.content = content
        kb.doc_metadata = metadata
        kb.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return kb

    def soft_delete_with_embeddings(self, kb: KnowledgeBase) -> None:
        """Soft-delete a knowledge base entry and its embeddings in one transaction.

        Does not commit; the caller owns the transaction.
        """
        now = datetime.now(timezone.utc)
        kb.deleted_at = now

        embeddings = self.db.query(Embedding).filter(Embedding.doc_id == kb.id).all()
        for embedding in embeddings:
            embedding.deleted_at = now

        self.db.flush()
