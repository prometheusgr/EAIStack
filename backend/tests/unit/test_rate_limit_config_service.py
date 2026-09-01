"""Unit tests for rate-limit config resolution - TDD discipline.

Mirrors test_tracing_config_service.py's/test_guardrail_config_service.py's
config-resolution scenarios: DB override over env default, resolved fresh
per call, and `is not None` (never truthiness) semantics per AGENTS.md's
Retention Field Semantics section.
"""

import pytest

from app.core.config import settings
from app.db.models import SystemSettings
from app.services.rate_limit_config_service import RateLimitConfig, resolve_rate_limit_config


@pytest.mark.unit
def test_resolve_rate_limit_config_falls_back_to_env_defaults_when_no_db_row(db_session):
    """With no SystemSettings row, rate limit config comes from env-level config."""
    config = resolve_rate_limit_config(db_session)

    assert config.enabled == settings.rate_limit_enabled
    assert config.chat_capacity == settings.rate_limit_chat_capacity
    assert config.chat_refill_per_minute == settings.rate_limit_chat_refill_per_minute
    assert config.auth_capacity == settings.rate_limit_auth_capacity
    assert config.auth_refill_per_minute == settings.rate_limit_auth_refill_per_minute


@pytest.mark.parametrize(
    "db_value,expected",
    [
        (None, True),  # falls back to the env default (True)
        (False, False),  # explicit False override must be honoured, not treated as unset
        (True, True),
    ],
)
@pytest.mark.unit
def test_resolve_rate_limit_config_enabled_is_not_none_semantics(db_session, db_value, expected):
    """False is a meaningful override ("rate limiting is off") just as much
    as True is - a truthiness check would silently discard an explicit
    False the same way it would for guardrails_input_enabled.
    """
    db_session.add(SystemSettings(id="default", rate_limit_enabled=db_value, updated_by="admin-1"))
    db_session.commit()

    config = resolve_rate_limit_config(db_session)

    assert config.enabled is expected


@pytest.mark.unit
def test_resolve_rate_limit_config_db_override_wins_over_env_default(db_session):
    """A DB override for every rate-limit field wins over its env default -
    the same DB-over-env precedence every other resolver in this codebase
    uses.
    """
    db_session.add(
        SystemSettings(
            id="default",
            rate_limit_enabled=False,
            rate_limit_chat_capacity=3,
            rate_limit_chat_refill_per_minute=2,
            rate_limit_auth_capacity=5,
            rate_limit_auth_refill_per_minute=4,
            updated_by="admin-1",
        )
    )
    db_session.commit()

    config = resolve_rate_limit_config(db_session)

    assert config.enabled is False
    assert config.chat_capacity == 3
    assert config.chat_refill_per_minute == 2
    assert config.auth_capacity == 5
    assert config.auth_refill_per_minute == 4


@pytest.mark.unit
def test_resolve_rate_limit_config_returns_frozen_dataclass(db_session):
    """RateLimitConfig mirrors GuardrailConfig/TracingConfig's shape: a
    frozen dataclass, not a mutable object callers could accidentally
    mutate.
    """
    config = resolve_rate_limit_config(db_session)

    assert isinstance(config, RateLimitConfig)
    with pytest.raises(Exception):
        config.enabled = False  # type: ignore[misc]
