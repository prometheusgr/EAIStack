"""Rate limit config resolution: DB override over env default.

Resolves the effective rate-limiting policy the same way
guardrail_config_service and tracing_config_service resolve their config -
DB value if a row set it, else the env default, read fresh on every call so
an admin's change (via the settings screen) takes effect on the next
request with no backend restart.

app.ratelimit.token_bucket stays a pure, DB-free module (see its module
docstring) - this service is the one place that reads SystemSettings and
turns it into the plain capacity/refill values that module accepts.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SystemSettings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.system_settings_service import NOT_PROVIDED, NotProvided


@dataclass(frozen=True)
class RateLimitConfig:
    """Effective rate-limiting policy, DB override merged over env defaults.

    enabled being False is a meaningful override ("rate limiting is off
    entirely"), not "not set" - resolution must test `is not None` rather
    than truthiness, the same trap every other config field in this
    codebase guards against (see AGENTS.md's Retention Field Semantics).

    One shared enabled switch covers both chat and auth limiting, not two
    independent switches like the guardrails' input/output split: both
    limiters share the same trip behavior (429 + Retry-After) and
    mechanism, unlike the guardrails' reject-vs-sanitize split that
    justified separate switches there.
    """

    enabled: bool
    chat_capacity: int
    chat_refill_per_minute: int
    auth_capacity: int
    auth_refill_per_minute: int


def _resolve_field(db_value, env_default):
    """Resolve one overridable rate-limit field: the DB value if a row set
    it, else the env default.

    Must stay an `is not None` check, not a truthiness check: an explicit
    DB `False` for `enabled` must not be treated as unset and silently
    replaced with the env default - see AGENTS.md's Retention Field
    Semantics section.

    Not shared with guardrail_config_service._resolve_field or the other
    sibling resolvers, per this repo's no-premature-abstraction convention
    (AGENTS.md) - each service keeps its own even though the bodies are
    identical.
    """
    return db_value if db_value is not None else env_default


def resolve_rate_limit_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> RateLimitConfig:
    """Resolve the effective rate-limiting policy: DB value if set, else env
    default, for every field.

    db_settings: the already-fetched singleton row, if the caller has one
    (see app.api.settings._to_response, which resolves provider, retention,
    guardrail, tracing, and rate-limit config from the same row) - avoids a
    redundant SELECT. Omit it for callers that only have a session.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return RateLimitConfig(
        enabled=_resolve_field(
            db_settings.rate_limit_enabled if db_settings else None,
            settings.rate_limit_enabled,
        ),
        chat_capacity=_resolve_field(
            db_settings.rate_limit_chat_capacity if db_settings else None,
            settings.rate_limit_chat_capacity,
        ),
        chat_refill_per_minute=_resolve_field(
            db_settings.rate_limit_chat_refill_per_minute if db_settings else None,
            settings.rate_limit_chat_refill_per_minute,
        ),
        auth_capacity=_resolve_field(
            db_settings.rate_limit_auth_capacity if db_settings else None,
            settings.rate_limit_auth_capacity,
        ),
        auth_refill_per_minute=_resolve_field(
            db_settings.rate_limit_auth_refill_per_minute if db_settings else None,
            settings.rate_limit_auth_refill_per_minute,
        ),
    )
