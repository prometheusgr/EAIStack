"""API endpoints for admin-only runtime provider settings."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.schemas import (
    AuditLogEntry,
    AuditLogResponse,
    CreateGuardrailPatternRequest,
    DashboardResponse,
    GuardrailPatternResponse,
    GuardrailStatusResponse,
    ProviderOption,
    RateLimitStatusResponse,
    SystemSettingsResponse,
    TestConnectionRequest,
    TestConnectionResponse,
    TracingStatusResponse,
    UpdateGuardrailPatternRequest,
    UpdateSettingsRequest,
)
from app.core.auth import require_admin
from app.core.config import settings as env_settings
from app.db.database import get_db
from app.db.models import SystemSettings, utc_now
from app.repositories import (
    AuditLogRepository,
    GuardrailPatternRepository,
    SystemSettingsRepository,
)
from app.services import (
    available_provider_options,
    resolve_audit_log_ui_config,
    resolve_dashboard_status,
    resolve_embedding_config,
    resolve_guardrail_config,
    resolve_llm_config,
    resolve_rate_limit_config,
    resolve_retention_config,
    resolve_tracing_config,
)
from app.services.provider_probe_service import probe_provider
from app.services.system_settings_service import (
    NOT_PROVIDED,
    NotProvided,
    ProviderOptionDict,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _error_response(status_code: int, detail: str, message: str) -> JSONResponse:
    """Build a {detail, message} JSONResponse for this router's error paths.

    Every 4xx here needs both a stable, machine-readable `detail` code and a
    human-readable `message` -- the Settings screen's toast reads only
    `message` (never `detail`, see ApiErrorImpl in
    frontend/src/api/authorizedFetch.ts), so a response missing it reaches
    the admin as a blank toast. Mirrors
    app.services.rate_limiter_service.rate_limit_exceeded_response, which
    documents the same consolidation for the identical reason: two (now,
    across this router, six) call sites hand-building an identical
    status-code/detail-key shape with only the message differing.
    """
    return JSONResponse(status_code=status_code, content={"detail": detail, "message": message})


def _provider_options_by_category() -> dict[str, dict[str, ProviderOptionDict]]:
    """available_provider_options(), indexed by provider name within each
    category, for O(1) lookups of a provider's catalog entry.
    """
    return {
        category: {str(option["provider"]): option for option in options}
        for category, options in available_provider_options().items()
    }


def _to_response(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> SystemSettingsResponse:
    """Build the settings response: resolved effective config, plus which
    fields are DB-overridden vs. falling back to the env default.

    db_settings: the already-fetched singleton row, if the caller has one
    (e.g. update_settings, whose upsert() call already returns it) — avoids
    a redundant SELECT. Omit it (the default) for callers like get_settings
    that have no row of their own yet.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()
    llm_config = resolve_llm_config(db, db_settings)
    embedding_config = resolve_embedding_config(db, db_settings)
    retention_config = resolve_retention_config(db, db_settings)
    guardrail_config = resolve_guardrail_config(db, db_settings)
    guardrail_patterns = GuardrailPatternRepository(db).list_all()
    tracing_config = resolve_tracing_config(db, db_settings)
    rate_limit_config = resolve_rate_limit_config(db, db_settings)
    audit_log_ui_config = resolve_audit_log_ui_config(db, db_settings)

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
        max_input_length=guardrail_config.max_input_length,
        max_input_length_is_db_override=bool(
            db_settings and db_settings.max_input_length is not None
        ),
        guardrails_input_enabled=guardrail_config.input_enabled,
        guardrails_input_enabled_is_db_override=bool(
            db_settings and db_settings.guardrails_input_enabled is not None
        ),
        guardrails_output_enabled=guardrail_config.output_enabled,
        guardrails_output_enabled_is_db_override=bool(
            db_settings and db_settings.guardrails_output_enabled is not None
        ),
        guardrail_patterns=[
            GuardrailPatternResponse.model_validate(pattern) for pattern in guardrail_patterns
        ],
        tracing_enabled=tracing_config.enabled,
        tracing_enabled_is_db_override=bool(
            db_settings and db_settings.tracing_enabled is not None
        ),
        rate_limit_enabled=rate_limit_config.enabled,
        rate_limit_enabled_is_db_override=bool(
            db_settings and db_settings.rate_limit_enabled is not None
        ),
        rate_limit_chat_capacity=rate_limit_config.chat_capacity,
        rate_limit_chat_capacity_is_db_override=bool(
            db_settings and db_settings.rate_limit_chat_capacity is not None
        ),
        rate_limit_chat_refill_per_minute=rate_limit_config.chat_refill_per_minute,
        rate_limit_chat_refill_per_minute_is_db_override=bool(
            db_settings and db_settings.rate_limit_chat_refill_per_minute is not None
        ),
        rate_limit_auth_capacity=rate_limit_config.auth_capacity,
        rate_limit_auth_capacity_is_db_override=bool(
            db_settings and db_settings.rate_limit_auth_capacity is not None
        ),
        rate_limit_auth_refill_per_minute=rate_limit_config.auth_refill_per_minute,
        rate_limit_auth_refill_per_minute_is_db_override=bool(
            db_settings and db_settings.rate_limit_auth_refill_per_minute is not None
        ),
        audit_log_ui_enabled=audit_log_ui_config.enabled,
        audit_log_ui_enabled_is_db_override=bool(
            db_settings and db_settings.audit_log_ui_enabled is not None
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


@router.put("", response_model=None)
async def update_settings(
    payload: UpdateSettingsRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemSettingsResponse | JSONResponse:
    """Update the runtime provider overrides.

    Any field omitted (or null) clears back to the env-var default,
    matching the nullable-column semantics of SystemSettings. Takes effect
    on the next chat/embedding call — no backend restart required.
    """
    options_by_category = _provider_options_by_category()

    if payload.llm_provider is not None and payload.llm_provider not in options_by_category["llm"]:
        return _error_response(
            400,
            f"unknown_llm_provider:{payload.llm_provider}",
            f"Unknown LLM provider: {payload.llm_provider}",
        )
    if (
        payload.embedding_provider is not None
        and payload.embedding_provider not in options_by_category["embedding"]
    ):
        return _error_response(
            400,
            f"unknown_embedding_provider:{payload.embedding_provider}",
            f"Unknown embedding provider: {payload.embedding_provider}",
        )

    repo = SystemSettingsRepository(db)
    db_settings = repo.get()

    # The provider this URL applies to is the one the payload is setting, or
    # (if the payload only touches the URL) the currently-effective one —
    # never assume "fake", since an existing openai-compatible override must
    # still be validated when only its URL is being cleared.
    llm_provider = payload.llm_provider or resolve_llm_config(db, db_settings).provider
    if options_by_category["llm"][llm_provider]["requires_manual_entry"] and payload.llm_url == "":
        return _error_response(
            400,
            f"llm_url_required:{llm_provider}",
            f"A URL is required for LLM provider: {llm_provider}",
        )

    embedding_provider = (
        payload.embedding_provider or resolve_embedding_config(db, db_settings).provider
    )
    if (
        options_by_category["embedding"][embedding_provider]["requires_manual_entry"]
        and payload.embedding_url == ""
    ):
        return _error_response(
            400,
            f"embedding_url_required:{embedding_provider}",
            f"A URL is required for embedding provider: {embedding_provider}",
        )

    # Captured before the write: the audit trail must show the actual
    # transition (72 -> 24), which is unrecoverable once upsert has run.
    previous_retention = _retention_override_values(db_settings)
    previous_guardrail = _guardrail_override_values(db_settings)
    previous_tracing = _tracing_override_values(db_settings)
    previous_rate_limit = _rate_limit_override_values(db_settings)
    previous_audit_log_ui = _audit_log_ui_override_values(db_settings)

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
        max_input_length=payload.max_input_length,
        guardrails_input_enabled=payload.guardrails_input_enabled,
        guardrails_output_enabled=payload.guardrails_output_enabled,
        tracing_enabled=payload.tracing_enabled,
        rate_limit_enabled=payload.rate_limit_enabled,
        rate_limit_chat_capacity=payload.rate_limit_chat_capacity,
        rate_limit_chat_refill_per_minute=payload.rate_limit_chat_refill_per_minute,
        rate_limit_auth_capacity=payload.rate_limit_auth_capacity,
        rate_limit_auth_refill_per_minute=payload.rate_limit_auth_refill_per_minute,
        audit_log_ui_enabled=payload.audit_log_ui_enabled,
        updated_by=user["user_id"],
    )

    _record_retention_changes(
        db,
        actor_user_id=user["user_id"],
        previous=previous_retention,
        current=_retention_override_values(updated_settings),
    )
    _record_guardrail_changes(
        db,
        actor_user_id=user["user_id"],
        previous=previous_guardrail,
        current=_guardrail_override_values(updated_settings),
    )
    _record_tracing_changes(
        db,
        actor_user_id=user["user_id"],
        previous=previous_tracing,
        current=_tracing_override_values(updated_settings),
    )
    _record_rate_limit_changes(
        db,
        actor_user_id=user["user_id"],
        previous=previous_rate_limit,
        current=_rate_limit_override_values(updated_settings),
    )
    _record_audit_log_ui_changes(
        db,
        actor_user_id=user["user_id"],
        previous=previous_audit_log_ui,
        current=_audit_log_ui_override_values(updated_settings),
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


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get the admin dashboard's status snapshot (issue #48): rate-limit
    bucket state, guardrail trip counts over a recent window, and tracing
    status. Admin-only, read-only -- see
    app.services.dashboard_service.resolve_dashboard_status for how each
    tile's data source was chosen.
    """
    status = resolve_dashboard_status(db, now=utc_now())
    return DashboardResponse(
        rate_limit=RateLimitStatusResponse(
            enabled=status.rate_limit.enabled,
            active_bucket_count=status.rate_limit.active_bucket_count,
        ),
        guardrails=GuardrailStatusResponse(
            input_rejected_counts_by_pattern=status.guardrails.input_rejected_counts_by_pattern,
            output_redacted_count=status.guardrails.output_redacted_count,
        ),
        tracing=TracingStatusResponse(
            db_desired_enabled=status.tracing.db_desired_enabled,
            process_actually_configured=status.tracing.process_actually_configured,
            phoenix_ui_url=status.tracing.phoenix_ui_url,
        ),
        keycloak_console_url=status.keycloak_console_url,
    )


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    payload: TestConnectionRequest,
    user: dict = Depends(require_admin),
):
    """Probe a candidate LLM/embedding provider URL for reachability and
    served models, for the Settings screen's "Test connection" action.

    Shared by both the LLM and embedding tabs: both llama-cpp and
    openai-compatible providers implement the same OpenAI-compatible
    /models endpoint, so one probe serves either. Writes nothing -- this
    never touches SystemSettings or the audit log, it only reports on a
    URL the admin is still deciding whether to save.

    Always 200, success or failure alike: a failed probe (unreachable host,
    timeout, non-2xx, unrecognized body) is a diagnostic result the admin
    needs to see, not a request error, so the frontend never has to
    special-case HTTP status vs. response body to render the same
    "connection failed" state.

    api_key always comes from this deployment's env-configured
    llm_api_key, mirroring get_settings' rule that api_key is never
    persisted to the DB or accepted from the frontend -- a probe can only
    authenticate as the currently configured provider, not a hypothetical
    different hosted endpoint with different credentials.
    """
    result = await probe_provider(
        url=payload.url, api_key=env_settings.llm_api_key, timeout=env_settings.llm_timeout
    )
    return TestConnectionResponse(ok=result.ok, models=result.models, error=result.error)


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


def _guardrail_override_values(db_settings: SystemSettings | None) -> dict[str, str | None]:
    """Snapshot the guardrail scalar columns' raw override values as strings.

    Mirrors _retention_override_values exactly, for the same reason: the
    audit trail must record what the admin set (including "cleared back to
    the env default", as None), not what the value happened to resolve to.
    Deliberately not generalized into one shared helper with the retention
    version -- see _record_guardrail_changes' docstring for why.
    """
    fields = ("max_input_length", "guardrails_input_enabled", "guardrails_output_enabled")
    if db_settings is None:
        return {field: None for field in fields}

    return {
        field: None if getattr(db_settings, field) is None else str(getattr(db_settings, field))
        for field in fields
    }


def _record_guardrail_changes(
    db: Session,
    *,
    actor_user_id: str,
    previous: dict[str, str | None],
    current: dict[str, str | None],
) -> None:
    """Append one "guardrail.config_update" audit entry per guardrail scalar
    field whose value actually changed.

    Mirrors _record_retention_changes' shape exactly (only changed fields
    recorded, one shared timestamp per request). Kept as its own function
    rather than generalizing the two into one action-name-parameterized
    helper: per AGENTS.md's no-premature-abstraction standard, two small,
    clearly-named functions that happen to look alike are preferable to a
    shared one that takes on an extra parameter for the sole purpose of
    being reused twice -- this was a deliberate call, not an oversight.
    """
    repo = AuditLogRepository(db)
    changed_at = utc_now()

    for field, new_value in current.items():
        if previous[field] == new_value:
            continue
        repo.record(
            actor_user_id=actor_user_id,
            action="guardrail.config_update",
            field_name=field,
            old_value=previous[field],
            new_value=new_value,
            now=changed_at,
        )


def _tracing_override_values(db_settings: SystemSettings | None) -> dict[str, str | None]:
    """Snapshot the tracing_enabled column's raw override value as a string.

    Mirrors _guardrail_override_values exactly, for the same reason: the
    audit trail must record what the admin set (including "cleared back to
    the env default", as None), not what the value happened to resolve to.
    A single-field dict rather than a bare value to keep the same
    shape/call pattern _record_tracing_changes shares with its siblings.
    """
    fields = ("tracing_enabled",)
    if db_settings is None:
        return {field: None for field in fields}

    return {
        field: None if getattr(db_settings, field) is None else str(getattr(db_settings, field))
        for field in fields
    }


def _record_tracing_changes(
    db: Session,
    *,
    actor_user_id: str,
    previous: dict[str, str | None],
    current: dict[str, str | None],
) -> None:
    """Append a "tracing.config_update" audit entry if tracing_enabled's
    override actually changed.

    Mirrors _record_guardrail_changes' shape exactly (only changed fields
    recorded, one shared timestamp per request). Kept as its own function
    rather than generalizing across all three families, per AGENTS.md's
    no-premature-abstraction standard - see _record_guardrail_changes'
    docstring for the same reasoning applied there.
    """
    repo = AuditLogRepository(db)
    changed_at = utc_now()

    for field, new_value in current.items():
        if previous[field] == new_value:
            continue
        repo.record(
            actor_user_id=actor_user_id,
            action="tracing.config_update",
            field_name=field,
            old_value=previous[field],
            new_value=new_value,
            now=changed_at,
        )


def _rate_limit_override_values(db_settings: SystemSettings | None) -> dict[str, str | None]:
    """Snapshot the rate-limit columns' raw override values as strings.

    Mirrors _tracing_override_values exactly, for the same reason: the
    audit trail must record what the admin set (including "cleared back to
    the env default", as None), not what the value happened to resolve to.
    """
    fields = (
        "rate_limit_enabled",
        "rate_limit_chat_capacity",
        "rate_limit_chat_refill_per_minute",
        "rate_limit_auth_capacity",
        "rate_limit_auth_refill_per_minute",
    )
    if db_settings is None:
        return {field: None for field in fields}

    return {
        field: None if getattr(db_settings, field) is None else str(getattr(db_settings, field))
        for field in fields
    }


def _record_rate_limit_changes(
    db: Session,
    *,
    actor_user_id: str,
    previous: dict[str, str | None],
    current: dict[str, str | None],
) -> None:
    """Append one "rate_limit.config_update" audit entry per rate-limit
    field whose value actually changed.

    Mirrors _record_tracing_changes' shape exactly (only changed fields
    recorded, one shared timestamp per request). This covers only admin
    config changes, not individual 429 trips -- see docs/SECURITY.md's
    rate-limiting section for why a trip itself is deliberately not
    audit-logged (a high-frequency operational signal, not an individual
    compliance-relevant event like a guardrail rejection).
    """
    repo = AuditLogRepository(db)
    changed_at = utc_now()

    for field, new_value in current.items():
        if previous[field] == new_value:
            continue
        repo.record(
            actor_user_id=actor_user_id,
            action="rate_limit.config_update",
            field_name=field,
            old_value=previous[field],
            new_value=new_value,
            now=changed_at,
        )


def _audit_log_ui_override_values(db_settings: SystemSettings | None) -> dict[str, str | None]:
    """Snapshot the audit_log_ui_enabled column's raw override value as a
    string.

    Mirrors _tracing_override_values exactly, for the same reason: the
    audit trail must record what the admin set (including "cleared back to
    the env default", as None), not what the value happened to resolve to.
    """
    fields = ("audit_log_ui_enabled",)
    if db_settings is None:
        return {field: None for field in fields}

    return {
        field: None if getattr(db_settings, field) is None else str(getattr(db_settings, field))
        for field in fields
    }


def _record_audit_log_ui_changes(
    db: Session,
    *,
    actor_user_id: str,
    previous: dict[str, str | None],
    current: dict[str, str | None],
) -> None:
    """Append an "audit_log_ui.config_update" audit entry if
    audit_log_ui_enabled's override actually changed.

    Mirrors _record_tracing_changes' shape exactly (only changed fields
    recorded, one shared timestamp per request).
    """
    repo = AuditLogRepository(db)
    changed_at = utc_now()

    for field, new_value in current.items():
        if previous[field] == new_value:
            continue
        repo.record(
            actor_user_id=actor_user_id,
            action="audit_log_ui.config_update",
            field_name=field,
            old_value=previous[field],
            new_value=new_value,
            now=changed_at,
        )


@router.post("/guardrail-patterns", response_model=GuardrailPatternResponse)
async def create_guardrail_pattern(
    payload: CreateGuardrailPatternRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add a custom prompt-injection detection phrase.

    pattern_text is stored and matched as a literal, case-insensitive
    substring by app.guardrails.input_guardrail.check_input -- never
    compiled as regex (see the GuardrailPattern model docstring for why
    admin-supplied regex is out of scope).
    """
    pattern = GuardrailPatternRepository(db).upsert_custom(
        label=payload.label,
        pattern_text=payload.pattern_text,
        created_by=user["user_id"],
    )
    AuditLogRepository(db).record(
        actor_user_id=user["user_id"],
        action="guardrail.pattern_update",
        field_name=pattern.id,
        old_value=None,
        new_value=pattern.pattern_text,
        now=utc_now(),
    )
    db.commit()
    return GuardrailPatternResponse.model_validate(pattern)


@router.put("/guardrail-patterns/{pattern_id}", response_model=None)
async def update_guardrail_pattern(
    pattern_id: str,
    payload: UpdateGuardrailPatternRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GuardrailPatternResponse | JSONResponse:
    """Toggle a pattern (built-in or custom) on or off.

    Toggle only -- editing a custom pattern's phrase text after creation is
    not in this issue's scope. 404 if pattern_id doesn't exist; a built-in
    pattern can be toggled here (only deletion is refused, see
    delete_guardrail_pattern).
    """
    repo = GuardrailPatternRepository(db)
    existing = repo.get(pattern_id)
    if existing is None:
        return _error_response(404, "guardrail_pattern_not_found", "Guardrail pattern not found")

    was_enabled = existing.enabled
    pattern = repo.set_enabled(pattern_id, payload.enabled)

    if was_enabled != payload.enabled:
        AuditLogRepository(db).record(
            actor_user_id=user["user_id"],
            action="guardrail.pattern_update",
            field_name=pattern_id,
            old_value="enabled" if was_enabled else "disabled",
            new_value="enabled" if payload.enabled else "disabled",
            now=utc_now(),
        )

    db.commit()
    return GuardrailPatternResponse.model_validate(pattern)


@router.delete("/guardrail-patterns/{pattern_id}", status_code=204, response_model=None)
async def delete_guardrail_pattern(
    pattern_id: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse | None:
    """Delete a custom prompt-injection detection phrase.

    404 if pattern_id doesn't exist at all; 400 if it exists but is a
    built_in row -- a built-in pattern's row carries its on/off state and
    must always exist for that toggle to mean anything, so only a custom
    row is ever deletable (see GuardrailPatternRepository.delete_custom).
    """
    repo = GuardrailPatternRepository(db)
    existing = repo.get(pattern_id)
    if existing is None:
        return _error_response(404, "guardrail_pattern_not_found", "Guardrail pattern not found")
    if existing.source != "custom":
        return _error_response(
            400,
            "guardrail_pattern_not_custom",
            "Only a custom guardrail pattern can be deleted",
        )

    pattern_text = existing.pattern_text
    repo.delete_custom(pattern_id)

    AuditLogRepository(db).record(
        actor_user_id=user["user_id"],
        action="guardrail.pattern_update",
        field_name=pattern_id,
        old_value=pattern_text,
        new_value=None,
        now=utc_now(),
    )
    db.commit()
    return None
