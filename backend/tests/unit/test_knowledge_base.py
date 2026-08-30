"""Unit tests for Knowledge Base API - TDD discipline."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.auth import get_current_user
from app.db.models import Embedding, KnowledgeBase
from app.main import app
from app.repositories import KnowledgeBaseRepository
from app.storage.dependencies import get_document_store


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
def test_create_knowledge_base_rejects_whitespace_only_content(client, db_session):
    """Test: POST /api/knowledge-base rejects content that is whitespace-only.

    min_length=1 alone lets "   " or "\\n\\n" through, since whitespace counts
    toward string length - chunk_document then strips it to nothing and
    produces zero chunks, silently creating a document with no embeddings
    and no way to retrieve it. Reject it at the API boundary instead.
    """
    fake_user = {"user_id": "test-user-123", "token": {}}

    def override_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        payload = {"title": "Empty Document", "content": "   \n\n  "}

        response = client.post("/api/knowledge-base", json=payload)

        assert response.status_code == 422
        kb = db_session.query(KnowledgeBase).filter_by(user_id="test-user-123").first()
        assert kb is None
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
    """Test: PUT /api/knowledge-base/{id} updates KB and regenerates embedding.

    The original Embedding row is soft-deleted (not updated in place) and a
    fresh row is inserted for the new content - see replace_embeddings,
    which replaces the chunk set wholesale since the old and new content
    can chunk into a different number of passages.
    """
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

        db_session.refresh(embedding)
        assert embedding.deleted_at is not None

        active_embedding = (
            db_session.query(Embedding)
            .filter(Embedding.doc_id == kb.id, Embedding.deleted_at.is_(None))
            .first()
        )
        assert active_embedding is not None
        assert active_embedding.id != embedding.id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_update_knowledge_base_reembeds_with_document_prefix(client, db_session, monkeypatch):
    """PUT /api/knowledge-base/{id} regenerates the embedding via
    replace_embeddings (chunk + re-embed), so the new content's chunk(s)
    must carry the "search_document: " prefix, with title + heading path
    context prepended (see chunking_service.Chunk.embed_text), not the bare
    updated content.
    """
    from unittest.mock import MagicMock, patch

    from app.core.config import settings

    fake_user = {"user_id": "test-user-123", "token": {}}
    app.dependency_overrides[get_current_user] = lambda: fake_user

    monkeypatch.setattr(settings, "embedding_provider", "llama-cpp")
    monkeypatch.setattr(settings, "embedding_url", "http://localhost:8002/v1")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text-v1.5.Q4_K_M.gguf")

    try:
        kb = KnowledgeBase(
            id=str(uuid4()), user_id="test-user-123", title="Old Title", content="Old content"
        )
        db_session.add(kb)
        db_session.commit()

        embedding = Embedding(id=str(uuid4()), doc_id=kb.id, embedding=[0.1] * 768)
        db_session.add(embedding)
        db_session.commit()

        fake_vector = [0.01 * i for i in range(768)]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={"data": [{"embedding": fake_vector, "index": 0}]}
        )
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.embedding_service.httpx.Client") as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.post = MagicMock(return_value=mock_response)
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=None)
            mock_client_class.return_value = mock_client_instance

            response = client.put(
                f"/api/knowledge-base/{kb.id}",
                json={"title": "Old Title", "content": "New content here", "metadata": {}},
            )

            assert response.status_code == 200
            call_args = mock_client_instance.post.call_args
            assert call_args.kwargs["json"]["input"] == [
                "search_document: Old Title\n\nNew content here"
            ]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_update_knowledge_base_replaces_chunk_set_when_chunk_count_changes(client, db_session):
    """PUT /api/knowledge-base/{id} soft-deletes the old chunk rows and
    inserts a fresh set matching the new content's chunking, rather than
    updating a single row in place - the old and new content can chunk
    into a different number of passages.
    """
    fake_user = {"user_id": "test-user-123", "token": {}}
    app.dependency_overrides[get_current_user] = lambda: fake_user

    try:
        kb = KnowledgeBase(
            id=str(uuid4()), user_id="test-user-123", title="Doc", content="Old content"
        )
        db_session.add(kb)
        db_session.commit()

        old_embedding = Embedding(
            id=str(uuid4()), doc_id=kb.id, embedding=[0.1] * 768, chunk_index=0
        )
        db_session.add(old_embedding)
        db_session.commit()

        response = client.put(
            f"/api/knowledge-base/{kb.id}",
            json={
                "title": "Doc",
                "content": "# Section A\n\nBody A.\n\n# Section B\n\nBody B.\n",
                "metadata": {},
            },
        )

        assert response.status_code == 200

        db_session.refresh(old_embedding)
        assert old_embedding.deleted_at is not None

        active_chunks = (
            db_session.query(Embedding)
            .filter(Embedding.doc_id == kb.id, Embedding.deleted_at.is_(None))
            .order_by(Embedding.chunk_index)
            .all()
        )
        assert len(active_chunks) == 2
        assert [c.heading_path for c in active_chunks] == ["Section A", "Section B"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_replace_embeddings_stamps_deleted_at_with_injected_now(db_session, now_fixed):
    """replace_embeddings must accept `now: datetime` and use it to stamp
    deleted_at, per AGENTS.md's time-injection pattern (see
    docs/TIME_INJECTION.md) - not call datetime.now() internally, which
    would make the exact soft-delete timestamp untestable without
    monkeypatching datetime.
    """
    from app.services.embedding_service import replace_embeddings

    kb = KnowledgeBase(id=str(uuid4()), user_id="test-user-123", title="Doc", content="Old")
    db_session.add(kb)
    db_session.commit()

    old_embedding = Embedding(id=str(uuid4()), doc_id=kb.id, embedding=[0.1] * 768, chunk_index=0)
    db_session.add(old_embedding)
    db_session.commit()

    replace_embeddings(db_session, kb, "New content", now=now_fixed)
    db_session.commit()

    db_session.refresh(old_embedding)
    # The DB round-trip strips tzinfo (see app.api.schemas._as_utc_isoformat's
    # docstring: every timestamp column stores a naive datetime that is UTC
    # by convention, not by type) - compare the naive value.
    assert old_embedding.deleted_at == now_fixed.replace(tzinfo=None)


@pytest.mark.unit
def test_update_knowledge_base_clears_stale_file_metadata_and_deletes_object(client, db_session):
    """Test: PUT on a file-backed entry (non-null storage_key) clears
    storage_key/original_filename/content_type, since the row's content is
    now hand-edited text disconnected from the originally uploaded file,
    and deletes the now-orphaned MinIO object - otherwise the row would
    keep claiming to be backed by a file whose bytes no longer match the
    DB content.
    """
    fake_user = {"user_id": "test-user-123", "token": {}}
    app.dependency_overrides[get_current_user] = lambda: fake_user

    class FakeDocumentStore:
        def __init__(self):
            self.deleted: list[tuple[str, str]] = []

        def delete(self, storage_key, *, user_id):
            self.deleted.append((storage_key, user_id))

    fake_document_store = FakeDocumentStore()
    app.dependency_overrides[get_document_store] = lambda: fake_document_store

    try:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="spec.pdf",
            content="Extracted PDF text",
            storage_key="test-user-123/doc-1/spec.pdf",
            original_filename="spec.pdf",
            content_type="application/pdf",
        )
        db_session.add(kb)
        db_session.commit()

        update_payload = {
            "title": "Hand-edited title",
            "content": "Hand-edited content, no longer matches the PDF",
            "metadata": {},
        }

        response = client.put(f"/api/knowledge-base/{kb.id}", json=update_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["storage_key"] is None
        assert data["original_filename"] is None
        assert data["content_type"] is None

        db_session.refresh(kb)
        assert kb.storage_key is None
        assert kb.original_filename is None
        assert kb.content_type is None

        assert fake_document_store.deleted == [("test-user-123/doc-1/spec.pdf", "test-user-123")]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_update_knowledge_base_leaves_typed_entry_storage_fields_alone(client, db_session):
    """Test: PUT on an entry with no storage_key (never file-backed) does not
    attempt to delete anything from object storage - there is no object to
    clean up, and calling the document store with a None key would be a
    bug, not a no-op.
    """
    fake_user = {"user_id": "test-user-123", "token": {}}
    app.dependency_overrides[get_current_user] = lambda: fake_user

    class FakeDocumentStore:
        def __init__(self):
            self.deleted: list[tuple[str, str]] = []

        def delete(self, storage_key, *, user_id):
            self.deleted.append((storage_key, user_id))

    fake_document_store = FakeDocumentStore()
    app.dependency_overrides[get_document_store] = lambda: fake_document_store

    try:
        kb = KnowledgeBase(
            id=str(uuid4()),
            user_id="test-user-123",
            title="Typed note",
            content="Just typed text",
        )
        db_session.add(kb)
        db_session.commit()

        update_payload = {
            "title": "Updated typed note",
            "content": "Updated typed content",
            "metadata": {},
        }

        response = client.put(f"/api/knowledge-base/{kb.id}", json=update_payload)

        assert response.status_code == 200
        assert fake_document_store.deleted == []
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


@pytest.mark.unit
def test_generate_and_attach_embeddings_stages_one_embedding_for_short_content(db_session):
    """Test: generate_and_attach_embeddings() stages an Embedding row linked
    to the given KnowledgeBase's id, tagged with the provider/model
    provenance, without committing - shared by both the paste-text and
    file-upload creation paths (see app.api.knowledge_base), which is why
    this logic lives in the service layer per docs/BACKEND_SERVICES.md
    rather than as a private helper in the API module.

    Content short enough to be one chunk (see app.services.chunking_service)
    stages exactly one Embedding row, matching the pre-chunking shape.
    """
    from app.services import generate_and_attach_embeddings

    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-1",
        title="Doc",
        content="Some content",
    )
    db_session.add(kb)
    db_session.flush()

    generate_and_attach_embeddings(db_session, kb, "Some content")

    staged = db_session.query(Embedding).filter_by(doc_id=kb.id).all()
    assert len(staged) == 1
    assert len(staged[0].embedding) == 768
    assert staged[0].embed_metadata["embedding_provider"] == "fake"
    assert staged[0].chunk_index == 0
    assert staged[0].chunk_text == "Some content"


@pytest.mark.unit
def test_generate_and_attach_embeddings_stages_one_row_per_chunk_for_long_content(db_session):
    """Test: content long enough to be split into multiple chunks
    (app.services.chunking_service.chunk_document) stages one Embedding row
    per chunk, each carrying its own chunk_index/chunk_text/heading_path.
    """
    from app.services import generate_and_attach_embeddings
    from app.services.chunking_service import MAX_CHUNK_TOKENS

    long_paragraph = " ".join(f"word{i}" for i in range(MAX_CHUNK_TOKENS * 3))
    content = f"# Big Section\n\n{long_paragraph}\n"

    kb = KnowledgeBase(id=str(uuid4()), user_id="user-1", title="Big Doc", content=content)
    db_session.add(kb)
    db_session.flush()

    generate_and_attach_embeddings(db_session, kb, content)

    staged = (
        db_session.query(Embedding).filter_by(doc_id=kb.id).order_by(Embedding.chunk_index).all()
    )
    assert len(staged) > 1
    assert [row.chunk_index for row in staged] == list(range(len(staged)))
    assert all(row.heading_path == "Big Section" for row in staged)
    assert all(row.chunk_text for row in staged)


@pytest.mark.unit
def test_generate_and_attach_embeddings_embeds_title_and_heading_path_context(
    db_session, monkeypatch
):
    """Each chunk is embedded with its title + heading path prepended
    (Chunk.embed_text), then the "search_document: " prefix - not the bare
    chunk text - so retrieval benefits from the section context a chunk
    loses when extracted on its own.
    """
    from unittest.mock import MagicMock, patch

    from app.core.config import settings
    from app.services import generate_and_attach_embeddings

    monkeypatch.setattr(settings, "embedding_provider", "llama-cpp")
    monkeypatch.setattr(settings, "embedding_url", "http://localhost:8002/v1")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text-v1.5.Q4_K_M.gguf")

    content = "# TLS\n\nRotate certs every 90 days.\n"
    kb = KnowledgeBase(id=str(uuid4()), user_id="user-1", title="Deployment Guide", content=content)
    db_session.add(kb)
    db_session.flush()

    fake_vector = [0.01 * i for i in range(768)]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"data": [{"embedding": fake_vector, "index": 0}]})
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.embedding_service.httpx.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post = MagicMock(return_value=mock_response)
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client_instance

        generate_and_attach_embeddings(db_session, kb, content)

        call_args = mock_client_instance.post.call_args
        assert call_args.kwargs["json"]["input"] == [
            "search_document: Deployment Guide > TLS\n\nRotate certs every 90 days."
        ]


@pytest.mark.unit
def test_generate_and_attach_embeddings_uses_document_prefix_for_untitled_heading(
    db_session, monkeypatch
):
    """generate_and_attach_embeddings is the shared index-time write path
    (both the paste-text and file-upload creation flows go through it), so
    the "search_document: " prefix nomic-embed-text-v1.5 expects at index
    time (see docs/LLM_SETUP.md) must be applied here structurally, not left
    for each call site to remember - even for content with no markdown
    heading at all (heading_path=None, so embed_text is just title + text).
    """
    from unittest.mock import MagicMock, patch

    from app.core.config import settings
    from app.services import generate_and_attach_embeddings

    monkeypatch.setattr(settings, "embedding_provider", "llama-cpp")
    monkeypatch.setattr(settings, "embedding_url", "http://localhost:8002/v1")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text-v1.5.Q4_K_M.gguf")

    kb = KnowledgeBase(id=str(uuid4()), user_id="user-1", title="Doc", content="Some content")
    db_session.add(kb)
    db_session.flush()

    fake_vector = [0.01 * i for i in range(768)]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"data": [{"embedding": fake_vector, "index": 0}]})
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.embedding_service.httpx.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post = MagicMock(return_value=mock_response)
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client_instance

        generate_and_attach_embeddings(db_session, kb, "Some content")

        call_args = mock_client_instance.post.call_args
        assert call_args.kwargs["json"]["input"] == ["search_document: Doc\n\nSome content"]
