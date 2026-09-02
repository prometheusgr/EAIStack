"""Audit-log-UI-visibility config resolution: DB override over env default.

Resolves whether the in-product Audit Log admin view (issue #45) should be
shown, the same way guardrail_config_service and rate_limit_config_service
resolve their config - DB value if a row set it, else the env default, read
fresh on every call so an admin's change (via the settings screen) takes
effect on the next page load without a backend restart. Unlike
tracing_config_service, there is no process-lifetime resource tying this
flag to startup-only resolution - hiding/showing a nav button and view is a
pure per-request decision.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SystemSettings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.config_resolution import resolve_field
from app.services.system_settings_service import NOT_PROVIDED, NotProvided


@dataclass(frozen=True)
class AuditLogUiConfig:
    """Effective audit-log-UI-visibility policy, DB override merged over the
    env default.

    enabled being False is a meaningful override ("hide this view"), not
    "not set" - resolution must test `is not None` rather than truthiness,
    the same trap every other *_config_service in this module guards
    against.
    """

    enabled: bool


def resolve_audit_log_ui_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> AuditLogUiConfig:
    """Resolve whether the Audit Log admin view should be shown: DB value if
    set, else the env default.

    db_settings: the already-fetched singleton row, if the caller has one
    (see app.api.settings._to_response, which resolves provider, retention,
    guardrail, tracing, and rate-limit config from the same row) - avoids a
    redundant SELECT. Omit it for callers that only have a session.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return AuditLogUiConfig(
        enabled=resolve_field(
            db_value=db_settings.audit_log_ui_enabled if db_settings else None,
            env_default=settings.audit_log_ui_enabled,
        )
    )
