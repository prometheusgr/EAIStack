"""Integration tests for EmbeddingRepository.search_similar against real pgvector.

Cosine similarity ranking only produces meaningful results against a real
Postgres + pgvector instance, so these tests run against a testcontainers
Postgres (see conftest.py: test_db_url provisions real Postgres when a test
is marked `integration`) rather than the SQLite fallback used by unit tests.
"""

from uuid import uuid4

import pytest

from app.db.models import Embedding, KnowledgeBase
from app.repositories import EmbeddingRepository


def _make_knowledge_base(user_id: str, title: str = "Test Doc") -> KnowledgeBase:
    return KnowledgeBase(
        id=str(uuid4()),
        user_id=user_id,
        title=title,
        content=f"Content for {title}",
    )


def _make_embedding(doc_id: str, vector: list[float]) -> Embedding:
    return Embedding(id=str(uuid4()), doc_id=doc_id, embedding=vector)


def _unit_vector(dominant_index: int, dimensions: int = 1536) -> list[float]:
    """A one-hot vector, so cosine distance between two of these is easy to reason about."""
    vector = [0.0] * dimensions
    vector[dominant_index] = 1.0
    return vector


@pytest.mark.integration
def test_search_similar_ranks_nearest_vector_first(db_session):
    """The embedding closest to the query vector (by cosine distance) ranks first."""
    kb = _make_knowledge_base("user-a")
    db_session.add(kb)
    db_session.commit()

    near = _make_embedding(kb.id, _unit_vector(0))
    far = _make_embedding(kb.id, _unit_vector(1))
    db_session.add_all([near, far])
    db_session.commit()

    repo = EmbeddingRepository(db_session)
    results = repo.search_similar("user-a", query_embedding=_unit_vector(0), top_k=10)

    assert len(results) == 2
    nearest_emb, nearest_kb, nearest_distance = results[0]
    assert nearest_emb.id == near.id
    assert nearest_kb.id == kb.id
    second_distance = results[1][2]
    assert nearest_distance < second_distance


@pytest.mark.integration
def test_search_similar_limits_results_to_top_k(db_session):
    """top_k caps the number of returned results."""
    kb = _make_knowledge_base("user-a")
    db_session.add(kb)
    db_session.commit()

    embeddings = [_make_embedding(kb.id, _unit_vector(i)) for i in range(5)]
    db_session.add_all(embeddings)
    db_session.commit()

    repo = EmbeddingRepository(db_session)
    results = repo.search_similar("user-a", query_embedding=_unit_vector(0), top_k=2)

    assert len(results) == 2


@pytest.mark.integration
def test_search_similar_excludes_other_users_documents(db_session):
    """A user's search must never surface another user's embeddings."""
    kb_a = _make_knowledge_base("user-a", title="User A Doc")
    kb_b = _make_knowledge_base("user-b", title="User B Doc")
    db_session.add_all([kb_a, kb_b])
    db_session.commit()

    emb_a = _make_embedding(kb_a.id, _unit_vector(0))
    emb_b = _make_embedding(kb_b.id, _unit_vector(0))
    db_session.add_all([emb_a, emb_b])
    db_session.commit()

    repo = EmbeddingRepository(db_session)
    results = repo.search_similar("user-a", query_embedding=_unit_vector(0), top_k=10)

    assert len(results) == 1
    _, kb_result, _ = results[0]
    assert kb_result.id == kb_a.id


@pytest.mark.integration
def test_search_similar_excludes_soft_deleted_embeddings(db_session):
    """Soft-deleted embeddings are never returned, regardless of similarity."""
    from datetime import datetime, timezone

    kb = _make_knowledge_base("user-a")
    db_session.add(kb)
    db_session.commit()

    active = _make_embedding(kb.id, _unit_vector(0))
    deleted = _make_embedding(kb.id, _unit_vector(0))
    deleted.deleted_at = datetime.now(timezone.utc)
    db_session.add_all([active, deleted])
    db_session.commit()

    repo = EmbeddingRepository(db_session)
    results = repo.search_similar("user-a", query_embedding=_unit_vector(0), top_k=10)

    assert len(results) == 1
    assert results[0][0].id == active.id
