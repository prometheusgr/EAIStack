"""Tests for the shared config-field resolver used by every *_config_service
module (system_settings_service, retention_service, guardrail_config_service,
tracing_config_service, rate_limit_config_service).

Generalized here per system_settings_service._resolve_field's own,
self-predicted threshold ("if a third resolver with a different type ever
shows up, that's the point to generalize... not before") - five near-
identical copies had accumulated (str-typed, int|bool-typed x2, bool-typed,
and an @overload'd int|bool|None-typed one in retention_service) before this
generalization happened. One generic, correctly-typed function replaces all
five bodies; each service still owns its own resolve_*_config functions and
dataclasses - only the one-line is-not-None resolution step is shared.
"""

import pytest

from app.services.config_resolution import resolve_field


@pytest.mark.unit
def test_resolve_field_returns_db_value_when_set():
    assert resolve_field(db_value="override", env_default="default") == "override"


@pytest.mark.unit
def test_resolve_field_falls_back_to_env_default_when_db_value_is_none():
    assert resolve_field(db_value=None, env_default="default") == "default"


@pytest.mark.unit
@pytest.mark.parametrize(
    "db_value,env_default,expected",
    [
        (False, True, False),  # explicit DB False must win, not be treated as unset
        (0, 24, 0),  # explicit DB 0 ("purge immediately"/"zero capacity") must win
        ("", "fallback", ""),  # explicit DB empty string must win
        (None, True, True),
        (None, 24, 24),
        (None, None, None),  # both unset - env default is itself None ("keep forever")
    ],
)
def test_resolve_field_uses_is_not_none_semantics_never_truthiness(db_value, env_default, expected):
    """The one behavior every _resolve_field copy across this codebase
    existed to guarantee (see AGENTS.md's Retention Field Semantics
    section) - a truthiness check (`db_value or env_default`) would
    silently discard a meaningful False/0/"" override.
    """
    assert resolve_field(db_value=db_value, env_default=env_default) == expected
