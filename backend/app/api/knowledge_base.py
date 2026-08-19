"""API endpoints for Knowledge Base management."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse
from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import Embedding, KnowledgeBase
from app.services import generate_embedding

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])


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
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id=user["user_id"],
        title=payload.title,
        content=payload.content,
        doc_metadata=payload.metadata or {},
    )
    db.add(kb)
    db.flush()  # Flush to get the ID before creating embedding

    # Generate and store embedding
    embedding_vector = generate_embedding(payload.content)
    embedding = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=embedding_vector,
    )
    db.add(embedding)
    db.commit()
    db.refresh(kb)

    return _to_response(kb)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_base(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all knowledge base entries for the current user."""
    entries = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.user_id == user["user_id"],
            KnowledgeBase.deleted_at.is_(None),
        )
        .all()
    )

    return [_to_response(kb) for kb in entries]


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific knowledge base entry."""
    kb = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user["user_id"],
        )
        .first()
    )

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")

    return _to_response(kb)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a knowledge base entry and regenerate embedding."""
    kb = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user["user_id"],
        )
        .first()
    )

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")

    kb.title = payload.title
    kb.content = payload.content
    kb.doc_metadata = payload.metadata or {}
    kb.updated_at = datetime.now(timezone.utc)
    db.commit()

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
        embedding.embedding = generate_embedding(payload.content)
        embedding.updated_at = datetime.now(timezone.utc)
        db.commit()

    db.refresh(kb)
    return _to_response(kb)


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a knowledge base entry and its embeddings."""
    kb = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user["user_id"],
        )
        .first()
    )

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")

    # Soft-delete the knowledge base
    kb.deleted_at = datetime.now(timezone.utc)

    # Soft-delete associated embeddings
    embeddings = (
        db.query(Embedding)
        .filter(
            Embedding.doc_id == kb.id,
        )
        .all()
    )
    for emb in embeddings:
        emb.deleted_at = datetime.now(timezone.utc)

    db.commit()
