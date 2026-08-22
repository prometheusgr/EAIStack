"""Repository for Embedding data access."""

from sqlalchemy.orm import Session

from app.models import Embedding, KnowledgeBase


class EmbeddingRepository:
    """Repository for querying embeddings, read-only by design.

    Search is the single reason this service touches the database, and
    user_id is a required argument of the only method here — so there is no
    way to read an embedding without proving ownership first. That is the
    user-isolation guarantee of docs/REPOSITORY_PATTERN.md enforced
    structurally rather than by convention, which matters more here than in
    the backend: doc-search derives user_id from a JWT it verifies itself
    (see app/auth.py) precisely because it must never serve one user's
    documents to another.

    The absence of write methods is deliberate, not an oversight. doc-search
    is a read-only consumer of a schema owned by Alembic in backend/ (see
    app/models.py's module docstring); it never writes to knowledge_base,
    embeddings, or system_settings. The backend's own EmbeddingRepository
    has update_metadata/soft_delete, and those are intentionally not ported:
    following the same reasoning as AuditLogRepository's missing delete
    method, a write path cannot call a method that does not exist. Adding
    one here would silently expand this service's contract, so it should be
    treated as a design change requiring justification, not a routine edit.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def search_similar(
        self, user_id: str, query_embedding: list[float], top_k: int
    ) -> list[tuple[Embedding, KnowledgeBase, float]]:
        """Return the top_k most similar embeddings for a user, nearest first.

        Ranking is done in Postgres via pgvector's cosine distance operator.
        The third tuple element is the cosine distance (0 = identical,
        2 = opposite); lower is more similar.

        Only the embedding's own soft-delete flag is checked, matching
        backend/app/repositories/embedding_repository.py exactly — the two
        implementations must agree on what counts as a live document.
        """
        query = (
            self.db.query(
                Embedding,
                KnowledgeBase,
                Embedding.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .join(KnowledgeBase, Embedding.doc_id == KnowledgeBase.id)
            .filter(
                KnowledgeBase.user_id == user_id,
                Embedding.deleted_at.is_(None),
            )
            .order_by("distance")
            .limit(top_k)
        )
        return [(emb, kb, distance) for emb, kb, distance in query.all()]
