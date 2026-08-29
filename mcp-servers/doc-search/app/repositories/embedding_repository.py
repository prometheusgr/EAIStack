"""Repository for Embedding data access."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Embedding, KnowledgeBase

# Reciprocal Rank Fusion's smoothing constant: fused_score(doc) = sum over
# branches ranking doc of 1 / (RRF_K + rank_in_branch). RRF needs no score
# normalization between the two branches' incomparable scales (cosine
# distance and ts_rank are not on a common scale), which is why it is the
# default fusion choice here rather than a weighted sum of raw scores. 60 is
# the constant from the original Cormack et al. RRF paper and is what most
# hybrid-search implementations use unchanged: it damps the influence of a
# rank-1 result just enough that a document ranked highly by only one branch
# doesn't automatically outrank one ranked moderately well by both.
RRF_K = 60

# How many candidate rows to pull per branch before fusing. Must exceed
# top_k so a document ranked outside the top_k of one branch, but well
# inside the top_k of the other, still gets a chance to be fused in — RRF
# only sees rank within the candidates each branch actually returns.
_CANDIDATE_MULTIPLIER = 4


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

    def search_hybrid(
        self,
        user_id: str,
        query_embedding: list[float],
        query_text: str,
        top_k: int,
        *,
        return_candidates: bool = False,
    ) -> list[tuple[Embedding, KnowledgeBase, float]]:
        """Return the top_k results for a user, ranking by a fusion of
        vector similarity and Postgres full-text search.

        Our knowledge base holds highly technical content (error codes,
        version strings, CLI flags) where pure vector search is weak: these
        are rare tokens, and embeddings smear them toward semantic
        neighbors rather than matching them exactly. The lexical branch
        (ts_rank against chunk_text_search, a GENERATED ALWAYS ... STORED
        tsvector column — see alembic/versions/008_hybrid_search.py) covers
        exactly that weakness; the vector branch still matters for
        conceptual/paraphrased queries with no exact token overlap.

        Fused via Reciprocal Rank Fusion (see RRF_K's own comment for why
        RRF specifically). The third tuple element is the fused RRF score
        (higher is more relevant) — not directly comparable to
        search_similar's cosine distance (lower is more relevant).

        User isolation (KnowledgeBase.user_id) and the soft-delete filter
        (Embedding.deleted_at) are applied on both branches independently,
        not just the vector one — the most likely place to introduce a
        data-leak bug in a hybrid query is a lexical branch that forgets
        the ownership filter.

        return_candidates=True skips the final truncation to top_k,
        returning the full fused pool (still bounded by
        top_k * _CANDIDATE_MULTIPLIER per branch) instead. app.search's
        search_knowledge_base needs this: it deduplicates multiple chunks
        of the same document down to one before truncating to its own
        top_k, and doing that dedup *after* this method had already
        truncated to top_k would silently shrink the candidate pool below
        what dedup needs, forcing search.py to compound its own multiplier
        on top of this one just to compensate. One layer owns the "how many
        candidates are enough" decision (this method, via
        _CANDIDATE_MULTIPLIER); search.py owns only "how many final,
        deduplicated results to return."
        """
        candidate_limit = top_k * _CANDIDATE_MULTIPLIER

        vector_ranking = self.search_similar(user_id, query_embedding, candidate_limit)
        lexical_ranking = self._search_lexical(user_id, query_text, candidate_limit)

        fused = _fuse_rankings(vector_ranking, lexical_ranking)
        return fused if return_candidates else fused[:top_k]

    def _search_lexical(
        self, user_id: str, query_text: str, limit: int
    ) -> list[tuple[Embedding, KnowledgeBase, float]]:
        """Return up to `limit` embeddings for a user ranked by ts_rank
        against query_text, best match first. Rows with no lexical overlap
        at all (ts_rank == 0) are excluded — an unranked "match" would only
        dilute the fused ranking with noise.

        Reaches chunk_text_search via Embedding.__table__.c rather than as
        an Embedding.chunk_text_search instance attribute — see that
        column's own comment in app.models for why (a generated column must
        never be an ORM-mapped attribute, or SQLAlchemy tries to write and
        RETURNING-fetch it like any other insertable column).
        """
        chunk_text_search = Embedding.__table__.c.chunk_text_search
        tsquery = func.plainto_tsquery("english", query_text)
        rank = func.ts_rank(chunk_text_search, tsquery).label("rank")

        query = (
            self.db.query(Embedding, KnowledgeBase, rank)
            .join(KnowledgeBase, Embedding.doc_id == KnowledgeBase.id)
            .filter(
                KnowledgeBase.user_id == user_id,
                Embedding.deleted_at.is_(None),
                chunk_text_search.op("@@")(tsquery),
            )
            .order_by(rank.desc())
            .limit(limit)
        )
        return [(emb, kb, rank_value) for emb, kb, rank_value in query.all()]


def _fuse_rankings(
    *rankings: list[tuple[Embedding, KnowledgeBase, float]],
) -> list[tuple[Embedding, KnowledgeBase, float]]:
    """Combine any number of ranked result lists via Reciprocal Rank Fusion.

    Each ranking contributes 1 / (RRF_K + rank) per embedding it contains
    (rank is 1-based position within that ranking); an embedding's fused
    score is the sum of its contributions across every ranking it appears
    in. Returns (embedding, knowledge_base, fused_score) triples sorted by
    fused_score descending — higher is more relevant, unlike either
    branch's own raw score.
    """
    fused_scores: dict[str, float] = {}
    embedding_and_kb_by_id: dict[str, tuple[Embedding, KnowledgeBase]] = {}

    for ranking in rankings:
        for rank, (embedding, knowledge_base, _) in enumerate(ranking, start=1):
            fused_scores[embedding.id] = fused_scores.get(embedding.id, 0.0) + 1 / (RRF_K + rank)
            embedding_and_kb_by_id.setdefault(embedding.id, (embedding, knowledge_base))

    ranked_ids = sorted(fused_scores, key=lambda emb_id: fused_scores[emb_id], reverse=True)
    return [
        (embedding_and_kb_by_id[emb_id][0], embedding_and_kb_by_id[emb_id][1], fused_scores[emb_id])
        for emb_id in ranked_ids
    ]
