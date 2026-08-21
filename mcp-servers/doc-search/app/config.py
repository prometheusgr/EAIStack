"""Service configuration for the doc-search MCP server."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings from environment variables.

    Mirrors the subset of backend/app/core/config.py this service needs:
    its own database connection and enough Keycloak detail to verify a
    bearer token's signature and audience independently of the backend.
    """

    database_url: str = "postgresql://postgres:postgres@localhost:5432/eaistack"

    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "eaistack"

    # Tokens minted for either client are accepted: the frontend's web client
    # (a user's own session token, forwarded by the backend) and the backend's
    # own API client (for any future service-to-service call path).
    keycloak_client_id: str = "eaistack-api"
    keycloak_web_client_id: str = "eaistack-web"

    # Embedding provider env-level defaults. Mirrors backend/app/core/config.py's
    # embedding_provider/embedding_url/embedding_model: an admin's runtime
    # override (via the Settings screen, stored in system_settings) wins over
    # these — see app.search.resolve_embedding_config. Keeping the same env
    # defaults here means doc-search's query-time embedding stays consistent
    # with the backend's indexing-time embedding without any coordination step
    # beyond both services reading the same DB row.
    embedding_provider: str = "fake"
    embedding_url: str = "http://localhost:8002/v1"
    embedding_model: str = "nomic-embed-text-v1.5.Q4_K_M.gguf"
    embedding_timeout: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
