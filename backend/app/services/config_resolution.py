"""Shared one-field config resolution: DB override if set, else env default.

Every *_config_service module in app.services (system_settings_service,
retention_service, guardrail_config_service, tracing_config_service,
rate_limit_config_service) resolves each of its fields the same way: the
value from the SystemSettings singleton row if an admin has set one, else
the env-level Settings default. This module holds that one shared step;
each service still owns its own resolve_*_config function, its own
dataclass, and its own field list - only the repeated is-not-None
resolution line is centralized.

Generalized here per system_settings_service._resolve_field's own,
self-predicted threshold: "If a third resolver with a different type ever
shows up, that's the point to generalize both into one generic function —
not before" (AGENTS.md's no-premature-abstraction convention). Five
near-identical copies had accumulated by the time rate_limit_config_service
added a fifth - past the point that comment named, and worth generalizing
now rather than a sixth time.
"""

from typing import TypeVar

T = TypeVar("T")


def resolve_field(*, db_value: T | None, env_default: T) -> T:
    """Resolve one overridable config field.

    No @overload split for callers whose env_default is itself Optional
    (e.g. retention_service's knowledge_base_purge_days: int | None = 30,
    where None legitimately means "keep forever"): T unifies with `int |
    None` directly at those call sites, since nothing here requires T to
    exclude None - a single signature already covers both shapes correctly,
    with no spurious `| None` forced onto the always-non-None call sites'
    results (T is inferred as the narrower type there instead). An earlier
    version of this function tried an explicit two-overload split for this
    same reason and found mypy rejects it: with both overloads generic in
    an unbound TypeVar, mypy sees the non-Optional overload as already
    covering everything the Optional one could match. This plain signature
    is both simpler and the only variant mypy accepts.

    Must stay an `is not None` check, not a truthiness check: an explicit
    DB override of False, 0, or "" is meaningful and distinct from "unset"
    for several fields across this codebase (rate_limit_enabled=False,
    conversation_retention_hours=0, the 'fake' LLM provider's url="") - a
    truthiness check would silently discard any of these and fall back to
    the env default instead. See AGENTS.md's Retention Field Semantics
    section for the full rationale and the incidents this guards against.
    """
    return db_value if db_value is not None else env_default
