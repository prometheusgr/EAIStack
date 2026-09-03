"""Unit tests for audit-log-UI-visibility config resolution - TDD discipline.

Mirrors test_tracing_config_service.py's scenarios: DB override over env
default, resolved fresh per call (unlike tracing_enabled, this flag has no
process-lifetime resource tying it to startup-only resolution -- toggling
visibility of a nav button has no "requires restart" constraint, so it is
resolved per-request like guardrails_input_enabled), and `is not None`
(never truthiness) semantics per AGENTS.md's Retention Field Semantics
section.
"""

import pytest

from app.core.config import settings
from app.db.models import SystemSettings
from app.services.audit_log_ui_config_service import (
    AuditLogUiConfig,
    resolve_audit_log_ui_config,
)


@pytest.mark.unit
def test_resolve_audit_log_ui_config_falls_back_to_env_default_when_no_db_row(db_session):
    """With no SystemSettings row, the flag comes from env-level config."""
    config = resolve_audit_log_ui_config(db_session)

    assert config.enabled == settings.audit_log_ui_enabled


@pytest.mark.parametrize(
    "db_value,expected",
    [
        (None, True),  # falls back to the env default (True: transparent by default)
        (False, False),  # explicit False override must be honoured, not treated as unset
        (True, True),
    ],
)
@pytest.mark.unit
def test_resolve_audit_log_ui_config_is_not_none_semantics(db_session, db_value, expected):
    """False is a meaningful override just as much as True is - a
    truthiness check (`if audit_log_ui_enabled:`) would silently discard an
    explicit False override. This field's env default is True (unlike
    tracing_enabled's False), so the regression this guards against is a DB
    `False` being treated as "not set" and silently reverting to shown.
    """
    db_session.add(
        SystemSettings(id="default", audit_log_ui_enabled=db_value, updated_by="admin-1")
    )
    db_session.commit()

    config = resolve_audit_log_ui_config(db_session)

    assert config.enabled is expected


@pytest.mark.unit
def test_resolve_audit_log_ui_config_db_override_wins_over_env_default(db_session):
    """A DB override for audit_log_ui_enabled wins over the env default -
    the same DB-over-env precedence every other resolver in this codebase
    uses.
    """
    db_session.add(SystemSettings(id="default", audit_log_ui_enabled=False, updated_by="admin-1"))
    db_session.commit()

    config = resolve_audit_log_ui_config(db_session)

    assert config.enabled is False


@pytest.mark.unit
def test_resolve_audit_log_ui_config_returns_frozen_dataclass(db_session):
    """AuditLogUiConfig mirrors TracingConfig/GuardrailConfig's shape: a
    frozen dataclass, not a mutable object callers could accidentally
    mutate.
    """
    config = resolve_audit_log_ui_config(db_session)

    assert isinstance(config, AuditLogUiConfig)
    with pytest.raises(Exception):
        config.enabled = True  # type: ignore[misc]
