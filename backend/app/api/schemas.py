"""API request/response schemas."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _as_utc_isoformat(value: datetime) -> str:
    """Serialize a datetime as ISO 8601 with an explicit UTC offset.

    Every timestamp column in app.db.models (see utc_now) stores a naive
    datetime that is UTC by convention, not by type - the DB round-trip
    strips the tzinfo a Python-side aware value had on write. Pydantic's
    default serialization of a naive datetime omits any offset, so a
    JS `new Date(...)` on the client parses it as local time rather than
    UTC, silently shifting every rendered timestamp by the viewer's UTC
    offset. Stamping the offset back on at the response boundary - where
    the naive-vs-aware convention is actually violated - fixes this without
    touching how every model or repository in the codebase handles time.
    """
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.isoformat()


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    response: str
    thread_id: str


class ThreadSummary(BaseModel):
    """One entry in a user's thread list."""

    id: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_utc(self, value: datetime) -> str:
        return _as_utc_isoformat(value)


class ThreadListResponse(BaseModel):
    """Response body for GET /api/agents/threads."""

    threads: list[ThreadSummary]


class ThreadMessage(BaseModel):
    """One rendered message in a thread's history."""

    role: str
    text: str


class ThreadHistoryResponse(BaseModel):
    """Response body for GET /api/agents/threads/{thread_id}."""

    id: str
    messages: list[ThreadMessage]


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


class ProviderOption(BaseModel):
    """One entry in a settings-screen provider dropdown."""

    provider: str
    url: str
    label: str
    requires_manual_entry: bool


class AuditLogEntry(BaseModel):
    """One entry in the audit trail."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_user_id: str
    action: str
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_utc(self, value: datetime) -> str:
        return _as_utc_isoformat(value)


class AuditLogResponse(BaseModel):
    """Response body for GET /api/settings/audit."""

    entries: list[AuditLogEntry]


class SystemSettingsResponse(BaseModel):
    """Response body for GET /api/settings.

    Never includes llm_api_key: it stays env-only, never persisted to the
    DB or returned over the API, so the settings screen can pick a
    provider/url/model but never inject credentials.
    """

    llm_provider: str
    llm_url: str
    llm_model: str
    llm_provider_is_db_override: bool
    llm_url_is_db_override: bool
    llm_model_is_db_override: bool
    embedding_provider: str
    embedding_url: str
    embedding_model: str
    embedding_provider_is_db_override: bool
    embedding_url_is_db_override: bool
    embedding_model_is_db_override: bool
    conversation_retention_hours: Optional[int] = None
    conversation_retention_hours_is_db_override: bool
    cleanup_on_logout: bool
    cleanup_on_logout_is_db_override: bool
    knowledge_base_purge_days: Optional[int] = None
    knowledge_base_purge_days_is_db_override: bool
    api_key_purge_days: Optional[int] = None
    api_key_purge_days_is_db_override: bool
    available_providers: dict[str, list[ProviderOption]]


class UpdateSettingsRequest(BaseModel):
    """Request body for PUT /api/settings.

    Any field omitted (or explicitly null) clears back to the env-var
    default, matching the nullable-column semantics of SystemSettings.
    """

    llm_provider: Optional[str] = None
    llm_url: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_url: Optional[str] = None
    embedding_model: Optional[str] = None
    # Retention windows. None clears back to the env default; 0 is a valid
    # "purge immediately" override, so the lower bound is 0, not 1.
    conversation_retention_hours: Optional[int] = Field(default=None, ge=0)
    cleanup_on_logout: Optional[bool] = None
    knowledge_base_purge_days: Optional[int] = Field(default=None, ge=0)
    api_key_purge_days: Optional[int] = Field(default=None, ge=0)
