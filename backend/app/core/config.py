"""Application configuration."""

from typing import List

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

    # Keycloak (OIDC)
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "eaistack"
    keycloak_client_id: str = "eaistack-api"
    keycloak_web_client_id: str = "eaistack-web"
    keycloak_client_secret: str = "eaistack-api-secret"

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
