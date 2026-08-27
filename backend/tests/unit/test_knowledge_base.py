"""Unit tests for Knowledge Base API - TDD discipline."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.auth import get_current_user
from app.db.models import Embedding, KnowledgeBase
from app.main import app
from app.repositories import KnowledgeBaseRepository


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
def test_knowledge_base_model_stores_object_storage_fields(db_session):
    """Test: KnowledgeBase model persists storage_key/original_filename/content_type
    for a document backed by an uploaded file, alongside its extracted text.
    """
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-123",
        title="Uploaded Spec.pdf",
        content="Extracted text from the PDF",
        storage_key="user-123/doc-id/Uploaded Spec.pdf",
        original_filename="Uploaded Spec.pdf",
        content_type="application/pdf",
    )
    db_session.add(kb)
    db_session.commit()

    retrieved = db_session.query(KnowledgeBase).filter_by(user_id="user-123").first()
    assert retrieved is not None
    assert retrieved.storage_key == "user-123/doc-id/Uploaded Spec.pdf"
    assert retrieved.original_filename == "Uploaded Spec.pdf"
    assert retrieved.content_type == "application/pdf"


@pytest.mark.unit
def test_knowledge_base_model_storage_fields_default_to_none_for_typed_entries(db_session):
    """Test: pasted-text entries (no file upload) leave the storage fields NULL,
    not empty string - distinguishing "no file" from "file with no name".
    """
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-123",
        title="Typed Note",
        content="Just typed text",
    )
    db_session.add(kb)
    db_session.commit()

    retrieved = db_session.query(KnowledgeBase).filter_by(user_id="user-123").first()
    assert retrieved.storage_key is None
    assert retrieved.original_filename is None
    assert retrieved.content_type is None


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
        assert len(emb.embedding) == 768
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
            embedding=[0.1] * 768,
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
            embedding=[0.1] * 768,
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
def test_knowledge_base_repository_create_persists_storage_fields(db_session):
    """Test: KnowledgeBaseRepository.create() round-trips storage_key,
    original_filename, and content_type for a file-backed entry.
    """
    repo = KnowledgeBaseRepository(db_session)
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-1",
        title="spec.pdf",
        content="Extracted PDF text",
        storage_key="user-1/doc-1/spec.pdf",
        original_filename="spec.pdf",
        content_type="application/pdf",
    )

    created = repo.create(kb)
    db_session.commit()

    retrieved = db_session.query(KnowledgeBase).filter_by(id=created.id).first()
    assert retrieved.storage_key == "user-1/doc-1/spec.pdf"
    assert retrieved.original_filename == "spec.pdf"
    assert retrieved.content_type == "application/pdf"


@pytest.mark.unit
def test_mock_embedding_deterministic(db_session):
    """Test: Mock embedding is deterministic (same text = same embedding)."""
    from app.services import generate_embedding

    text = "Hello world this is a test"
    emb1 = generate_embedding(db_session, text)
    emb2 = generate_embedding(db_session, text)

    assert emb1.vector == emb2.vector
    assert len(emb1.vector) == 768


@pytest.mark.unit
def test_mock_embedding_different_for_different_text(db_session):
    """Test: Different text produces different embedding."""
    from app.services import generate_embedding

    emb1 = generate_embedding(db_session, "Text A")
    emb2 = generate_embedding(db_session, "Text B")

    assert emb1.vector != emb2.vector
