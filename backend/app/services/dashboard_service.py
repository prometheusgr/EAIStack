"""Admin dashboard aggregation: one status snapshot from several sources.

Issue #48: an admin has no single place to see what the system is
currently doing -- rate-limit bucket state, guardrail trip counts, and
tracing status each exist in the backend today but have no shared view.
This module assembles a real-data snapshot from each existing source
rather than introducing new tracked metrics, per the issue's "each tile
must be backed by a real data path" requirement:

- Rate limiting: app.services.rate_limiter_service.bucket_count() (the only
  existing introspection hook) plus the resolved on/off config. There is no
  data source for "recent 429 count" -- rate-limit trips are deliberately
  not audit-logged (see docs/SECURITY.md's Rate Limiting section) -- so
  that figure is intentionally not part of this snapshot, not an oversight.
- Guardrails: per-pattern guardrail.input_rejected trip counts and a bare
  guardrail.output_redacted count, aggregated from the audit trail via
  AuditLogRepository.count_by_action_and_value_since over a recent window
  (RECENT_WINDOW below). Output redactions have no per-pattern breakdown
  available by design -- filter_agent_response never logs which pattern
  matched, only that a redaction happened (see chat_guardrail_service),
  since the redacted content itself must never be audit-logged.
- Tracing: both the DB-desired state (resolve_tracing_config) and the
  process-actual state (app.core.tracing.is_tracing_configured) are
  reported, since they can genuinely diverge -- an admin's settings-screen
  change only takes effect after the next backend restart. Also carries the
  browser-facing Phoenix UI URL for an outbound link.
- keycloak_console_url (issue #40): the browser-facing Keycloak admin
  console root backing the frontend's "User Management" nav deep link.
  Falls back to keycloak_url when keycloak_console_url is unset, the same
  override-with-default shape as every other admin-configurable URL here.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tracing import is_tracing_configured
from app.repositories import AuditLogRepository
from app.services.rate_limit_config_service import resolve_rate_limit_config
from app.services.rate_limiter_service import bucket_count
from app.services.tracing_config_service import resolve_tracing_config

# How far back to look for guardrail trip counts. A fixed window, not a
# configurable one: this is a glance-level operational signal, not a
# reporting feature, so one sensible default (matching a typical admin's
# "what's happened today/this shift" mental model) is enough for v1.
RECENT_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class RateLimitStatus:
    enabled: bool
    active_bucket_count: int


@dataclass(frozen=True)
class GuardrailStatus:
    input_rejected_counts_by_pattern: dict[str, int]
    output_redacted_count: int


@dataclass(frozen=True)
class TracingStatus:
    db_desired_enabled: bool
    process_actually_configured: bool
    phoenix_ui_url: str


@dataclass(frozen=True)
class DashboardStatus:
    rate_limit: RateLimitStatus
    guardrails: GuardrailStatus
    tracing: TracingStatus
    keycloak_console_url: str


def resolve_dashboard_status(db: Session, *, now: datetime) -> DashboardStatus:
    """Assemble the admin dashboard's status snapshot.

    now is injected (see docs/TIME_INJECTION.md) so the recent-window
    cutoff for guardrail trip counts is deterministic under test.
    """
    rate_limit_config = resolve_rate_limit_config(db)
    tracing_config = resolve_tracing_config(db)

    audit_repo = AuditLogRepository(db)
    since = now - RECENT_WINDOW
    input_rejected_counts = audit_repo.count_by_action_and_value_since(
        "guardrail.input_rejected", since=since
    )
    output_redacted_counts = audit_repo.count_by_action_and_value_since(
        "guardrail.output_redacted", since=since
    )

    return DashboardStatus(
        rate_limit=RateLimitStatus(
            enabled=rate_limit_config.enabled,
            active_bucket_count=bucket_count(),
        ),
        guardrails=GuardrailStatus(
            input_rejected_counts_by_pattern=input_rejected_counts,
            output_redacted_count=sum(output_redacted_counts.values()),
        ),
        tracing=TracingStatus(
            db_desired_enabled=tracing_config.enabled,
            process_actually_configured=is_tracing_configured(),
            phoenix_ui_url=settings.tracing_ui_url,
        ),
        keycloak_console_url=settings.keycloak_console_url or settings.keycloak_url,
    )
