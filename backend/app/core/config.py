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

    # Keycloak (OIDC)
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "eaistack"
    keycloak_client_id: str = "eaistack-api"
    keycloak_client_secret: str = "eaistack-api-secret"

    # Session lifecycle
    session_cleanup_on_logout: bool = True
    session_ttl_hours: int | None = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
