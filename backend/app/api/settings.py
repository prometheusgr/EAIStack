"""API endpoints for admin-only runtime provider settings."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    AuditLogEntry,
    AuditLogResponse,
    ProviderOption,
    SystemSettingsResponse,
    UpdateSettingsRequest,
)
from app.core.auth import require_admin
from app.db.database import get_db
from app.db.models import SystemSettings, utc_now
from app.repositories import AuditLogRepository, SystemSettingsRepository
from app.services import (
    available_provider_options,
    resolve_embedding_config,
    resolve_llm_config,
    resolve_retention_config,
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
    retention_config = resolve_retention_config(db, db_settings)

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
        conversation_retention_hours=retention_config.conversation_retention_hours,
        conversation_retention_hours_is_db_override=bool(
            db_settings and db_settings.conversation_retention_hours is not None
        ),
        cleanup_on_logout=retention_config.cleanup_on_logout,
        cleanup_on_logout_is_db_override=bool(
            db_settings and db_settings.cleanup_on_logout is not None
        ),
        knowledge_base_purge_days=retention_config.knowledge_base_purge_days,
        knowledge_base_purge_days_is_db_override=bool(
            db_settings and db_settings.knowledge_base_purge_days is not None
        ),
        api_key_purge_days=retention_config.api_key_purge_days,
        api_key_purge_days_is_db_override=bool(
            db_settings and db_settings.api_key_purge_days is not None
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

    # Captured before the write: the audit trail must show the actual
    # transition (72 -> 24), which is unrecoverable once upsert has run.
    previous_retention = _retention_override_values(db_settings)

    updated_settings = repo.upsert(
        llm_provider=payload.llm_provider,
        llm_url=payload.llm_url,
        llm_model=payload.llm_model,
        embedding_provider=payload.embedding_provider,
        embedding_url=payload.embedding_url,
        embedding_model=payload.embedding_model,
        conversation_retention_hours=payload.conversation_retention_hours,
        cleanup_on_logout=payload.cleanup_on_logout,
        knowledge_base_purge_days=payload.knowledge_base_purge_days,
        api_key_purge_days=payload.api_key_purge_days,
        updated_by=user["user_id"],
    )

    _record_retention_changes(
        db,
        actor_user_id=user["user_id"],
        previous=previous_retention,
        current=_retention_override_values(updated_settings),
    )

    db.commit()

    return _to_response(db, updated_settings)


@router.get("/audit", response_model=AuditLogResponse)
async def get_audit_log(
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Read the audit trail of retention changes, newest first.

    Admin-only, read-only: this API exposes no way to modify or delete an
    audit entry, and AuditLogRepository has no method that could.
    """
    entries = AuditLogRepository(db).list_recent()
    return AuditLogResponse(entries=[AuditLogEntry.model_validate(entry) for entry in entries])


def _retention_override_values(db_settings: SystemSettings | None) -> dict[str, str | None]:
    """Snapshot the retention columns' raw override values as strings.

    Reads the columns rather than the resolved config on purpose: the audit
    trail records what the admin set (including "cleared back to the env
    default", as None), not what the value happened to resolve to.
    """
    fields = (
        "conversation_retention_hours",
        "cleanup_on_logout",
        "knowledge_base_purge_days",
        "api_key_purge_days",
    )
    if db_settings is None:
        return {field: None for field in fields}

    return {
        field: None if getattr(db_settings, field) is None else str(getattr(db_settings, field))
        for field in fields
    }


def _record_retention_changes(
    db: Session,
    *,
    actor_user_id: str,
    previous: dict[str, str | None],
    current: dict[str, str | None],
) -> None:
    """Append one audit entry per retention field whose value actually changed.

    Only changed fields are recorded: the trail is a history of changes, so
    re-saving the settings form without touching retention must not
    fabricate entries. One timestamp is shared across every entry from this
    request so a multi-field change reads as a single event.
    """
    repo = AuditLogRepository(db)
    changed_at = utc_now()

    for field, new_value in current.items():
        if previous[field] == new_value:
            continue
        repo.record(
            actor_user_id=actor_user_id,
            action="retention.update",
            field_name=field,
            old_value=previous[field],
            new_value=new_value,
            now=changed_at,
        )
