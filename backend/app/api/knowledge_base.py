"""API endpoints for Knowledge Base management."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse
from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import Embedding, KnowledgeBase
from app.repositories import KnowledgeBaseRepository
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
    repo = KnowledgeBaseRepository(db)
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id=user["user_id"],
        title=payload.title,
        content=payload.content,
        doc_metadata=payload.metadata or {},
    )

    # Generate and store embedding, tagged with the provider/model that
    # produced it so a later runtime provider switch (Settings screen) is
    # detectable instead of silently mixing incompatible vectors.
    embedding_result = generate_embedding(db, payload.content)
    embedding = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=embedding_result.vector,
        embed_metadata={
            "embedding_provider": embedding_result.provider,
            "embedding_model": embedding_result.model,
        },
    )
    db.add(embedding)

    created = repo.create(kb)
    db.commit()
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
):
    """Update a knowledge base entry and regenerate embedding."""
    repo = KnowledgeBaseRepository(db)
    kb = repo.get_by_id(kb_id, user["user_id"])

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")

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
        embedding.embed_metadata = {
            "embedding_provider": embedding_result.provider,
            "embedding_model": embedding_result.model,
        }
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
    repo = KnowledgeBaseRepository(db)
    kb = repo.get_by_id(kb_id, user["user_id"])

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")

    repo.soft_delete_with_embeddings(kb)
    db.commit()
