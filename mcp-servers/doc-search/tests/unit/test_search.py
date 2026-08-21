"""Tests for doc-search's core search logic.

Marked integration: ranking uses pgvector's cosine distance operator, which
only runs against real Postgres (mirrors backend's
tests/unit/test_embedding_repository.py and tests/unit/test_tools.py, which
carry the same constraint despite living under a "unit" directory name).

Behavior must match backend/app/agents/tools.py's search_knowledge_base
exactly (same excerpt formatting, same "no matches" message, same
per-user scoping) — this is a structural move, not a behavior change.
"""

from uuid import uuid4

import pytest

from app.models import Embedding, KnowledgeBase
from app.search import generate_query_embedding, search_knowledge_base


def _seed_document(db_session, user_id: str, title: str, content: str) -> None:
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


@pytest.mark.integration
def test_search_knowledge_base_returns_matching_document_content(db_session):
    """Returns the seeded document's title and content excerpt for a matching query."""
    _seed_document(
        db_session,
        user_id="user-a",
        title="Vacation Policy",
        content="Employees receive 25 days of paid vacation per year.",
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="vacation days", top_k=5)

    assert "Vacation Policy" in result
    assert "25 days of paid vacation" in result


@pytest.mark.integration
def test_search_knowledge_base_returns_empty_message_when_no_documents(db_session):
    """A clear, non-crashing message is returned when the user has no documents."""
    result = search_knowledge_base(
        db_session, user_id="user-with-no-docs", query="anything", top_k=5
    )

    assert isinstance(result, str)
    assert len(result) > 0
    assert "Vacation Policy" not in result


@pytest.mark.integration
def test_search_knowledge_base_is_scoped_to_requested_user(db_session):
    """Only documents owned by the requested user_id are returned — the
    critical isolation guarantee once search runs in a separate process from
    the backend: user_id here always comes from a verified JWT's sub claim
    (see app.auth.verify_bearer_token), never a caller-supplied string.
    """
    _seed_document(
        db_session,
        user_id="user-b",
        title="User B Confidential Doc",
        content="This document belongs only to user B.",
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="confidential", top_k=5)

    assert "User B Confidential Doc" not in result
    assert "belongs only to user B" not in result


@pytest.mark.integration
def test_search_knowledge_base_truncates_long_content_with_ellipsis(db_session):
    """Content longer than the excerpt limit is truncated with a trailing ellipsis."""
    long_content = "A" * 500
    _seed_document(db_session, user_id="user-a", title="Long Doc", content=long_content)

    result = search_knowledge_base(db_session, user_id="user-a", query="long", top_k=5)

    assert "A" * 300 in result
    assert "..." in result
    assert "A" * 301 not in result
