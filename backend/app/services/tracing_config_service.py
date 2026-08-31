"""Tracing config resolution: DB override over env default.

Resolves the effective tracing on/off switch the same way
guardrail_config_service and retention_service resolve their config - DB
value if a row set it, else the env default. Unlike those services'
callers, resolve_tracing_config is called exactly once, at process startup
(app.main's lifespan hook), not per-request: there is no supported way to
re-instrument OpenTelemetry's global tracer provider on a running process
(see app.core.tracing), so an admin's change via the settings screen takes
effect only after the next backend restart. The resolver itself stays a
plain, stateless DB-read for consistency with its siblings and so it can be
unit tested the same way - the "once at startup" constraint lives in the
caller, not here.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SystemSettings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.system_settings_service import NOT_PROVIDED, NotProvided


@dataclass(frozen=True)
class TracingConfig:
    """Effective tracing policy, DB override merged over the env default."""

    enabled: bool


def _resolve_field(db_value: bool | None, env_default: bool) -> bool:
    """Resolve the tracing_enabled field: the DB value if a row set it,
    else the env default.

    Must stay an `is not None` check, not a truthiness check: an explicit
    DB `False` ("tracing is off") must not be treated as unset and silently
    replaced with the env default - see AGENTS.md's Retention Field
    Semantics section.

    Not shared with guardrail_config_service._resolve_field or the other
    sibling resolvers, per this repo's no-premature-abstraction convention
    (AGENTS.md) - each service keeps its own even though the bodies are
    identical, since generalizing now would only save one line per service.
    """
    return db_value if db_value is not None else env_default


def resolve_tracing_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> TracingConfig:
    """Resolve the effective tracing config: DB value if set, else env default.

    db_settings: the already-fetched singleton row, if the caller has one
    (see app.api.settings._to_response, which resolves provider, retention,
    and guardrail config from the same row) - avoids a redundant SELECT.
    Omit it for callers that only have a session.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return TracingConfig(
        enabled=_resolve_field(
            db_settings.tracing_enabled if db_settings else None,
            settings.tracing_enabled,
        )
    )
