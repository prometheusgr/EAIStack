"""API request/response schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    response: str
    thread_id: str


class APIKeyCreate(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(..., description="API provider (openai, anthropic, huggingface, custom)")
    secret_value: str = Field(..., min_length=1, description="The secret API key")


class APIKeyUpdate(BaseModel):
    """Request body for updating an API key (name/provider only, secret is immutable)."""

    name: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(..., description="API provider (openai, anthropic, huggingface, custom)")


class APIKeyResponse(BaseModel):
    """Response body for API key (never includes full secret)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    provider: str
    secret_value_masked: str = Field(..., description="Masked version of the secret")
    created_at: datetime
    updated_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class EmbeddingResponse(BaseModel):
    """Response body for an embedding."""

    id: str
    doc_id: str
    embedding: list[float]
    embed_metadata: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str
    deleted_at: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    doc_metadata: Optional[dict] = None


class SemanticSearchRequest(BaseModel):
    """Request body for semantic search."""

    query_text: str = Field(..., min_length=1, description="The search query")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


class SemanticSearchResult(BaseModel):
    """A single result from semantic search."""

    id: str
    doc_id: str
    title: str
    content: str
    preview: str
    similarity_score: float
    created_at: str
    embed_metadata: Optional[dict] = None
    doc_metadata: Optional[dict] = None


class SemanticSearchResponse(BaseModel):
    """Response body for semantic search."""

    results: list[SemanticSearchResult]
    query_count: int


class KnowledgeBaseCreate(BaseModel):
    """Request body for creating a knowledge base entry."""

    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    content: str = Field(..., min_length=1, description="Document content")
    metadata: dict = Field(default_factory=dict, description="Optional metadata")


class KnowledgeBaseResponse(BaseModel):
    """Response body for a knowledge base entry."""

    id: str
    user_id: str
    title: str
    content: str
    doc_metadata: Optional[dict] = None
    created_at: str
    updated_at: str
