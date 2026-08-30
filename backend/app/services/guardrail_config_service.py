"""Guardrail config resolution: DB override over env default.

Resolves the effective guardrail policy the same way retention_service and
system_settings_service resolve their config - DB value if a row set it,
else the env default, read fresh on every call so an admin's change (via
the settings screen) takes effect on the next chat request without a
backend restart.

app.guardrails.input_guardrail / output_guardrail stay pure, DB-free
functions (see their module docstrings) - this service is the one place
that reads SystemSettings and GuardrailPatternRepository and turns them
into the plain values those pure functions accept.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SystemSettings
from app.guardrails.input_guardrail import BUILT_IN_PATTERN_LABELS
from app.repositories.guardrail_pattern_repository import GuardrailPatternRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.system_settings_service import NOT_PROVIDED, NotProvided


@dataclass(frozen=True)
class GuardrailConfig:
    """Effective guardrail policy, DB override merged over env defaults and
    the current GuardrailPattern rows.

    input_enabled/output_enabled being False is a meaningful override
    ("this guardrail is switched off"), not "not set" - resolution must
    test `is not None` rather than truthiness, the same trap
    RetentionConfig's fields guard against.
    """

    max_input_length: int
    input_enabled: bool
    output_enabled: bool
    enabled_pattern_ids: frozenset[str]
    custom_phrases: tuple[str, ...]


def _resolve_field(db_value, env_default):
    """Resolve one overridable guardrail field: the DB value if a row set
    it, else the env default.

    Must stay an `is not None` check, not a truthiness check: False
    ("turn this guardrail off") and 0 are both legitimate overrides a
    truthiness test would silently discard and replace with the env
    default - see AGENTS.md's Retention Field Semantics section.

    Not shared with retention_service._resolve_field or
    system_settings_service._resolve_field: each is typed for its own call
    sites (int | bool here; overloaded int/bool there; str there), and this
    repo's no-premature-abstraction convention (AGENTS.md) calls for
    generalizing only once a shared, identically-typed shape actually
    emerges - not preemptively.
    """
    return db_value if db_value is not None else env_default


def resolve_guardrail_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> GuardrailConfig:
    """Resolve the effective guardrail policy: DB value if set, else env
    default, plus the currently enabled built-in patterns and custom
    phrases.

    Read per-call, not cached at process start - this is the mechanism by
    which an admin's change takes effect without a restart.

    Seeds the built-in pattern rows (via
    GuardrailPatternRepository.ensure_built_ins_seeded) before reading them
    back, so a brand-new database or a code change that adds another
    built-in pattern is reflected here with no separate migration/backfill
    step - see that method's docstring.

    db_settings: the already-fetched singleton row, if the caller has one
    (see app.api.settings._to_response, which resolves provider,
    retention, and guardrail config from the same row) - avoids a
    redundant SELECT. Omit it for callers that only have a session.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    pattern_repo = GuardrailPatternRepository(db)
    pattern_repo.ensure_built_ins_seeded(BUILT_IN_PATTERN_LABELS)
    patterns = pattern_repo.list_all()

    enabled_pattern_ids = frozenset(
        pattern.id for pattern in patterns if pattern.source == "built_in" and pattern.enabled
    )
    custom_phrases = tuple(
        pattern.pattern_text
        for pattern in patterns
        if pattern.source == "custom" and pattern.enabled and pattern.pattern_text is not None
    )

    return GuardrailConfig(
        max_input_length=_resolve_field(
            db_settings.max_input_length if db_settings else None,
            settings.guardrail_max_input_length,
        ),
        input_enabled=_resolve_field(
            db_settings.guardrails_input_enabled if db_settings else None,
            settings.guardrails_input_enabled,
        ),
        output_enabled=_resolve_field(
            db_settings.guardrails_output_enabled if db_settings else None,
            settings.guardrails_output_enabled,
        ),
        enabled_pattern_ids=enabled_pattern_ids,
        custom_phrases=custom_phrases,
    )
