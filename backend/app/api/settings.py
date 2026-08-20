"""API endpoints for admin-only runtime provider settings."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import ProviderOption, SystemSettingsResponse, UpdateSettingsRequest
from app.core.auth import require_admin
from app.db.database import get_db
from app.repositories import SystemSettingsRepository
from app.services import (
    available_provider_options,
    resolve_embedding_config,
    resolve_llm_config,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

_VALID_LLM_PROVIDERS = {"fake", "llama-cpp", "openai-compatible"}
_VALID_EMBEDDING_PROVIDERS = {"fake", "llama-cpp"}


def _to_response(db: Session) -> SystemSettingsResponse:
    """Build the settings response: resolved effective config, plus which
    fields are DB-overridden vs. falling back to the env default.
    """
    db_settings = SystemSettingsRepository(db).get()
    llm_config = resolve_llm_config(db)
    embedding_config = resolve_embedding_config(db)

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
    if payload.llm_provider is not None and payload.llm_provider not in _VALID_LLM_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown llm_provider: {payload.llm_provider}")
    if (
        payload.embedding_provider is not None
        and payload.embedding_provider not in _VALID_EMBEDDING_PROVIDERS
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown embedding_provider: {payload.embedding_provider}",
        )

    repo = SystemSettingsRepository(db)
    repo.upsert(
        llm_provider=payload.llm_provider,
        llm_url=payload.llm_url,
        llm_model=payload.llm_model,
        embedding_provider=payload.embedding_provider,
        embedding_url=payload.embedding_url,
        embedding_model=payload.embedding_model,
        updated_by=user["user_id"],
    )
    db.commit()

    return _to_response(db)
