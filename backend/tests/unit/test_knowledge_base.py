"""Unit tests for Knowledge Base API - TDD discipline."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.auth import get_current_user
from app.db.models import Embedding, KnowledgeBase
from app.main import app


@pytest.mark.unit
def test_knowledge_base_model_creation(db_session):
    """Test: KnowledgeBase model can be created."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-123",
        title="Test Document",
        content="This is test content",
    )
    db_session.add(kb)
    db_session.commit()

    retrieved = db_session.query(KnowledgeBase).filter_by(user_id="user-123").first()
    assert retrieved is not None
    assert retrieved.title == "Test Document"
    assert retrieved.content == "This is test content"


@pytest.mark.unit
def test_knowledge_base_user_isolation(db_session):
    """Test: Knowledge bases are isolated per user."""
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

    user_a_docs = db_session.query(KnowledgeBase).filter_by(user_id="user-a").all()
    user_b_docs = db_session.query(KnowledgeBase).filter_by(user_id="user-b").all()

    assert len(user_a_docs) == 1
    assert len(user_b_docs) == 1
    assert user_a_docs[0].title == "Doc A"
    assert user_b_docs[0].title == "Doc B"


@pytest.mark.unit
def test_create_knowledge_base_success(client, db_session):
    """Test: POST /api/knowledge-base creates KB + embedding."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        payload = {
            "title": "My Document",
            "content": "This is the document content",
            "metadata": {"source": "test"},
        }

        response = client.post("/api/knowledge-base", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My Document"
        assert data["content"] == "This is the document content"
        assert data["user_id"] == "test-user-123"

        # Verify KB was stored
        kb = db_session.query(KnowledgeBase).filter_by(user_id="test-user-123").first()
        assert kb is not None

        # Verify embedding was created
        emb = db_session.query(Embedding).filter_by(doc_id=kb.id).first()
        assert emb is not None
        assert len(emb.embedding) == 1536
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_list_knowledge_base_success(client, db_session):
    """Test: GET /api/knowledge-base lists user's entries."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        # Create test entries
        kb1 = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Doc 1",
            content="Content 1",
        )
        kb2 = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Doc 2",
            content="Content 2",
        )
        db_session.add_all([kb1, kb2])
        db_session.commit()

        response = client.get("/api/knowledge-base")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        titles = {kb["title"] for kb in data}
        assert titles == {"Doc 1", "Doc 2"}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_get_knowledge_base_detail(client, db_session):
    """Test: GET /api/knowledge-base/{id} returns KB details."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Test Doc",
            content="Test content",
        )
        db_session.add(kb)
        db_session.commit()

        response = client.get(f"/api/knowledge-base/{kb.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == kb.id
        assert data["title"] == "Test Doc"
        assert data["content"] == "Test content"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_get_knowledge_base_not_found(client):
    """Test: GET /api/knowledge-base/{id} returns 404 for missing KB."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        response = client.get(f"/api/knowledge-base/{uuid4()}")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_update_knowledge_base_success(client, db_session):
    """Test: PUT /api/knowledge-base/{id} updates KB and regenerates embedding."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Old Title",
            content="Old content",
        )
        db_session.add(kb)
        db_session.commit()

        # Create embedding for original content
        embedding = Embedding(
            id=str(uuid4()),
            doc_id=kb.id,
            embedding=[0.1] * 1536,
        )
        db_session.add(embedding)
        db_session.commit()

        old_embedding = embedding.embedding[0]

        update_payload = {
            "title": "New Title",
            "content": "New content here",
            "metadata": {},
        }

        response = client.put(f"/api/knowledge-base/{kb.id}", json=update_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"
        assert data["content"] == "New content here"

        # Verify embedding was regenerated
        db_session.refresh(embedding)
        assert embedding.embedding[0] != old_embedding  # Should be different for different content
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_delete_knowledge_base_soft_delete(client, db_session):
    """Test: DELETE /api/knowledge-base/{id} soft-deletes KB and embeddings."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Test Doc",
            content="Test content",
        )
        db_session.add(kb)
        db_session.commit()

        # Create embedding
        embedding = Embedding(
            id=str(uuid4()),
            doc_id=kb.id,
            embedding=[0.1] * 1536,
        )
        db_session.add(embedding)
        db_session.commit()

        response = client.delete(f"/api/knowledge-base/{kb.id}")

        assert response.status_code == 204

        # Verify soft-delete
        db_session.refresh(kb)
        db_session.refresh(embedding)
        assert kb.deleted_at is not None
        assert embedding.deleted_at is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_get_knowledge_base_soft_deleted_returns_404(client, db_session):
    """Test: GET /api/knowledge-base/{id} returns 404 for a soft-deleted entry."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Test Doc",
            content="Test content",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(kb)
        db_session.commit()

        response = client.get(f"/api/knowledge-base/{kb.id}")

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_update_knowledge_base_soft_deleted_returns_404(client, db_session):
    """Test: PUT /api/knowledge-base/{id} returns 404 for a soft-deleted entry."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Test Doc",
            content="Test content",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(kb)
        db_session.commit()

        update_payload = {
            "title": "New Title",
            "content": "New content here",
            "metadata": {},
        }

        response = client.put(f"/api/knowledge-base/{kb.id}", json=update_payload)

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_delete_knowledge_base_soft_deleted_returns_404(client, db_session):
    """Test: DELETE /api/knowledge-base/{id} returns 404 for an already soft-deleted entry."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Test Doc",
            content="Test content",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(kb)
        db_session.commit()

        response = client.delete(f"/api/knowledge-base/{kb.id}")

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_delete_excludes_from_list(client, db_session):
    """Test: Deleted KB doesn't appear in list."""
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        active_kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Active",
            content="Active content",
        )
        db_session.add(active_kb)
        db_session.commit()

        # Delete one
        client.delete(f"/api/knowledge-base/{active_kb.id}")

        # List should be empty (or show nothing since we deleted the only one)
        response = client.get("/api/knowledge-base")
        data = response.json()
        assert len(data) == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_mock_embedding_deterministic(db_session):
    """Test: Mock embedding is deterministic (same text = same embedding)."""
    from app.services import generate_embedding

    text = "Hello world this is a test"
    emb1 = generate_embedding(text)
    emb2 = generate_embedding(text)

    assert emb1 == emb2
    assert len(emb1) == 1536


@pytest.mark.unit
def test_mock_embedding_different_for_different_text(db_session):
    """Test: Different text produces different embedding."""
    from app.services import generate_embedding

    emb1 = generate_embedding("Text A")
    emb2 = generate_embedding("Text B")

    assert emb1 != emb2
