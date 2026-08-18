"""Unit tests for Embeddings API - TDD discipline."""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.models import Embedding, KnowledgeBase


@pytest.mark.unit
def test_embedding_model_creation(db_session):
    """Test: Embedding model can be created with vector."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-123",
        title="Test Document",
        content="This is test content",
    )
    db_session.add(kb)
    db_session.commit()

    embedding = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 1536,  # Standard OpenAI embedding dimension
    )
    db_session.add(embedding)
    db_session.commit()

    retrieved = db_session.query(Embedding).filter_by(doc_id=kb.id).first()
    assert retrieved is not None
    assert len(retrieved.embedding) == 1536
    assert retrieved.doc_id == kb.id


@pytest.mark.unit
def test_embedding_user_isolation(db_session):
    """Test: Embeddings are isolated per user via knowledge base."""
    kb_a = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Doc A",
        content="Content A",
    )
    kb_b = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-b",
        title="Doc B",
        content="Content B",
    )
    db_session.add_all([kb_a, kb_b])
    db_session.commit()

    emb_a = Embedding(
        id=str(uuid4()),
        doc_id=kb_a.id,
        embedding=[0.1] * 1536,
    )
    emb_b = Embedding(
        id=str(uuid4()),
        doc_id=kb_b.id,
        embedding=[0.2] * 1536,
    )
    db_session.add_all([emb_a, emb_b])
    db_session.commit()

    user_a_embs = db_session.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(KnowledgeBase.user_id == "user-a").all()

    user_b_embs = db_session.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(KnowledgeBase.user_id == "user-b").all()

    assert len(user_a_embs) == 1
    assert len(user_b_embs) == 1
    assert user_a_embs[0].doc_id == kb_a.id
    assert user_b_embs[0].doc_id == kb_b.id


@pytest.mark.unit
def test_embedding_soft_delete_excludes_deleted(db_session):
    """Test: Soft-deleted embeddings (deleted_at not None) are excluded from active list."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    active_emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 1536,
        deleted_at=None,
    )
    deleted_emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.2] * 1536,
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([active_emb, deleted_emb])
    db_session.commit()

    active_count = db_session.query(Embedding).filter(
        Embedding.doc_id == kb.id,
        Embedding.deleted_at.is_(None)
    ).count()

    assert active_count == 1


@pytest.mark.unit
def test_list_embeddings_success(client, db_session):
    """Test: GET /api/embeddings returns all active embeddings for user."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="test-user-123",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb1 = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 1536,
    )
    emb2 = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.2] * 1536,
    )
    db_session.add_all([emb1, emb2])
    db_session.commit()

    response = client.get("/api/embeddings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(e["doc_id"] == kb.id for e in data)


@pytest.mark.unit
def test_list_embeddings_empty(client, db_session):
    """Test: GET /api/embeddings returns empty list when no embeddings."""
    response = client.get("/api/embeddings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


@pytest.mark.unit
def test_get_embedding_detail(client, db_session):
    """Test: GET /api/embeddings/{id} returns embedding with KB info."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="test-user-123",
        title="Test Document",
        content="Test content here",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 1536,
    )
    db_session.add(emb)
    db_session.commit()

    response = client.get(f"/api/embeddings/{emb.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == emb.id
    assert data["doc_id"] == kb.id
    assert data["title"] == "Test Document"
    assert data["content"] == "Test content here"


@pytest.mark.unit
def test_get_embedding_not_found(client):
    """Test: GET /api/embeddings/{id} for non-existent embedding returns 404."""
    response = client.get(f"/api/embeddings/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.unit
def test_update_embedding_metadata(client, db_session):
    """Test: PUT /api/embeddings/{id} updates metadata."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="test-user-123",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 1536,
        embed_metadata={"key": "old_value"},
    )
    db_session.add(emb)
    db_session.commit()

    update_request = {"metadata": {"key": "new_value", "added": True}}

    response = client.put(f"/api/embeddings/{emb.id}", json=update_request)

    assert response.status_code == 200
    data = response.json()
    assert data["embed_metadata"]["key"] == "new_value"
    assert data["embed_metadata"]["added"] is True


@pytest.mark.unit
def test_delete_embedding_soft_delete(client, db_session):
    """Test: DELETE /api/embeddings/{id} soft-deletes embedding."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="test-user-123",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 1536,
    )
    db_session.add(emb)
    db_session.commit()

    response = client.delete(f"/api/embeddings/{emb.id}")

    assert response.status_code == 204

    # Verify soft-delete (deleted_at is set)
    db_session.refresh(emb)
    assert emb.deleted_at is not None


@pytest.mark.unit
def test_delete_embedding_excludes_from_list(client, db_session):
    """Test: Deleted embedding doesn't appear in list."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="test-user-123",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    active_emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 1536,
    )
    deleted_emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.2] * 1536,
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([active_emb, deleted_emb])
    db_session.commit()

    response = client.get("/api/embeddings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == active_emb.id


@pytest.mark.unit
def test_semantic_search_endpoint_exists(client):
    """Test: POST /api/embeddings/search endpoint responds."""
    search_request = {
        "query_text": "test query",
        "top_k": 10,
    }
    response = client.post("/api/embeddings/search", json=search_request)

    # Should return 200 even if results are empty (placeholder implementation)
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "query_count" in data
