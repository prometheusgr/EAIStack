"""API endpoints for Knowledge Base management."""

import io
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse
from app.core.auth import get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Embedding, KnowledgeBase
from app.repositories import KnowledgeBaseRepository
from app.services import generate_and_attach_embedding, generate_embedding
from app.storage.dependencies import get_document_store
from app.storage.document_store import DocumentStore
from app.storage.text_extraction import UnsupportedContentTypeError, extract_text

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])
logger = logging.getLogger(__name__)


def _to_response(kb: KnowledgeBase) -> KnowledgeBaseResponse:
    """Convert KnowledgeBase model to response DTO."""
    return KnowledgeBaseResponse(
        id=kb.id,
        user_id=kb.user_id,
        title=kb.title,
        content=kb.content,
        doc_metadata=kb.doc_metadata or {},
        created_at=kb.created_at.isoformat(),
        updated_at=kb.updated_at.isoformat(),
        storage_key=kb.storage_key,
        original_filename=kb.original_filename,
        content_type=kb.content_type,
    )


@router.post("", status_code=201, response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new knowledge base entry with auto-generated embeddings.

    - Creates a KnowledgeBase record
    - Generates a mock embedding for the content
    - Returns the created knowledge base
    """
    repo = KnowledgeBaseRepository(db)
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id=user["user_id"],
        title=payload.title,
        content=payload.content,
        doc_metadata=payload.metadata or {},
    )

    generate_and_attach_embedding(db, kb, payload.content)

    created = repo.create(kb)
    db.commit()
    db.refresh(created)
    return _to_response(created)


@router.post("/upload", status_code=201, response_model=KnowledgeBaseResponse)
async def upload_knowledge_base_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    document_store: DocumentStore = Depends(get_document_store),
):
    """Create a knowledge base entry from an uploaded file.

    - Validates content type and size at the boundary, before reading the
      full file into memory or attempting extraction.
    - Extracts searchable text from the file (PDF, DOCX, or plain text) and
      stores it as `content`, exactly as the paste-text flow does - the
      rest of the ingestion/search pipeline (embedding, semantic search)
      doesn't need to know a document came from a file upload.
    - Stores the original file bytes in MinIO under a key scoped to the
      caller's own user_id (see app.storage.object_keys), never a
      client-supplied path.
    """
    if file.content_type not in settings.knowledge_base_upload_allowed_content_types:
        return JSONResponse(
            status_code=415,
            content={
                "detail": "unsupported_content_type",
                "message": f"Unsupported file type: {file.content_type}",
            },
        )

    max_bytes = settings.knowledge_base_upload_max_bytes
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "detail": "file_too_large",
                "message": f"File exceeds the maximum allowed size of {max_bytes} bytes",
            },
        )

    try:
        # extract_text is CPU-bound (PDF/DOCX parsing); running it inline
        # would block the event loop for its full duration under concurrent
        # load, so it runs in the threadpool like the MinIO upload below.
        extracted_text = await run_in_threadpool(extract_text, data, content_type=file.content_type)
    except UnsupportedContentTypeError as e:
        return JSONResponse(
            status_code=415,
            content={"detail": "unsupported_content_type", "message": str(e)},
        )

    # FastAPI's own request validation rejects a multipart file part with no
    # filename (422) before this handler runs, so filename is always a str
    # here - this assertion documents that guarantee for mypy rather than
    # re-validating something the framework already enforced.
    assert file.filename is not None

    repo = KnowledgeBaseRepository(db)
    kb_id = str(uuid4())
    try:
        # document_store.upload is blocking MinIO network I/O; run it in the
        # threadpool for the same reason extract_text is above - inline, it
        # would block the event loop for the full duration of the upload.
        storage_key = await run_in_threadpool(
            document_store.upload,
            user_id=user["user_id"],
            kb_id=kb_id,
            filename=file.filename,
            data=io.BytesIO(data),
            length=len(data),
            content_type=file.content_type,
        )
    except ValueError as e:
        # Raised by build_object_key (see app.storage.object_keys) for a
        # filename it cannot safely turn into an object key - e.g. a
        # path-traversal attempt, or an empty filename. No MinIO object was
        # written in this case, so there is nothing to clean up, unlike the
        # try/except below.
        return JSONResponse(
            status_code=400,
            content={"detail": "invalid_filename", "message": str(e)},
        )

    # From here on, the MinIO object already exists. If anything below
    # fails, no KnowledgeBase row is ever created to reference it, and the
    # retention sweep only ever finds objects via a row's storage_key - so
    # a failure here would otherwise leak the object in MinIO forever.
    # Delete it and let the original exception propagate as a 500.
    try:
        kb = KnowledgeBase(
            id=kb_id,
            user_id=user["user_id"],
            title=file.filename,
            content=extracted_text,
            storage_key=storage_key,
            original_filename=file.filename,
            content_type=file.content_type,
            doc_metadata={},
        )

        generate_and_attach_embedding(db, kb, extracted_text)

        created = repo.create(kb)
        db.commit()
    except Exception:
        db.rollback()
        # The compensating delete must never let its own failure (e.g. MinIO
        # transiently unreachable) replace the exception actually being
        # handled - that would mask the real root cause of the request
        # failure behind an unrelated cleanup error. Log the cleanup failure
        # so the orphaned object is still discoverable, then always
        # re-raise the original exception via the bare `raise` below.
        try:
            document_store.delete(storage_key, user_id=user["user_id"])
        except Exception:
            logger.exception(
                "Failed to clean up orphaned MinIO object %r after upload failure", storage_key
            )
        raise

    db.refresh(created)
    return _to_response(created)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_base(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all knowledge base entries for the current user."""
    repo = KnowledgeBaseRepository(db)
    entries = repo.get_by_user(user["user_id"])

    return [_to_response(kb) for kb in entries]


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific knowledge base entry."""
    repo = KnowledgeBaseRepository(db)
    kb = repo.get_by_id(kb_id, user["user_id"])

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")

    return _to_response(kb)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    document_store: DocumentStore = Depends(get_document_store),
):
    """Update a knowledge base entry and regenerate embedding.

    A file-backed entry (non-null storage_key) that gets its content
    hand-edited here is no longer backed by the originally uploaded file -
    KnowledgeBaseRepository.update clears storage_key/original_filename/
    content_type on the row for exactly this reason. The now-orphaned MinIO
    object is deleted after that DB change is committed (see the ordering
    rationale on the upload endpoint's own compensating delete above): if
    the DB commit were to fail, the object must still exist to match the
    still-file-backed row a rollback would leave in place.
    """
    repo = KnowledgeBaseRepository(db)
    kb = repo.get_by_id(kb_id, user["user_id"])

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")

    previous_storage_key = kb.storage_key

    repo.update(kb, payload.title, payload.content, payload.metadata or {})

    # Update embedding if content changed
    embedding = (
        db.query(Embedding)
        .filter(
            Embedding.doc_id == kb.id,
            Embedding.deleted_at.is_(None),
        )
        .first()
    )

    if embedding:
        embedding_result = generate_embedding(db, payload.content)
        embedding.embedding = embedding_result.vector
        embedding.embed_metadata = embedding_result.as_embed_metadata()
        embedding.updated_at = datetime.now(timezone.utc)

    db.commit()

    if previous_storage_key is not None:
        document_store.delete(previous_storage_key, user_id=user["user_id"])
    db.refresh(kb)
    return _to_response(kb)


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a knowledge base entry and its embeddings."""
    repo = KnowledgeBaseRepository(db)
    kb = repo.get_by_id(kb_id, user["user_id"])

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")

    repo.soft_delete_with_embeddings(kb)
    db.commit()
