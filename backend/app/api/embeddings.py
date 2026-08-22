"""API endpoints for Embeddings management."""


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    EmbeddingResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSearchResult,
)
from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import Embedding, KnowledgeBase
from app.repositories import EmbeddingRepository
from app.services import generate_embedding

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
    query_embedding = generate_embedding(db, payload.query_text).vector

    repo = EmbeddingRepository(db)
    matches = repo.search_similar(user["user_id"], query_embedding, payload.top_k)

    results: list[SemanticSearchResult] = []
    for emb, kb, distance in matches:
        # Cosine distance is in [0, 2]; convert to a similarity score in [0, 1].
        similarity = 1 - (distance / 2)

        preview = kb.content[:150] + "..." if len(kb.content) > 150 else kb.content

        results.append(
            SemanticSearchResult(
                id=emb.id,
                doc_id=kb.id,
                title=kb.title,
                content=kb.content,
                preview=preview,
                similarity_score=similarity,
                created_at=emb.created_at.isoformat(),
                embed_metadata=emb.embed_metadata or {},
                doc_metadata=kb.doc_metadata or {},
            )
        )

    return SemanticSearchResponse(results=results, query_count=len(results))


@router.get("", response_model=list[EmbeddingResponse])
async def list_embeddings(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all embeddings for the current user."""
    repo = EmbeddingRepository(db)
    embedding_kb_pairs = repo.list_for_user(user["user_id"])

    return [_to_response(embedding, kb) for embedding, kb in embedding_kb_pairs]


@router.get("/{embedding_id}", response_model=EmbeddingResponse)
async def get_embedding(
    embedding_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific embedding (with knowledge base info)."""
    repo = EmbeddingRepository(db)
    embedding = repo.get_by_id(embedding_id, user["user_id"])

    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")

    kb = repo.get_knowledge_base_for_embedding(embedding_id)
    return _to_response(embedding, kb)


@router.put("/{embedding_id}", response_model=EmbeddingResponse)
async def update_embedding(
    embedding_id: str,
    payload: dict,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update embedding metadata."""
    repo = EmbeddingRepository(db)
    embedding = repo.get_by_id(embedding_id, user["user_id"])

    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")

    if "metadata" in payload:
        repo.update_metadata(embedding_id, payload["metadata"])
        db.commit()
        db.refresh(embedding)

    kb = repo.get_knowledge_base_for_embedding(embedding_id)
    return _to_response(embedding, kb)


@router.delete("/{embedding_id}", status_code=204)
async def delete_embedding(
    embedding_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete an embedding."""
    repo = EmbeddingRepository(db)
    embedding = repo.get_by_id(embedding_id, user["user_id"])

    if not embedding:
        raise HTTPException(status_code=404, detail="Embedding not found")

    repo.soft_delete(embedding_id)
    db.commit()
