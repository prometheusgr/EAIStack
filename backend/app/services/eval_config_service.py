"""Workflow eval-run config resolution: DB override over env default.

Resolves the per-case-run timeout for workflow eval runs (issue #84) the
same way the other *_config_service modules resolve theirs - DB value if a
row set it, else the env default. Read once when an eval run starts, so a
change applies to the next eval run, never to one already executing.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SystemSettings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.config_resolution import resolve_field
from app.services.system_settings_service import NOT_PROVIDED, NotProvided


@dataclass(frozen=True)
class EvalConfig:
    """Effective eval-run policy, DB override merged over the env default."""

    case_run_timeout_seconds: int


def resolve_eval_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> EvalConfig:
    """Resolve the effective eval config: DB value if set, else env default.

    db_settings: the already-fetched singleton row, if the caller has one
    (see app.api.settings._to_response) - avoids a redundant SELECT.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return EvalConfig(
        case_run_timeout_seconds=resolve_field(
            db_value=db_settings.eval_case_run_timeout_seconds if db_settings else None,
            env_default=settings.eval_case_run_timeout_seconds,
        )
    )
