"""Tests for doc-search's EmbeddingRepository.

Marked integration: ranking uses pgvector's cosine distance operator, which
only runs against real Postgres (doc-search has no SQLite fallback — see
tests/conftest.py), so these live under tests/integration/ and are not part
of the CI-gating unit run.

The repository is the structural enforcement point for user isolation: the
only way to read embeddings is through a method that requires a user_id and
filters on it. These tests pin that guarantee. The companion assertion that
the class exposes no write method lives in tests/unit/test_repository_surface.py,
which needs no database and so runs in the CI-gating unit suite.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models import Embedding, KnowledgeBase
from app.repositories import EmbeddingRepository
from app.search import generate_query_embedding


def _seed_document(
    db_session,
    user_id: str,
    title: str,
    content: str,
    chunk_text: str | None = None,
    embedding_vector: list[float] | None = None,
) -> Embedding:
    """chunk_text defaults to content, matching the pre-chunking one-row-per-
    document shape - most existing tests here only care about vector
    similarity and don't need the two to differ.

    embedding_vector defaults to generate_query_embedding(content) (the fake
    provider's hash(text)-seeded vector) for most tests here, which only
    care that documents get *some* distinct vector. Pass an explicit vector
    (see _unit_vector) when a test's assertions depend on a specific,
    deterministic cosine-distance ranking - hash(text) is randomized per
    process by default, so relying on it for a specific ranking outcome is
    flaky.
    """
    kb = KnowledgeBase(id=str(uuid4()), user_id=user_id, title=title, content=content)
    db_session.add(kb)
    db_session.commit()

    embedding = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=(
            embedding_vector
            if embedding_vector is not None
            else generate_query_embedding(db_session, content)
        ),
        chunk_text=chunk_text if chunk_text is not None else content,
    )
    db_session.add(embedding)
    db_session.commit()
    return embedding


def _unit_vector(
    dominant_index: int, secondary_index: int | None = None, dimensions: int = 768
) -> list[float]:
    """A vector that is 1.0 at dominant_index (and, if given, 0.5 at
    secondary_index) and 0.0 elsewhere, for deterministic cosine-distance
    comparisons: two vectors sharing a dominant_index are close; two with
    different dominant_index values are maximally far (cosine distance 1.0,
    orthogonal) regardless of what generate_query_embedding's hash-seeded
    randomness would have produced for the same text.
    """
    vector = [0.0] * dimensions
    vector[dominant_index] = 1.0
    if secondary_index is not None:
        vector[secondary_index] = 0.5
    return vector


@pytest.mark.integration
def test_search_similar_returns_embedding_knowledge_base_and_distance(db_session):
    """Each result is the (Embedding, KnowledgeBase, distance) triple callers rank on."""
    _seed_document(
        db_session,
        user_id="user-a",
        title="Vacation Policy",
        content="Employees receive 25 days of paid vacation per year.",
    )

    repo = EmbeddingRepository(db_session)
    matches = repo.search_similar(
        "user-a", generate_query_embedding(db_session, "vacation days"), top_k=5
    )

    assert len(matches) == 1
    embedding, knowledge_base, distance = matches[0]
    assert isinstance(embedding, Embedding)
    assert knowledge_base.title == "Vacation Policy"
    assert isinstance(distance, float)


@pytest.mark.integration
def test_search_similar_excludes_other_users_documents(db_session):
    """Ownership is filtered in the query itself, not by the caller afterwards.

    This is the isolation guarantee the repository pattern exists to enforce
    structurally: there is no read method that skips the user_id filter.
    """
    _seed_document(
        db_session,
        user_id="user-b",
        title="User B Confidential Doc",
        content="This document belongs only to user B.",
    )

    repo = EmbeddingRepository(db_session)
    matches = repo.search_similar(
        "user-a", generate_query_embedding(db_session, "confidential"), top_k=5
    )

    assert matches == []


@pytest.mark.integration
def test_search_similar_excludes_soft_deleted_embeddings(db_session):
    """A soft-deleted embedding is invisible to search even though its row remains."""
    embedding = _seed_document(
        db_session,
        user_id="user-a",
        title="Retired Policy",
        content="This policy has been withdrawn.",
    )
    embedding.deleted_at = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    db_session.commit()

    repo = EmbeddingRepository(db_session)
    matches = repo.search_similar("user-a", generate_query_embedding(db_session, "policy"), top_k=5)

    assert matches == []


@pytest.mark.integration
def test_search_similar_orders_nearest_first_and_respects_top_k(db_session):
    """Results come back nearest-first by cosine distance, capped at top_k.

    Ordering is asserted via the returned distances rather than by expecting
    a particular document to win: the ranking contract is "ascending cosine
    distance", and that holds regardless of what the embedding provider
    produces for any given text.
    """
    for index in range(4):
        _seed_document(
            db_session,
            user_id="user-a",
            title=f"Doc {index}",
            content=f"Content number {index} about workplace policy.",
        )

    repo = EmbeddingRepository(db_session)
    matches = repo.search_similar(
        "user-a", generate_query_embedding(db_session, "workplace policy"), top_k=3
    )

    distances = [distance for _, _, distance in matches]
    assert len(matches) == 3
    assert distances == sorted(distances)


# search_hybrid: vector similarity + Postgres full-text search, fused via
# Reciprocal Rank Fusion (see app.repositories.embedding_repository's
# search_hybrid and its RRF_K constant). Motivated by issue #7 Prompt 3:
# our knowledge base holds error codes, version strings, and CLI flags —
# rare tokens embeddings smear toward semantic neighbors, where pure
# vector search alone ranks the exact match poorly.


@pytest.mark.integration
def test_search_hybrid_ranks_exact_token_match_first_when_vector_search_alone_would_not(
    db_session,
):
    """The actual motivating case: an exact-token query (an error code) is
    outranked by an unrelated-but-semantically-adjacent document under pure
    vector search, but hybrid (lexical + vector, fused via RRF) ranks the
    exact match first.

    Confirms the pure-vector baseline actually fails before asserting the
    fix — per Prompt 3's own instruction: "If that test does not fail
    before your change, the change is not justified."

    Embedding vectors are seeded directly as one-hot-ish unit vectors
    (deliberately, not via generate_query_embedding) rather than the fake
    provider's hash(text)-seeded vectors: Python randomizes str hashing per
    process by default, which made an earlier version of this test flaky —
    the "exact match" could occasionally win on vector similarity by chance
    alone. Direct vectors make the cosine-distance ranking deterministic,
    so only the lexical/hybrid behavior under test can affect the outcome.
    """
    query_vector = _unit_vector(dominant_index=0)
    exact_match_vector = _unit_vector(dominant_index=1)  # deliberately far from query_vector
    distractor_vector = _unit_vector(dominant_index=0, secondary_index=2)  # close to query_vector

    exact_match = _seed_document(
        db_session,
        user_id="user-a",
        title="ORA-01555 Troubleshooting",
        content="Generic document body unrelated to the query semantically.",
        chunk_text=(
            "ORA-01555: snapshot too old. Increase UNDO_RETENTION or the " "undo tablespace size."
        ),
        embedding_vector=exact_match_vector,
    )
    for i in range(5):
        _seed_document(
            db_session,
            user_id="user-a",
            title=f"Database Error Guide {i}",
            content=f"How to troubleshoot common database errors, guide {i}.",
            chunk_text=f"How to troubleshoot common database errors, guide {i}.",
            embedding_vector=distractor_vector,
        )

    repo = EmbeddingRepository(db_session)

    vector_only = repo.search_similar("user-a", query_vector, top_k=6)
    vector_only_ranking = [emb.id for emb, _, _ in vector_only]
    assert vector_only_ranking.index(exact_match.id) > 0, (
        "expected pure vector search to NOT rank the exact error-code match "
        "first among semantically-similar distractors - if it already does, "
        "this test no longer demonstrates hybrid search's value"
    )

    hybrid = repo.search_hybrid("user-a", query_vector, query_text="ORA-01555", top_k=6)
    assert hybrid[0][0].id == exact_match.id


@pytest.mark.integration
def test_search_hybrid_excludes_other_users_documents(db_session):
    """User isolation must hold on the lexical branch too, not just vector -
    the most likely place for a data-leak bug in a hybrid query (a lexical
    branch that forgets the ownership filter).
    """
    _seed_document(
        db_session,
        user_id="user-b",
        title="User B Confidential Doc",
        content="Confidential content.",
        chunk_text="ORA-01555 snapshot too old, confidential to user B.",
    )

    query_embedding = generate_query_embedding(db_session, "ORA-01555")
    repo = EmbeddingRepository(db_session)
    matches = repo.search_hybrid("user-a", query_embedding, query_text="ORA-01555", top_k=5)

    assert matches == []


@pytest.mark.integration
def test_search_hybrid_excludes_soft_deleted_embeddings(db_session):
    """A soft-deleted embedding is invisible to hybrid search on both
    branches, not just the vector one.
    """
    embedding = _seed_document(
        db_session,
        user_id="user-a",
        title="Retired Doc",
        content="Retired.",
        chunk_text="ORA-01555 snapshot too old, now retired.",
    )
    embedding.deleted_at = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    db_session.commit()

    query_embedding = generate_query_embedding(db_session, "ORA-01555")
    repo = EmbeddingRepository(db_session)
    matches = repo.search_hybrid("user-a", query_embedding, query_text="ORA-01555", top_k=5)

    assert matches == []


@pytest.mark.integration
def test_search_hybrid_respects_top_k(db_session):
    """Fused results are capped at top_k, same contract as search_similar."""
    for i in range(5):
        _seed_document(
            db_session,
            user_id="user-a",
            title=f"Doc {i}",
            content=f"Certificate rotation content {i}.",
            chunk_text=f"Certificate rotation content {i}.",
        )

    query_embedding = generate_query_embedding(db_session, "certificate rotation")
    repo = EmbeddingRepository(db_session)
    matches = repo.search_hybrid(
        "user-a", query_embedding, query_text="certificate rotation", top_k=3
    )

    assert len(matches) == 3


@pytest.mark.integration
def test_search_hybrid_returns_a_match_found_only_by_the_lexical_branch(db_session):
    """A document that pure vector search alone would not surface at all
    (seeded with a query_embedding pointing elsewhere) still appears in
    hybrid results, because the lexical branch finds it independently -
    demonstrating that RRF fusion surfaces either branch's find, not just
    an intersection of both.
    """
    lexical_only_match = _seed_document(
        db_session,
        user_id="user-a",
        title="CLI Reference",
        content="Something else entirely, unrelated in embedding space.",
        chunk_text="The --ctx-size flag sets the context window in tokens.",
    )

    query_embedding = generate_query_embedding(db_session, "something else entirely")
    repo = EmbeddingRepository(db_session)
    matches = repo.search_hybrid("user-a", query_embedding, query_text="--ctx-size", top_k=5)

    assert lexical_only_match.id in [emb.id for emb, _, _ in matches]
