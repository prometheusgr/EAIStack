"""API endpoints for Embeddings management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from uuid import uuid4

from app.core.auth import get_current_user
from app.db.models import Embedding, KnowledgeBase
from app.db.database import get_db
from app.api.schemas import EmbeddingResponse, SemanticSearchRequest, SemanticSearchResponse

router = APIRouter(prefix="/api/embeddings", tags=["embeddings"])


def _to_response(embedding: Embedding, kb: KnowledgeBase | None = None) -> EmbeddingResponse:
    """Convert Embedding model to response DTO."""
    return EmbeddingResponse(
        id=embedding.id,
        doc_id=embedding.doc_id,
        embedding=embedding.embedding,
        embed_metadata=embedding.embed_metadata or {},
        created_at=embedding.created_at.isoformat(),
        updated_at=embedding.updated_at.isoformat(),
        deleted_at=embedding.deleted_at.isoformat() if embedding.deleted_at else None,
        title=kb.title if kb else None,
        content=kb.content if kb else None,
        doc_metadata=kb.doc_metadata if kb else None,
    )


@router.post("/search", response_model=SemanticSearchResponse)
async def search_embeddings(
    payload: SemanticSearchRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Perform semantic search using pgvector similarity."""
    # Placeholder: in a real implementation, this would:
    # 1. Generate embedding for the query text
    # 2. Use pgvector similarity search
    # 3. Return results ranked by similarity

    # For now, return empty results (will be implemented with real embedding generation)
    return SemanticSearchResponse(results=[], query_count=0)


@router.get("", response_model=list[EmbeddingResponse])
async def list_embeddings(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all embeddings for the current user."""
    embeddings = db.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(
        KnowledgeBase.user_id == user["user_id"],
        Embedding.deleted_at.is_(None),
    ).all()

    result = []
    for embedding in embeddings:
        kb = db.query(KnowledgeBase).filter(
            KnowledgeBase.id == embedding.doc_id
        ).first()
        result.append(_to_response(embedding, kb))

    return result


@router.get("/{embedding_id}", response_model=EmbeddingResponse)
async def get_embedding(
    embedding_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific embedding (with knowledge base info)."""
    embedding = db.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(
        Embedding.id == embedding_id,
        KnowledgeBase.user_id == user["user_id"],
    ).first()

    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")

    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == embedding.doc_id
    ).first()
    return _to_response(embedding, kb)


@router.put("/{embedding_id}", response_model=EmbeddingResponse)
async def update_embedding(
    embedding_id: str,
    payload: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update embedding metadata."""
    embedding = db.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(
        Embedding.id == embedding_id,
        KnowledgeBase.user_id == user["user_id"],
    ).first()

    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")

    if "metadata" in payload:
        embedding.embed_metadata = payload["metadata"]
        embedding.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(embedding)

    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == embedding.doc_id
    ).first()
    return _to_response(embedding, kb)


@router.delete("/{embedding_id}", status_code=204)
async def delete_embedding(
    embedding_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete an embedding."""
    embedding = db.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(
        Embedding.id == embedding_id,
        KnowledgeBase.user_id == user["user_id"],
    ).first()

    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")

    embedding.deleted_at = datetime.now(timezone.utc)
    db.commit()
