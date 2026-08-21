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
from app.db.models import SystemSettings
from app.repositories.system_settings_repository import SystemSettingsRepository

# Sentinel distinguishing "caller didn't pass db_settings" from "caller
# passed the real value None" (which happens whenever no SystemSettings row
# has been created yet — a legitimate, common case, not an absent argument).
_NOT_PROVIDED = object()


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


def _resolve_field(db_value: str | None, env_default: str) -> str:
    """Resolve one overridable field: the DB value if a row set it (even to
    an empty string, which is a deliberate override — e.g. the 'fake'
    provider's URL template is ""), else the env default.

    Must stay an `is not None` check, not a truthiness check: `"" or env`
    would silently discard an empty-string override, which would make this
    resolver disagree with `_to_response`'s `is_db_override` computation in
    app.api.settings (also an `is not None` check).
    """
    return db_value if db_value is not None else env_default


def resolve_llm_config(
    db: Session, db_settings: SystemSettings | None = _NOT_PROVIDED
) -> LLMConfig:
    """Resolve the effective LLM config: DB value if set, else env default.

    api_key and timeout are always sourced from env Settings — there are no
    DB columns for them. api_key in particular must never be persisted to
    the DB or exposed to the settings screen (see the security note on
    app.api.settings.get_settings).

    db_settings: the already-fetched singleton row, if the caller has one.
    Pass it to avoid a redundant `SystemSettingsRepository(db).get()` query
    when the caller already fetched the row for its own purposes (see
    app.api.settings._to_response). Omit it (the default) to preserve this
    function's original self-contained behavior for callers (llm_client.py)
    that only have a session, not a pre-fetched row — the parameter must
    default to a sentinel, not None, because None is also the legitimate
    value of db_settings when no SystemSettings row has been created yet.
    """
    if db_settings is _NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return LLMConfig(
        provider=_resolve_field(
            db_settings.llm_provider if db_settings else None, settings.llm_provider
        ),
        url=_resolve_field(db_settings.llm_url if db_settings else None, settings.llm_url),
        model=_resolve_field(db_settings.llm_model if db_settings else None, settings.llm_model),
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
    )


def resolve_embedding_config(
    db: Session, db_settings: SystemSettings | None = _NOT_PROVIDED
) -> EmbeddingConfig:
    """Resolve the effective embedding config: DB value if set, else env default.

    db_settings: the already-fetched singleton row, if the caller has one.
    Pass it to avoid a redundant `SystemSettingsRepository(db).get()` query
    (see app.api.settings._to_response). Omit it (the default) to preserve
    this function's original self-contained behavior for callers
    (embedding_service.py) that only have a session, not a pre-fetched row —
    the parameter must default to a sentinel, not None, because None is also
    the legitimate value of db_settings when no SystemSettings row has been
    created yet.
    """
    if db_settings is _NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return EmbeddingConfig(
        provider=_resolve_field(
            db_settings.embedding_provider if db_settings else None, settings.embedding_provider
        ),
        url=_resolve_field(
            db_settings.embedding_url if db_settings else None, settings.embedding_url
        ),
        model=_resolve_field(
            db_settings.embedding_model if db_settings else None, settings.embedding_model
        ),
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
