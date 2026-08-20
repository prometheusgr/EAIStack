"""Tests for the search_knowledge_base agent tool.

Marked integration: the tool ranks results using EmbeddingRepository.search_similar,
which relies on pgvector's cosine distance operator and only runs against real
Postgres (see test_embedding_repository.py for the same constraint).
"""

from uuid import uuid4

import pytest

from app.agents.tools import make_search_knowledge_base_tool
from app.db.models import Embedding, KnowledgeBase
from app.services import generate_embedding


def _seed_document(db_session, user_id: str, title: str, content: str) -> None:
    kb = KnowledgeBase(id=str(uuid4()), user_id=user_id, title=title, content=content)
    db_session.add(kb)
    db_session.commit()

    embedding = Embedding(id=str(uuid4()), doc_id=kb.id, embedding=generate_embedding(content))
    db_session.add(embedding)
    db_session.commit()


@pytest.mark.integration
def test_search_knowledge_base_returns_matching_document_content(db_session):
    """The tool returns the seeded document's title and content for a matching query."""
    _seed_document(
        db_session,
        user_id="user-a",
        title="Vacation Policy",
        content="Employees receive 25 days of paid vacation per year.",
    )

    tool = make_search_knowledge_base_tool(user_id="user-a", db=db_session)
    result = tool.invoke({"query": "vacation days"})

    assert "Vacation Policy" in result
    assert "25 days of paid vacation" in result


@pytest.mark.integration
def test_search_knowledge_base_returns_empty_message_when_no_documents(db_session):
    """A clear, non-crashing message is returned when the user has no documents."""
    tool = make_search_knowledge_base_tool(user_id="user-with-no-docs", db=db_session)
    result = tool.invoke({"query": "anything"})

    assert isinstance(result, str)
    assert len(result) > 0
    assert "Vacation Policy" not in result


@pytest.mark.integration
def test_search_knowledge_base_is_scoped_to_bound_user(db_session):
    """The tool only returns documents owned by the user_id it was bound to,
    regardless of what query the model sends — user_id is not a model-supplied
    argument, so a compromised or confused model cannot read another user's data.
    """
    _seed_document(
        db_session,
        user_id="user-b",
        title="User B Confidential Doc",
        content="This document belongs only to user B.",
    )

    tool = make_search_knowledge_base_tool(user_id="user-a", db=db_session)
    result = tool.invoke({"query": "confidential"})

    assert "User B Confidential Doc" not in result
    assert "belongs only to user B" not in result
