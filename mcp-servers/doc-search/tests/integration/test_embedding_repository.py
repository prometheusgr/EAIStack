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


def _seed_document(db_session, user_id: str, title: str, content: str) -> Embedding:
    kb = KnowledgeBase(id=str(uuid4()), user_id=user_id, title=title, content=content)
    db_session.add(kb)
    db_session.commit()

    embedding = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=generate_query_embedding(db_session, content),
    )
    db_session.add(embedding)
    db_session.commit()
    return embedding


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
