"""Application configuration."""

from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # FastAPI
    app_name: str = "EAIStack Backend"
    debug: bool = False
    cors_origins: List[str] = ["http://localhost:3000"]

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/eaistack"

    # MinIO
    minio_url: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documents"

    # LLM Provider
    llm_provider: str = "fake"  # "fake" | "llama-cpp" | "openai-compatible"
    llm_url: str = "http://localhost:8000/v1"
    llm_model: str = "llama-2"
    llm_api_key: str | None = None
    enable_streaming: bool = True
    llm_timeout: int = 120

    # Embedding provider. Runs as a separate llama-server instance/port from
    # the chat LLM above, since embedding and chat models are different
    # weights loaded by different server processes.
    embedding_provider: str = "fake"  # "fake" | "llama-cpp"
    embedding_url: str = "http://localhost:8002/v1"
    embedding_model: str = "nomic-embed-text-v1.5.Q4_K_M.gguf"
    embedding_timeout: int = 60

    # LLM observability (Phoenix, issue #4). Off by default — set via
    # TRACING_ENABLED so unit tests (and any deployment that doesn't opt in)
    # never construct a real OTel exporter.
    #
    # tracing_enabled IS DB-backed (an admin can override it via the
    # settings screen — see app.services.tracing_config_service), but
    # unlike llm_provider it is resolved only once, at process startup
    # (app.main's lifespan hook calls resolve_tracing_config before
    # app.core.tracing.configure_tracing runs), not per-request: there is
    # no supported way to re-instrument a LangChainInstrumentor/OTel tracer
    # provider on a running process. A change via the settings screen is
    # therefore honored only after the next backend restart — the settings
    # UI says so explicitly, since this is the one override in this table
    # that doesn't take effect immediately like its siblings.
    #
    # tracing_otlp_endpoint stays env-only (out of scope for the DB-override
    # work): where traces are shipped is deployment topology, not a runtime
    # policy an admin should be able to redirect at will.
    tracing_enabled: bool = False
    tracing_otlp_endpoint: str = "http://localhost:6006/v1/traces"

    # doc-search MCP server (mcp-servers/doc-search): a standalone Streamable
    # HTTP service exposing search_knowledge_base as an MCP tool, so it can
    # run as its own K8s pod. The backend forwards each caller's own Keycloak
    # access token on every call (see app.mcp_client.doc_search_client) — the
    # server never trusts a bare user_id from this service.
    doc_search_mcp_url: str = "http://localhost:8100/mcp"

    # Keycloak (OIDC)
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "eaistack"
    keycloak_client_id: str = "eaistack-api"
    keycloak_web_client_id: str = "eaistack-web"
    #
    # This value is NOT a production secret — it is the plaintext client
    # secret baked into infra/keycloak/realm-import.json, the dev-only
    # Keycloak realm seed that `docker-compose up` imports, and it must
    # match that file exactly or local auth breaks. The documented
    # local-dev flow (docs/TESTING_QUICK_START.md) never sets
    # KEYCLOAK_CLIENT_SECRET, so removing this default outright would break
    # `docker-compose up` for every contributor.
    #
    # Every real deployment path overrides this: the Helm chart's
    # secret.yaml/deployment.yaml (infra/helm/charts/backend) inject a real
    # value via a K8s Secret with a `required` guard at install time, so a
    # Helm install with no value set fails loudly instead of silently
    # falling back to this constant. A bare `uvicorn` run or a
    # non-Helm/non-compose deployment that forgets to set this env var will
    # NOT fail loudly — it will silently authenticate with this well-known
    # dev-realm value instead (the CLAUDE.md "Keycloak secrets" gotcha).
    # Closing that gap needs a "required in production" settings split that
    # nothing else in this Settings class has yet, so it isn't fixed here;
    # the name below is deliberately unmistakable as a placeholder in the
    # meantime, so no one mistakes it for a value requiring no setup.
    keycloak_client_secret: str = "eaistack-api-secret"

    # Path to the internal CA bundle every outbound HTTP client verifies
    # against, mounted into the pod by the Helm chart (Phase 5, Decision 2).
    # None keeps httpx's default trust store, which is what local dev and
    # docker-compose need — both talk plain HTTP, where verify is ignored
    # anyway, and pointing at a file that isn't there would fail on startup.
    ca_bundle_path: str | None = None

    # Data retention (env-level defaults; an admin can override each of these
    # at runtime via the settings screen, which writes to SystemSettings —
    # see app.services.retention_service.resolve_retention_config).
    #
    # session_ttl_hours is the conversation/checkpoint window: None means
    # "keep forever", 0 means "purge immediately". Enforced by the retention
    # sweep (`python -m app.cli.retention_sweep`), which a K8s CronJob runs
    # on a schedule — deliberately not an in-process scheduler, which would
    # double-run across replicas.
    session_cleanup_on_logout: bool = True
    session_ttl_hours: int | None = 24

    # How long soft-deleted documents (and their embeddings) and revoked API
    # keys are retained before being hard-deleted. None means "keep forever",
    # preserving today's behaviour of never purging them.
    knowledge_base_purge_days: int | None = 30
    api_key_purge_days: int | None = 30

    # Guardrail config (env-level defaults; an admin can override each at
    # runtime via the settings screen, which writes to SystemSettings — see
    # app.services.guardrail_config_service.resolve_guardrail_config).
    #
    # guardrail_max_input_length is the env-level default for the input
    # guardrail's length-rejection threshold — distinct from
    # app.guardrails.input_guardrail.DEFAULT_MAX_INPUT_LENGTH (that module's
    # own fallback when called with no override at all, e.g. from a test)
    # and MAX_INPUT_LENGTH_CEILING (the hard, never-overridable upper bound
    # enforced at the settings-request schema boundary). The two constants
    # happen to share this same value today, but a change to one must not
    # silently move the other, so they stay independent.
    guardrail_max_input_length: int = 8000
    guardrails_input_enabled: bool = True
    guardrails_output_enabled: bool = True

    # Rate limiting (env-level defaults; an admin can override each at
    # runtime via the settings screen, which writes to SystemSettings — see
    # app.services.rate_limit_config_service.resolve_rate_limit_config).
    # Token-bucket shaped: *_capacity is the burst size (max tokens the
    # bucket can hold), *_refill_per_minute is the sustained rate tokens
    # accrue at. Chat (POST /api/agents/chat) is keyed by the caller's
    # user_id from the validated JWT; auth (POST /api/auth/token) has no
    # authenticated identity yet, so it's keyed by client IP instead — see
    # app.services.rate_limiter_service.
    #
    # Bounded to >= 1 here, not just on UpdateSettingsRequest (the admin API
    # schema): that bound only guards the DB-override write path. Without an
    # equal floor here, a misconfigured env var (e.g. a typo'd
    # RATE_LIMIT_CHAT_REFILL_PER_MINUTE=0) would reach
    # app.ratelimit.token_bucket.check_and_consume's
    # `missing_tokens / refill_per_second` division and crash every request
    # that empties the bucket with an unhandled ZeroDivisionError instead of
    # failing loudly at process startup, where a misconfiguration belongs.
    rate_limit_enabled: bool = True
    rate_limit_chat_capacity: int = Field(default=10, ge=1)
    rate_limit_chat_refill_per_minute: int = Field(default=10, ge=1)
    rate_limit_auth_capacity: int = Field(default=10, ge=1)
    rate_limit_auth_refill_per_minute: int = Field(default=10, ge=1)

    # How many trusted reverse-proxy hops sit between the real client and
    # this process, for resolving the IP that keys POST /api/auth/token's
    # rate-limit bucket (see app.core.client_ip.resolve_client_ip). 0 (the
    # default) means "don't trust X-Forwarded-For at all" - use the raw
    # transport peer IP, which is correct for local dev/docker-compose
    # (no proxy in front of the backend) and safe for any deployment that
    # hasn't explicitly confirmed its proxy topology, since a wrongly
    # trusted header would let any caller spoof their own rate-limit
    # identity. Set to 1 for a single reverse proxy/ingress in front of the
    # backend (this repo's own Helm chart deployment target, Phase 5) - see
    # docs/SECURITY.md's Rate Limiting section. Env-only: unlike the
    # capacity/refill fields above, this describes fixed deployment
    # topology, not a runtime policy an admin should redirect at will (the
    # same reasoning tracing_otlp_endpoint uses for staying env-only).
    rate_limit_trusted_proxy_count: int = Field(default=0, ge=0)

    # Knowledge-base file upload limits (see app.api.knowledge_base's
    # upload endpoint, issue #13). Enforced at the request boundary before
    # any bytes are read into memory or handed to text extraction - an
    # unbounded upload from an authenticated-but-untrusted-content caller
    # is a resource-exhaustion vector.
    knowledge_base_upload_max_bytes: int = 25 * 1024 * 1024  # 25 MiB
    knowledge_base_upload_allowed_content_types: List[str] = [
        "text/plain",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    @field_validator("*", mode="before")
    @classmethod
    def _blank_bool_env_var_uses_field_default(cls, value: Any, info) -> Any:
        """Treat a blank string as "unset" for bool-typed fields only.

        pydantic-settings reads every env var as a string and hands it to
        the field's type for parsing; its bool parser rejects "" outright
        (ValidationError: bool_parsing) rather than treating it like an
        absent variable. That turns a harmless blank line in a .env file or
        a K8s ConfigMap that renders an empty string (rather than omitting
        the key) into a process that won't start at all. Scoped to bool
        fields specifically - an empty string is a legitimate, meaningful
        value for a str field (e.g. llm_api_key = "" means "no key"), so
        this must not touch anything but the bool-parsing failure mode.
        """
        field = cls.model_fields[info.field_name]
        if value == "" and field.annotation is bool:
            return field.default
        return value

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
