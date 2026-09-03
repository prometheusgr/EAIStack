"""API request/response schemas."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.guardrails.input_guardrail import MAX_INPUT_LENGTH_CEILING


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


class SourceReference(BaseModel):
    """One knowledge-base document that grounded a chat response.

    Mirrors app.mcp_client.doc_search_client.Source, the structured
    provenance ToolMessage.artifact carries out of search_knowledge_base
    (see app.agents.chat_agent.extract_sources_from_messages) -- this is
    the API-facing copy of that shape, kept separate the same way every
    other internal/response schema pair in this file is (e.g.
    KnowledgeBaseResponse vs. the KnowledgeBase model).
    """

    knowledge_base_id: str
    title: str
    heading_path: Optional[str] = None


class ChatResponse(BaseModel):
    """Response body for chat endpoint."""

    response: str
    thread_id: str
    sources: list[SourceReference] = Field(default_factory=list)
    # Issue #46: whether the output guardrail altered this response before
    # it was returned (see app.services.chat_guardrail_service.
    # filter_agent_response). The redacted content itself is never exposed
    # here or anywhere else -- only the fact that a redaction happened, so
    # the user sees a factual signal rather than an indistinguishable
    # "the model didn't know this."
    was_modified: bool = False


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
    """Request body for creating (or updating - see PUT /{kb_id}) a knowledge
    base entry.
    """

    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    content: str = Field(..., min_length=1, description="Document content")
    metadata: dict = Field(default_factory=dict, description="Optional metadata")

    @field_validator("content")
    @classmethod
    def _reject_whitespace_only_content(cls, value: str) -> str:
        """min_length=1 alone lets whitespace-only content ("   ", "\\n\\n")
        through, since whitespace counts toward string length. Downstream,
        chunk_document strips such content to nothing and produces zero
        chunks, silently creating (or updating into) a document with no
        embeddings and no way to ever retrieve it - reject it here instead,
        at the boundary, rather than letting it reach the chunker.
        """
        if not value.strip():
            raise ValueError("content must not be empty or whitespace-only")
        return value


class KnowledgeBaseResponse(BaseModel):
    """Response body for a knowledge base entry."""

    id: str
    user_id: str
    title: str
    content: str
    doc_metadata: Optional[dict] = None
    created_at: str
    updated_at: str
    storage_key: Optional[str] = None
    original_filename: Optional[str] = None
    content_type: Optional[str] = None


class ProviderOption(BaseModel):
    """One entry in a settings-screen provider dropdown."""

    provider: str
    url: str
    label: str
    requires_manual_entry: bool


class TestConnectionRequest(BaseModel):
    """Body for POST /api/settings/test-connection."""

    url: str


class TestConnectionResponse(BaseModel):
    """Result of probing a provider URL's OpenAI-compatible /models endpoint.

    Always returned with a 200 status, success or failure alike -- see
    app.services.provider_probe_service.ProviderProbeResult and the
    test_connection endpoint's docstring for why this is a diagnostic
    result, not a request error.
    """

    ok: bool
    models: list[str]
    error: Optional[str] = None


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


class GuardrailPatternResponse(BaseModel):
    """One row from GuardrailPatternRepository, as returned to the settings
    screen.

    pattern_text is None for a built_in row (its regex stays in code, never
    exposed over the API) and holds the literal phrase for a custom row.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    label: str
    pattern_text: Optional[str] = None
    enabled: bool


class CreateGuardrailPatternRequest(BaseModel):
    """Request body for POST /api/settings/guardrail-patterns."""

    label: str = Field(..., min_length=1, max_length=255)
    pattern_text: str = Field(..., min_length=1, max_length=500)

    @field_validator("pattern_text")
    @classmethod
    def _reject_whitespace_only_pattern_text(cls, value: str) -> str:
        """min_length=1 alone lets a whitespace-only phrase ("   ", a single
        space) through, since whitespace counts toward string length. Unlike
        KnowledgeBaseCreate.content's equivalent guard (whitespace-only
        content silently produces zero chunks), the failure mode here is
        worse: check_input matches custom phrases as a case-insensitive
        substring, so a single-space phrase matches nearly every real chat
        message, turning the input guardrail into a de facto denial of
        service the moment it's saved. Reject it here, at the boundary,
        rather than letting it reach the guardrail pattern table at all.
        """
        if not value.strip():
            raise ValueError("pattern_text must not be empty or whitespace-only")
        return value


class UpdateGuardrailPatternRequest(BaseModel):
    """Request body for PUT /api/settings/guardrail-patterns/{pattern_id}.

    Toggle only -- editing a custom pattern's phrase text after creation is
    not in this issue's scope.
    """

    enabled: bool


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
    max_input_length: int
    max_input_length_is_db_override: bool
    guardrails_input_enabled: bool
    guardrails_input_enabled_is_db_override: bool
    guardrails_output_enabled: bool
    guardrails_output_enabled_is_db_override: bool
    guardrail_patterns: list[GuardrailPatternResponse]
    # LLM observability (issue #4). Unlike every other field above, a
    # change here requires a backend restart to take effect - see
    # app.services.tracing_config_service's module docstring - since it is
    # resolved once at process startup, not per-request.
    tracing_enabled: bool
    tracing_enabled_is_db_override: bool
    # Rate limiting (issue #25). Token-bucket capacity/refill for chat
    # (per-user) and auth (per-IP), plus one shared on/off switch - see
    # app.services.rate_limit_config_service.
    rate_limit_enabled: bool
    rate_limit_enabled_is_db_override: bool
    rate_limit_chat_capacity: int
    rate_limit_chat_capacity_is_db_override: bool
    rate_limit_chat_refill_per_minute: int
    rate_limit_chat_refill_per_minute_is_db_override: bool
    rate_limit_auth_capacity: int
    rate_limit_auth_capacity_is_db_override: bool
    rate_limit_auth_refill_per_minute: int
    rate_limit_auth_refill_per_minute_is_db_override: bool
    # Admin audit log viewer (issue #45). Transparent-by-default (True):
    # hides the in-product Audit Log nav entry/view for forks that route
    # audit consumption through an external SIEM instead.
    audit_log_ui_enabled: bool
    audit_log_ui_enabled_is_db_override: bool
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
    # Guardrail config. max_input_length's upper bound is imported directly
    # from app.guardrails.input_guardrail.MAX_INPUT_LENGTH_CEILING (the
    # module docstring there calls it "the one place that ceiling is
    # defined") rather than duplicated as a literal -- so a future change to
    # the ceiling can't silently drift out of sync with what this request
    # schema accepts. Enforced here, at the request boundary, so an
    # out-of-range value never reaches the service/DB layer at all.
    max_input_length: Optional[int] = Field(default=None, ge=1, le=MAX_INPUT_LENGTH_CEILING)
    guardrails_input_enabled: Optional[bool] = None
    guardrails_output_enabled: Optional[bool] = None
    # See SystemSettingsResponse.tracing_enabled: takes effect on the next
    # backend restart, not the next request.
    tracing_enabled: Optional[bool] = None
    # Rate limiting. Unlike retention's windows, 0 has no meaningful
    # interpretation for a bucket's capacity/refill rate (a zero-capacity
    # bucket would never allow anything), so these are bounded to >= 1
    # rather than >= 0.
    rate_limit_enabled: Optional[bool] = None
    rate_limit_chat_capacity: Optional[int] = Field(default=None, ge=1)
    rate_limit_chat_refill_per_minute: Optional[int] = Field(default=None, ge=1)
    rate_limit_auth_capacity: Optional[int] = Field(default=None, ge=1)
    rate_limit_auth_refill_per_minute: Optional[int] = Field(default=None, ge=1)
    # See SystemSettingsResponse.audit_log_ui_enabled: takes effect on the
    # next request, no restart required.
    audit_log_ui_enabled: Optional[bool] = None
