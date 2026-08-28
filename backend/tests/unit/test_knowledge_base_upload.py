"""Unit tests for POST /api/knowledge-base/upload - TDD discipline.

MinIO is an external boundary (per AGENTS.md), so these tests override the
app's DocumentStore dependency with a stand-in that records calls rather
than talking to a real server - the same pattern the LLM boundary uses
(FakeChatModel). Real MinIO interaction is covered separately by
tests/integration (testcontainers).
"""

from io import BytesIO

import pytest

from app.core.auth import get_current_user
from app.db.models import Embedding, KnowledgeBase
from app.main import app
from app.storage.dependencies import get_document_store
from app.storage.object_keys import build_object_key


class FakeDocumentStore:
    """Records uploads in memory instead of talking to MinIO.

    upload() delegates key construction to the real build_object_key, the
    same as DocumentStore.upload does - so a filename that build_object_key
    rejects (e.g. a path-traversal attempt) raises ValueError here too,
    exercising the endpoint's own handling of that error rather than a
    fake that always succeeds.
    """

    def __init__(self):
        self.uploads: list[dict] = []
        self.deleted_keys: list[str] = []

    def upload(self, *, user_id, kb_id, filename, data, length, content_type):
        key = build_object_key(user_id=user_id, kb_id=kb_id, filename=filename)
        content = data.read()
        self.uploads.append(
            {
                "user_id": user_id,
                "kb_id": kb_id,
                "filename": filename,
                "content": content,
                "length": length,
                "content_type": content_type,
            }
        )
        return key

    def delete(self, storage_key, *, user_id):
        self.deleted_keys.append(storage_key)

    def delete_many(self, storage_keys):
        self.deleted_keys.extend(storage_keys)


@pytest.fixture
def fake_document_store():
    store = FakeDocumentStore()
    app.dependency_overrides[get_document_store] = lambda: store
    yield store
    del app.dependency_overrides[get_document_store]


def _authed(client_user_id="test-user-123"):
    fake_user = {"user_id": client_user_id, "token": {}}
    app.dependency_overrides[get_current_user] = lambda: fake_user
    return fake_user


@pytest.mark.unit
def test_upload_plain_text_file_creates_knowledge_base_entry(
    client, db_session, fake_document_store
):
    """Test: uploading a .txt file creates a KnowledgeBase row with extracted
    text as content, stores the object in MinIO, and generates an embedding.
    """
    _authed()
    try:
        response = client.post(
            "/api/knowledge-base/upload",
            files={"file": ("notes.txt", BytesIO(b"Some plain text content"), "text/plain")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "notes.txt"
        assert data["content"] == "Some plain text content"
        assert data["original_filename"] == "notes.txt"
        assert data["content_type"] == "text/plain"
        assert data["storage_key"] == f"test-user-123/{data['id']}/notes.txt"

        kb = db_session.query(KnowledgeBase).filter_by(id=data["id"]).first()
        assert kb is not None
        assert kb.storage_key == f"test-user-123/{kb.id}/notes.txt"

        embedding = db_session.query(Embedding).filter_by(doc_id=kb.id).first()
        assert embedding is not None

        assert len(fake_document_store.uploads) == 1
        assert fake_document_store.uploads[0]["content"] == b"Some plain text content"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_rejects_missing_filename(client, fake_document_store):
    """Test: a multipart file part with no filename is rejected (FastAPI's
    own request validation, since UploadFile.filename is required) rather
    than reaching DocumentStore.upload with a None filename.
    """
    _authed()
    try:
        response = client.post(
            "/api/knowledge-base/upload",
            files={"file": ("", BytesIO(b"content"), "text/plain")},
        )

        assert response.status_code == 422
        assert len(fake_document_store.uploads) == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_rejects_unsupported_content_type(client, fake_document_store):
    """Test: an unsupported file type is rejected with 415, not embedded as
    garbage text. The response carries a human-readable `message` alongside
    the stable `detail` code, matching the guardrail rejection shape (see
    app.api.agents) - the frontend only ever displays `message`, never the
    internal `detail` string, verbatim to a user.
    """
    _authed()
    try:
        response = client.post(
            "/api/knowledge-base/upload",
            files={"file": ("virus.exe", BytesIO(b"\x00\x01\x02"), "application/x-executable")},
        )

        assert response.status_code == 415
        assert len(fake_document_store.uploads) == 0
        body = response.json()
        assert "message" in body
        assert "unsupported file type" in body["message"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_rejects_file_exceeding_size_limit(client, fake_document_store):
    """Test: a file larger than the configured limit is rejected at the
    boundary with 413, before text extraction or storage is attempted.
    """
    from app.core.config import settings

    _authed()
    try:
        oversized = b"a" * (settings.knowledge_base_upload_max_bytes + 1)
        response = client.post(
            "/api/knowledge-base/upload",
            files={"file": ("big.txt", BytesIO(oversized), "text/plain")},
        )

        assert response.status_code == 413
        assert len(fake_document_store.uploads) == 0
        assert "message" in response.json()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_scopes_object_key_to_caller_user_id(client, db_session, fake_document_store):
    """Test: the storage key is built from the authenticated caller's
    user_id, never from anything client-supplied - the structural
    isolation guarantee from docs/REPOSITORY_PATTERN.md applied to MinIO
    object paths.
    """
    _authed(client_user_id="user-a")
    try:
        response = client.post(
            "/api/knowledge-base/upload",
            files={"file": ("doc.txt", BytesIO(b"content"), "text/plain")},
        )

        assert response.status_code == 201
        assert fake_document_store.uploads[0]["user_id"] == "user-a"
        assert response.json()["storage_key"].startswith("user-a/")
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_pdf_extracts_text_before_storing(client, db_session, fake_document_store):
    """Test: a PDF upload's KnowledgeBase.content holds extracted text, not
    the raw PDF bytes.
    """
    from io import BytesIO as IO

    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, StreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    content_stream = StreamObject()
    content_stream.set_data(b"BT /F1 24 Tf 10 100 Td (Extracted PDF text) Tj ET")
    page[NameObject("/Contents")] = content_stream
    buf = IO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    _authed()
    try:
        response = client.post(
            "/api/knowledge-base/upload",
            files={"file": ("report.pdf", BytesIO(pdf_bytes), "application/pdf")},
        )

        assert response.status_code == 201
        data = response.json()
        assert "Extracted PDF text" in data["content"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_accepts_filename_containing_literal_dot_dot(
    client, db_session, fake_document_store
):
    """Test: a legitimate filename that merely contains the substring ".."
    (e.g. "report..final.pdf") uploads successfully - it is not a
    path-traversal attempt, just a filename with two dots in it (see
    app.storage.object_keys.build_object_key).
    """
    _authed()
    try:
        response = client.post(
            "/api/knowledge-base/upload",
            files={"file": ("report..final.pdf", BytesIO(b"content"), "text/plain")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "report..final.pdf"
        assert len(fake_document_store.uploads) == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_rejects_path_traversal_filename_with_clean_4xx(
    client, db_session, fake_document_store
):
    """Test: an actual path-traversal filename is rejected with a clean 4xx
    response, not an unhandled 500 - build_object_key's ValueError must be
    caught by the endpoint rather than propagating past it.
    """
    _authed()
    try:
        response = client.post(
            "/api/knowledge-base/upload",
            files={"file": ("../../etc/passwd", BytesIO(b"content"), "text/plain")},
        )

        assert response.status_code == 400
        body = response.json()
        assert "message" in body
        assert len(fake_document_store.uploads) == 0
        assert db_session.query(KnowledgeBase).count() == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_deletes_orphaned_object_when_embedding_generation_fails(
    client, db_session, fake_document_store, monkeypatch
):
    """Test: if the MinIO upload succeeds but a later step (embedding
    generation) fails, the just-uploaded object is deleted rather than left
    as a permanent orphan with no KnowledgeBase row ever pointing at it -
    the retention sweep can only ever purge objects it can reach via a
    storage_key column, so a row that's never created means the object
    would otherwise never be cleaned up.
    """
    import app.api.knowledge_base as knowledge_base_module

    def _boom(db, kb, text):
        raise RuntimeError("embedding service unavailable")

    monkeypatch.setattr(knowledge_base_module, "generate_and_attach_embedding", _boom)

    _authed()
    try:
        with pytest.raises(RuntimeError):
            client.post(
                "/api/knowledge-base/upload",
                files={"file": ("notes.txt", BytesIO(b"content"), "text/plain")},
            )

        assert len(fake_document_store.uploads) == 1
        # The kb_id is server-generated and not observable ahead of time, so
        # assert by key equality against what was actually stored, rather
        # than reconstructing it independently.
        uploaded = fake_document_store.uploads[0]
        actual_key = f"{uploaded['user_id']}/{uploaded['kb_id']}/{uploaded['filename']}"
        assert fake_document_store.deleted_keys == [actual_key]

        assert db_session.query(KnowledgeBase).count() == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
def test_upload_cleanup_failure_does_not_mask_the_original_exception(
    client, db_session, fake_document_store, monkeypatch
):
    """Test: if the compensating document_store.delete() call (run when an
    error after upload forces a rollback) itself raises, the ORIGINAL
    exception must still be what propagates - not the cleanup failure. A
    cleanup exception replacing the real root cause would hide why the
    request actually failed (e.g. "embedding service unavailable") behind
    an unrelated MinIO error, making the failure much harder to diagnose.
    """
    import app.api.knowledge_base as knowledge_base_module

    def _embedding_boom(db, kb, text):
        raise RuntimeError("embedding service unavailable")

    def _cleanup_boom(storage_key, *, user_id):
        raise ConnectionError("MinIO transiently unreachable")

    monkeypatch.setattr(knowledge_base_module, "generate_and_attach_embedding", _embedding_boom)
    monkeypatch.setattr(fake_document_store, "delete", _cleanup_boom)

    _authed()
    try:
        with pytest.raises(RuntimeError, match="embedding service unavailable"):
            client.post(
                "/api/knowledge-base/upload",
                files={"file": ("notes.txt", BytesIO(b"content"), "text/plain")},
            )

        assert db_session.query(KnowledgeBase).count() == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
