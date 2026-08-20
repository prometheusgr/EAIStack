"""Service for resolving effective runtime LLM/embedding provider config.

Reads the DB-backed SystemSettings singleton (per-call, not cached) and
falls back to the process-start env Settings object for any field that
hasn't been overridden. This is the "no restart" mechanism: an admin can
change a field via the settings API and the very next chat/embedding call
picks it up, because every call resolves config fresh rather than reading
a value cached at process start.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.system_settings_repository import SystemSettingsRepository


@dataclass(frozen=True)
class LLMConfig:
    """Effective LLM config for one call, DB override merged over env defaults."""

    provider: str
    url: str
    model: str
    api_key: str | None
    timeout: int


@dataclass(frozen=True)
class EmbeddingConfig:
    """Effective embedding config for one call, DB override merged over env defaults."""

    provider: str
    url: str
    model: str
    timeout: int


def resolve_llm_config(db: Session) -> LLMConfig:
    """Resolve the effective LLM config: DB value if set, else env default.

    api_key and timeout are always sourced from env Settings — there are no
    DB columns for them. api_key in particular must never be persisted to
    the DB or exposed to the settings screen (see the security note on
    app.api.settings.get_settings).
    """
    db_settings = SystemSettingsRepository(db).get()

    return LLMConfig(
        provider=(db_settings.llm_provider if db_settings else None) or settings.llm_provider,
        url=(db_settings.llm_url if db_settings else None) or settings.llm_url,
        model=(db_settings.llm_model if db_settings else None) or settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
    )


def resolve_embedding_config(db: Session) -> EmbeddingConfig:
    """Resolve the effective embedding config: DB value if set, else env default."""
    db_settings = SystemSettingsRepository(db).get()

    return EmbeddingConfig(
        provider=(db_settings.embedding_provider if db_settings else None)
        or settings.embedding_provider,
        url=(db_settings.embedding_url if db_settings else None) or settings.embedding_url,
        model=(db_settings.embedding_model if db_settings else None) or settings.embedding_model,
        timeout=settings.embedding_timeout,
    )


def available_provider_options() -> dict[str, list[dict[str, str]]]:
    """Return the fixed "detected local services" list for the settings screen's
    provider pickers.

    Hardcoded to match docker-compose.yml's actual service DNS names/ports
    (both llama-server and embedding-server listen on container-internal
    port 8000; embedding-server's 8002 is only the host-published port) —
    not discovered dynamically, since this stack has no service-discovery
    mechanism.
    """
    return {
        "llm": [
            {"provider": "fake", "url": "", "label": "Fake (mocked, for testing)"},
            {
                "provider": "llama-cpp",
                "url": "http://llama-server:8000/v1",
                "label": "llama-cpp (llama-server, detected)",
            },
            {
                "provider": "openai-compatible",
                "url": "",
                "label": "OpenAI-compatible (custom)",
            },
        ],
        "embedding": [
            {"provider": "fake", "url": "", "label": "Fake (mocked, for testing)"},
            {
                "provider": "llama-cpp",
                "url": "http://embedding-server:8000/v1",
                "label": "llama-cpp (embedding-server, detected)",
            },
        ],
    }
