"""Unit tests for tracing config resolution - TDD discipline.

Mirrors test_guardrail_config_service.py's config-resolution scenarios: DB
override over env default, resolved fresh per call (the resolver itself is
pure and stateless - the fact that app.main only actually calls it once, at
process startup, is a caller-side decision documented on
resolve_tracing_config, not something this resolver enforces), and
`is not None` (never truthiness) semantics per AGENTS.md's Retention Field
Semantics section.
"""

import pytest

from app.core.config import settings
from app.db.models import SystemSettings
from app.services.tracing_config_service import TracingConfig, resolve_tracing_config


@pytest.mark.unit
def test_resolve_tracing_config_falls_back_to_env_default_when_no_db_row(db_session):
    """With no SystemSettings row, tracing config comes from env-level config."""
    config = resolve_tracing_config(db_session)

    assert config.enabled == settings.tracing_enabled


@pytest.mark.parametrize(
    "db_value,expected",
    [
        (None, False),  # falls back to the env default (False)
        (False, False),  # explicit False override must be honoured, not treated as unset
        (True, True),
    ],
)
@pytest.mark.unit
def test_resolve_tracing_config_is_not_none_semantics(db_session, db_value, expected):
    """False is a meaningful override just as much as True is - a
    truthiness check (`if tracing_enabled:`) would silently discard an
    explicit False the same way it would for guardrails_input_enabled. This
    field's env default happens to already be False, so the regression this
    guards against is a DB `False` being treated as "not set" and falling
    back to... False again, which is why the True case matters most here.
    """
    db_session.add(SystemSettings(id="default", tracing_enabled=db_value, updated_by="admin-1"))
    db_session.commit()

    config = resolve_tracing_config(db_session)

    assert config.enabled is expected


@pytest.mark.unit
def test_resolve_tracing_config_db_override_wins_over_env_default(db_session):
    """A DB override for tracing_enabled wins over the env default - the
    same DB-over-env precedence every other resolver in this codebase uses.
    """
    db_session.add(SystemSettings(id="default", tracing_enabled=True, updated_by="admin-1"))
    db_session.commit()

    config = resolve_tracing_config(db_session)

    assert config.enabled is True


@pytest.mark.unit
def test_resolve_tracing_config_returns_frozen_dataclass(db_session):
    """TracingConfig mirrors GuardrailConfig/RetentionConfig's shape: a
    frozen dataclass, not a mutable object callers could accidentally
    mutate.
    """
    config = resolve_tracing_config(db_session)

    assert isinstance(config, TracingConfig)
    with pytest.raises(Exception):
        config.enabled = True  # type: ignore[misc]
