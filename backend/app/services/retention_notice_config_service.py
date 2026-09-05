"""Retention-notice-visibility config resolution: DB override over env default.

Resolves whether the end-user-facing retention notice (issue #49) should be
shown, the same way audit_log_ui_config_service resolves its flag - DB value
if a row set it, else the env default, read fresh on every call so an
admin's change takes effect on the next page load without a backend
restart. This flag controls only whether the notice is shown; the retention
*values* it reports come from app.services.retention_service.resolve_retention_config.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SystemSettings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.config_resolution import resolve_field
from app.services.system_settings_service import NOT_PROVIDED, NotProvided


@dataclass(frozen=True)
class RetentionNoticeConfig:
    """Effective retention-notice-visibility policy, DB override merged over
    the env default.

    enabled being False is a meaningful override ("hide this notice"), not
    "not set" - resolution must test `is not None` rather than truthiness,
    the same trap every other *_config_service in this module guards
    against.
    """

    enabled: bool


def resolve_retention_notice_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> RetentionNoticeConfig:
    """Resolve whether the end-user retention notice should be shown: DB
    value if set, else the env default.

    db_settings: the already-fetched singleton row, if the caller has one
    (see app.api.settings._to_response) - avoids a redundant SELECT. Omit it
    for callers that only have a session.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return RetentionNoticeConfig(
        enabled=resolve_field(
            db_value=db_settings.retention_notice_enabled if db_settings else None,
            env_default=settings.retention_notice_enabled,
        )
    )
