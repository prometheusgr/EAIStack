"""Repository for Embedding data access."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Embedding, KnowledgeBase


class EmbeddingRepository:
    """Repository for querying and managing embeddings."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def search_similar(self, user_id: str) -> list[tuple[Embedding, KnowledgeBase]]:
        """Fetch all active embeddings for a user with their knowledge bases.

        Returns tuples of (Embedding, KnowledgeBase) for similarity search or listing.
        Similarity scoring is done at the endpoint level after fetching.
        """
        query = (
            self.db.query(Embedding, KnowledgeBase)
            .join(KnowledgeBase, Embedding.doc_id == KnowledgeBase.id)
            .filter(
                KnowledgeBase.user_id == user_id,
                Embedding.deleted_at.is_(None),
            )
        )
        return [(emb, kb) for emb, kb in query.all()]

    def get_by_id(self, embedding_id: str, user_id: str) -> Embedding | None:
        """Fetch a single embedding by ID, verifying user ownership.

        Returns None if embedding not found or user doesn't own it.
        """
        return (
            self.db.query(Embedding)
            .join(KnowledgeBase, Embedding.doc_id == KnowledgeBase.id)
            .filter(
                Embedding.id == embedding_id,
                KnowledgeBase.user_id == user_id,
            )
            .first()
        )

    def get_knowledge_base_for_embedding(self, embedding_id: str) -> KnowledgeBase | None:
        """Fetch the knowledge base associated with an embedding."""
        embedding = self.db.query(Embedding).filter(Embedding.id == embedding_id).first()

        if not embedding:
            return None

        return self.db.query(KnowledgeBase).filter(KnowledgeBase.id == embedding.doc_id).first()

    def update_metadata(self, embedding_id: str, metadata: dict) -> None:
        """Update embedding metadata.

        Does not commit; the caller owns the transaction.
        """
        embedding = self.db.query(Embedding).filter(Embedding.id == embedding_id).first()

        if embedding:
            embedding.embed_metadata = metadata
            embedding.updated_at = datetime.now(timezone.utc)
            self.db.flush()

    def soft_delete(self, embedding_id: str) -> None:
        """Soft-delete an embedding by setting deleted_at timestamp.

        Does not commit; the caller owns the transaction.
        """
        embedding = self.db.query(Embedding).filter(Embedding.id == embedding_id).first()

        if embedding:
            embedding.deleted_at = datetime.now(timezone.utc)
            self.db.flush()
