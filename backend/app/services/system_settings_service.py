"""Service for resolving effective runtime LLM/embedding provider config.

Reads the DB-backed SystemSettings singleton (per-call, not cached) and
falls back to the process-start env Settings object for any field that
hasn't been overridden. This is the "no restart" mechanism: an admin can
change a field via the settings API and the very next chat/embedding call
picks it up, because every call resolves config fresh rather than reading
a value cached at process start.
"""

from dataclasses import dataclass
from enum import Enum
from typing import TypedDict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SystemSettings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.config_resolution import resolve_field


class NotProvided(Enum):
    """Type for the "argument omitted" sentinel below.

    A single-member Enum rather than object() so the sentinel has a type
    mypy can narrow on: SystemSettings | None | NotProvided states the
    three real cases, and the `is NOT_PROVIDED` checks narrow the sentinel
    away. A bare object() forces the annotation to widen to object, which
    loses that distinction.
    """

    token = 0


# Sentinel distinguishing "caller didn't pass db_settings" from "caller
# passed the real value None" (which happens whenever no SystemSettings row
# has been created yet — a legitimate, common case, not an absent argument).
NOT_PROVIDED = NotProvided.token


class ProviderOptionDict(TypedDict):
    """One provider-picker entry as returned by available_provider_options.

    A TypedDict rather than dict[str, str | bool] so each key keeps its own
    type, which is what lets ProviderOption(**option) typecheck at the call
    site in app.api.settings; a union-valued dict cannot express that.
    """

    provider: str
    url: str
    label: str
    requires_manual_entry: bool


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


def resolve_llm_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
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
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return LLMConfig(
        provider=resolve_field(
            db_value=db_settings.llm_provider if db_settings else None,
            env_default=settings.llm_provider,
        ),
        url=resolve_field(
            db_value=db_settings.llm_url if db_settings else None, env_default=settings.llm_url
        ),
        model=resolve_field(
            db_value=db_settings.llm_model if db_settings else None,
            env_default=settings.llm_model,
        ),
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
    )


def resolve_embedding_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
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
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return EmbeddingConfig(
        provider=resolve_field(
            db_value=db_settings.embedding_provider if db_settings else None,
            env_default=settings.embedding_provider,
        ),
        url=resolve_field(
            db_value=db_settings.embedding_url if db_settings else None,
            env_default=settings.embedding_url,
        ),
        model=resolve_field(
            db_value=db_settings.embedding_model if db_settings else None,
            env_default=settings.embedding_model,
        ),
        timeout=settings.embedding_timeout,
    )


def _provider_option(
    provider: str, label: str, configured_provider: str, configured_url: str
) -> ProviderOptionDict:
    """Build one picker entry, suggesting the configured URL to its own provider.

    Only the provider this deployment is actually configured for gets the
    configured URL (and the "detected" suffix). Every other entry is offered
    with an empty URL for the admin to fill in, because this deployment
    holds no address for it: LLM_URL describes one endpoint, and which
    provider that endpoint belongs to is exactly what LLM_PROVIDER says.

    "fake" is always urlless — it runs in-process, so a URL for it is
    meaningless even if a deployment nonsensically configured one.
    """
    if provider == "fake":
        return {"provider": provider, "url": "", "label": label, "requires_manual_entry": False}

    is_configured = provider == configured_provider
    return {
        "provider": provider,
        "url": configured_url if is_configured else "",
        "label": f"{label} (detected)" if is_configured else label,
        "requires_manual_entry": True,
    }


def available_provider_options() -> dict[str, list[ProviderOptionDict]]:
    """Return the provider pickers for the settings screen.

    Which providers exist is fixed by the code (each needs a branch in
    llm_client / embedding_service). What varies is the URL suggested for
    each, and that comes from this process's own env config
    (settings.llm_provider/llm_url, settings.embedding_provider/embedding_url)
    rather than hardcoded service names.

    Why not hardcode: every deployment already states where its LLM and
    embedding servers live, and they disagree. docker-compose.yml sets
    LLM_URL to http://llama-server:8000/v1; infra/k3s/ uses that cluster's
    eaistack-prefixed service names; and a deployment with no llama.cpp at
    all can point LLM_URL at Azure OpenAI, Bedrock, or any OpenAI-compatible
    gateway. Hardcoding compose's names offered every other deployment a URL
    that resolves nowhere — and because a saved DB override always beats the
    env default (see _resolve_field), accepting that offer would overwrite a
    correct env value with an unreachable one, turning "pick the detected
    default" into an outage.

    The URL is suggested only for the configured provider, never blanket-
    applied to llama-cpp: a hosted endpoint must not be labelled
    "llama-server, detected". Providers this deployment did not configure are
    offered with an empty URL for the admin to fill in.

    There is no service *discovery* here: this reports what this deployment
    was configured to use, it does not probe the network.

    `requires_manual_entry` is an explicit flag for whether the settings
    screen should show the custom URL/model fields. It is not inferred from
    `url` being empty: a configured provider has a suggested URL and is
    still customizable, so "has a default URL" and "is customizable" are
    independent facts.
    """
    return {
        "llm": [
            _provider_option(
                "fake", "Fake (mocked, for testing)", settings.llm_provider, settings.llm_url
            ),
            _provider_option(
                "llama-cpp",
                "llama-cpp (local llama-server)",
                settings.llm_provider,
                settings.llm_url,
            ),
            _provider_option(
                "openai-compatible",
                "OpenAI-compatible (hosted endpoint)",
                settings.llm_provider,
                settings.llm_url,
            ),
        ],
        "embedding": [
            _provider_option(
                "fake",
                "Fake (mocked, for testing)",
                settings.embedding_provider,
                settings.embedding_url,
            ),
            _provider_option(
                "llama-cpp",
                "llama-cpp (local embedding-server)",
                settings.embedding_provider,
                settings.embedding_url,
            ),
        ],
    }
