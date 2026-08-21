"""API endpoints for admin-only runtime provider settings."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import ProviderOption, SystemSettingsResponse, UpdateSettingsRequest
from app.core.auth import require_admin
from app.db.database import get_db
from app.db.models import SystemSettings
from app.repositories import SystemSettingsRepository
from app.services import (
    available_provider_options,
    resolve_embedding_config,
    resolve_llm_config,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Sentinel distinguishing "caller didn't pass db_settings" from "caller
# passed the real value None" (a legitimate case: no SystemSettings row
# exists yet). Mirrors the same pattern in system_settings_service.
_NOT_PROVIDED = object()


def _provider_options_by_category() -> dict[str, dict[str, dict[str, str | bool]]]:
    """available_provider_options(), indexed by provider name within each
    category, for O(1) lookups of a provider's catalog entry.
    """
    return {
        category: {str(option["provider"]): option for option in options}
        for category, options in available_provider_options().items()
    }


def _to_response(
    db: Session, db_settings: SystemSettings | None = _NOT_PROVIDED
) -> SystemSettingsResponse:
    """Build the settings response: resolved effective config, plus which
    fields are DB-overridden vs. falling back to the env default.

    db_settings: the already-fetched singleton row, if the caller has one
    (e.g. update_settings, whose upsert() call already returns it) — avoids
    a redundant SELECT. Omit it (the default) for callers like get_settings
    that have no row of their own yet.
    """
    if db_settings is _NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()
    llm_config = resolve_llm_config(db, db_settings)
    embedding_config = resolve_embedding_config(db, db_settings)

    return SystemSettingsResponse(
        llm_provider=llm_config.provider,
        llm_url=llm_config.url,
        llm_model=llm_config.model,
        llm_provider_is_db_override=bool(db_settings and db_settings.llm_provider is not None),
        llm_url_is_db_override=bool(db_settings and db_settings.llm_url is not None),
        llm_model_is_db_override=bool(db_settings and db_settings.llm_model is not None),
        embedding_provider=embedding_config.provider,
        embedding_url=embedding_config.url,
        embedding_model=embedding_config.model,
        embedding_provider_is_db_override=bool(
            db_settings and db_settings.embedding_provider is not None
        ),
        embedding_url_is_db_override=bool(db_settings and db_settings.embedding_url is not None),
        embedding_model_is_db_override=bool(
            db_settings and db_settings.embedding_model is not None
        ),
        available_providers={
            category: [ProviderOption(**option) for option in options]
            for category, options in available_provider_options().items()
        },
    )


@router.get("", response_model=SystemSettingsResponse)
async def get_settings(
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get the current effective LLM/embedding provider config.

    Never returns llm_api_key: it stays env-only, never persisted to the
    DB or exposed over this API.
    """
    return _to_response(db)


@router.put("", response_model=SystemSettingsResponse)
async def update_settings(
    payload: UpdateSettingsRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update the runtime provider overrides.

    Any field omitted (or null) clears back to the env-var default,
    matching the nullable-column semantics of SystemSettings. Takes effect
    on the next chat/embedding call — no backend restart required.
    """
    options_by_category = _provider_options_by_category()

    if payload.llm_provider is not None and payload.llm_provider not in options_by_category["llm"]:
        raise HTTPException(status_code=400, detail=f"Unknown llm_provider: {payload.llm_provider}")
    if (
        payload.embedding_provider is not None
        and payload.embedding_provider not in options_by_category["embedding"]
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown embedding_provider: {payload.embedding_provider}",
        )

    repo = SystemSettingsRepository(db)
    db_settings = repo.get()

    # The provider this URL applies to is the one the payload is setting, or
    # (if the payload only touches the URL) the currently-effective one —
    # never assume "fake", since an existing openai-compatible override must
    # still be validated when only its URL is being cleared.
    llm_provider = payload.llm_provider or resolve_llm_config(db, db_settings).provider
    if options_by_category["llm"][llm_provider]["requires_manual_entry"] and payload.llm_url == "":
        raise HTTPException(
            status_code=400,
            detail=f"llm_url is required for provider: {llm_provider}",
        )

    embedding_provider = (
        payload.embedding_provider or resolve_embedding_config(db, db_settings).provider
    )
    if (
        options_by_category["embedding"][embedding_provider]["requires_manual_entry"]
        and payload.embedding_url == ""
    ):
        raise HTTPException(
            status_code=400,
            detail=f"embedding_url is required for provider: {embedding_provider}",
        )

    updated_settings = repo.upsert(
        llm_provider=payload.llm_provider,
        llm_url=payload.llm_url,
        llm_model=payload.llm_model,
        embedding_provider=payload.embedding_provider,
        embedding_url=payload.embedding_url,
        embedding_model=payload.embedding_model,
        updated_by=user["user_id"],
    )
    db.commit()

    return _to_response(db, updated_settings)
