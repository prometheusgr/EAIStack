"""Unit tests for guardrail config resolution - TDD discipline.

Mirrors test_retention_service.py's config-resolution scenarios: DB
override over env default, resolved fresh per call, `is not None` (never
truthiness) semantics for nullable bool/int fields per AGENTS.md's
Retention Field Semantics section.
"""

import pytest

from app.core.config import settings
from app.db.models import GuardrailPattern, SystemSettings
from app.services.guardrail_config_service import GuardrailConfig, resolve_guardrail_config


@pytest.mark.unit
def test_resolve_guardrail_config_falls_back_to_env_defaults_when_no_db_row(db_session):
    """With no SystemSettings row, guardrail config comes from env-level
    config.
    """
    config = resolve_guardrail_config(db_session)

    assert config.max_input_length == settings.guardrail_max_input_length
    assert config.input_enabled == settings.guardrails_input_enabled
    assert config.output_enabled == settings.guardrails_output_enabled


@pytest.mark.unit
def test_resolve_guardrail_config_max_input_length_db_override_wins(db_session):
    """A DB override for max_input_length wins over the env default -- the
    no-restart mechanism, same as every other resolver in this codebase.
    """
    db_session.add(SystemSettings(id="default", max_input_length=500, updated_by="admin-1"))
    db_session.commit()

    config = resolve_guardrail_config(db_session)

    assert config.max_input_length == 500


@pytest.mark.unit
def test_resolve_guardrail_config_max_input_length_none_falls_back_to_env(db_session):
    """An explicit NULL override (the row exists, but this field wasn't
    set) falls back to the env default, not to 0 or some other sentinel.
    """
    db_session.add(SystemSettings(id="default", max_input_length=None, updated_by="admin-1"))
    db_session.commit()

    config = resolve_guardrail_config(db_session)

    assert config.max_input_length == settings.guardrail_max_input_length


@pytest.mark.parametrize(
    "db_value,expected",
    [
        (None, True),  # falls back to the env default (True)
        (False, False),  # explicit False override must be honoured, not treated as unset
        (True, True),
    ],
)
@pytest.mark.unit
def test_resolve_guardrail_config_input_enabled_is_not_none_semantics(
    db_session, db_value, expected
):
    """False is a meaningful override ("turn the input guardrail off"), not
    a falsy "not set" -- the same truthiness trap AGENTS.md's Retention
    Field Semantics section warns about. Guards against a regression to
    `if guardrails_input_enabled:`-style resolution, which would silently
    discard an explicit False and re-enable the guardrail.
    """
    db_session.add(
        SystemSettings(id="default", guardrails_input_enabled=db_value, updated_by="admin-1")
    )
    db_session.commit()

    config = resolve_guardrail_config(db_session)

    assert config.input_enabled is expected


@pytest.mark.parametrize(
    "db_value,expected",
    [
        (None, True),
        (False, False),
        (True, True),
    ],
)
@pytest.mark.unit
def test_resolve_guardrail_config_output_enabled_is_not_none_semantics(
    db_session, db_value, expected
):
    """Same is-not-None guard as input_enabled, for the output guardrail's
    switch.
    """
    db_session.add(
        SystemSettings(id="default", guardrails_output_enabled=db_value, updated_by="admin-1")
    )
    db_session.commit()

    config = resolve_guardrail_config(db_session)

    assert config.output_enabled is expected


@pytest.mark.unit
def test_resolve_guardrail_config_seeds_built_in_patterns(db_session):
    """Resolution seeds every built-in pattern id (idempotently) so the
    settings screen and check_input always see the full built-in list, even
    on a brand-new database with no prior seeding call.
    """
    resolve_guardrail_config(db_session)

    rows = db_session.query(GuardrailPattern).filter(GuardrailPattern.source == "built_in").all()
    assert len(rows) > 0


@pytest.mark.unit
def test_resolve_guardrail_config_enabled_pattern_ids_excludes_disabled_built_ins(db_session):
    """enabled_pattern_ids reflects only built-in rows where enabled=True --
    a disabled built-in pattern's id must not appear."""
    resolve_guardrail_config(db_session)  # seed
    disabled_row = db_session.query(GuardrailPattern).filter_by(source="built_in").first()
    disabled_row.enabled = False
    db_session.commit()

    config = resolve_guardrail_config(db_session)

    assert disabled_row.id not in config.enabled_pattern_ids


@pytest.mark.unit
def test_resolve_guardrail_config_custom_phrases_reflects_enabled_custom_rows(db_session):
    """custom_phrases holds the pattern_text of enabled custom rows only --
    a disabled custom phrase must not be included."""
    db_session.add(
        GuardrailPattern(
            id="custom-1",
            source="custom",
            label="Enabled custom",
            pattern_text="leak the secret sauce",
            enabled=True,
        )
    )
    db_session.add(
        GuardrailPattern(
            id="custom-2",
            source="custom",
            label="Disabled custom",
            pattern_text="do not include this",
            enabled=False,
        )
    )
    db_session.commit()

    config = resolve_guardrail_config(db_session)

    assert "leak the secret sauce" in config.custom_phrases
    assert "do not include this" not in config.custom_phrases


@pytest.mark.unit
def test_resolve_guardrail_config_returns_frozen_dataclass(db_session):
    """GuardrailConfig mirrors RetentionConfig's shape: a frozen dataclass,
    not a mutable object callers could accidentally mutate.
    """
    config = resolve_guardrail_config(db_session)

    assert isinstance(config, GuardrailConfig)
    with pytest.raises(Exception):
        config.max_input_length = 1  # type: ignore[misc]
