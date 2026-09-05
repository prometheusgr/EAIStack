# Audit Events

This document specifies what gets recorded in the audit trail (`audit_logs` table, `AuditLog` model in `backend/app/db/models.py`) and the pattern for adding a new audited action. It is the audit counterpart to the retention policy table in [docs/SECURITY.md](SECURITY.md) — retention says how long data lives, this says who changed what and when.

## What the audit trail is for

The audit trail exists to answer, after the fact: **who changed this security-relevant setting, when, and what was it before?** It is not a general application log, not a request log, and not a replacement for `AuditLog`-adjacent business data (e.g. conversation history lives in its own tables). Scope is deliberately narrow: admin-facing configuration that affects other users' data (retention windows, session cleanup policy) or account security.

## Storage shape

One row per changed field, per change (`backend/app/db/models.py`, `AuditLog`):

| Column | Type | Meaning |
|---|---|---|
| `id` | `str` (UUID) | Primary key |
| `actor_user_id` | `str` | Who made the change (not who owns the affected row — see below) |
| `action` | `str` | Dot-namespaced event name, e.g. `retention.update` |
| `field_name` | `str` | Which field changed |
| `old_value` | `str \| None` | Value before the change, as a string. `None` means "had no DB override" (was using the env default), distinct from the literal string `"None"` |
| `new_value` | `str \| None` | Value after the change, same string convention |
| `created_at` | `datetime` | When, stamped once per request via injected `now` (see [docs/TIME_INJECTION.md](TIME_INJECTION.md)) — not per-row, so a multi-field change reads as one event when entries share a timestamp |

`old_value`/`new_value` are strings rather than typed columns so one table covers int, bool, and future field types without a column per setting.

**Not user-scoped in the usual sense.** `actor_user_id` is who made the change, not who owns the affected row, so the per-user read-isolation pattern in [docs/REPOSITORY_PATTERN.md](REPOSITORY_PATTERN.md) does not apply here. Reads are gated by `require_admin` (realm-role RBAC) instead, at the endpoint level.

## Append-only, structurally

`AuditLogRepository` (`backend/app/repositories/audit_log_repository.py`) exposes exactly two methods: `record()` and `list_recent()`. No `update`, `delete`, `remove`, or `purge` method exists on the class — not "isn't called," does not exist. This is enforced two ways:

1. **`backend/tests/unit/test_audit_log_repository.py`** asserts the repository's exact public method set (`{"db", "record", "list_recent"}`).
2. **`python tools/lint_repositories.py`** (gated in CI) statically flags any `*Repository` class whose name contains `Audit` or `Log` if it defines a method named or prefixed `update`, `delete`, `remove`, or `purge`. A future append-only store is covered automatically as long as its class name says so — see the Repository Checklist in [AGENTS.md](../AGENTS.md).

`app.services.retention_service` never queries `AuditLog` at all, so no purge sweep — scheduled or logout-triggered — can touch audit history, independent of the repository's method set. See the retention policy table in [docs/SECURITY.md](SECURITY.md) for the exemption.

## Events recorded today

| Action | Trigger | Where |
|---|---|---|
| `retention.update` | An admin changes a retention field (`conversation_retention_hours`, `cleanup_on_logout`, `knowledge_base_purge_days`, `api_key_purge_days`) via the Settings UI | `backend/app/api/settings.py`, `_record_retention_changes()` |
| `guardrail.config_update` | An admin changes a guardrail scalar field (`max_input_length`, `guardrails_input_enabled`, `guardrails_output_enabled`) via the Settings UI | `backend/app/api/settings.py`, `_record_guardrail_changes()` |
| `guardrail.pattern_update` | An admin adds, toggles, or deletes a guardrail pattern (built-in or custom) | `backend/app/api/settings.py`, `create_guardrail_pattern()` / `update_guardrail_pattern()` / `delete_guardrail_pattern()` |
| `guardrail.input_rejected` | The input guardrail rejects a chat message at request time (a runtime event, not an admin config change) | `backend/app/services/chat_guardrail_service.py` |
| `guardrail.output_redacted` | The output guardrail sanitizes an agent response before it's returned (a runtime event, not an admin config change) | `backend/app/services/chat_guardrail_service.py` |
| `tracing.config_update` | An admin changes `tracing_enabled` via the Settings UI (takes effect on the next backend restart, not immediately — see `docs/OBSERVABILITY.md`) | `backend/app/api/settings.py`, `_record_tracing_changes()` |
| `rate_limit.config_update` | An admin changes a rate-limit field (`rate_limit_enabled`, chat/auth capacity and refill rate) via the Settings UI | `backend/app/api/settings.py`, `_record_rate_limit_changes()` |
| `audit_log_ui.config_update` | An admin changes `audit_log_ui_enabled` (whether the in-product Audit Log view is shown) via the Settings UI | `backend/app/api/settings.py`, `_record_audit_log_ui_changes()` |
| `retention_notice.config_update` | An admin changes `retention_notice_enabled` (whether the end-user-facing retention notice is shown in the chat UI) via the Settings UI | `backend/app/api/settings.py`, `_record_retention_notice_changes()` |

Only fields whose value actually changed produce an entry — re-saving the settings form without touching a given field writes zero rows for it. All entries from one request share a single `now` timestamp so a multi-field change is legible as one event.

**Not yet instrumented:** API key creation/revocation, LLM/embedding provider switches, and login/logout events are not currently written to the audit trail. If a future phase needs those, add them following the pattern below rather than extending `AuditLog`'s scope implicitly.

## Reading the trail

`GET /api/settings/audit` (`backend/app/api/settings.py`), admin-only via `require_admin`, returns entries newest-first via `AuditLogRepository.list_recent(limit=100)`. There is no filtering by field or actor yet — add query parameters to the endpoint if that becomes necessary, not a new repository method.

**In-product viewer (issue #45):** the same endpoint now also backs an in-app "Audit Log" screen (`frontend/src/components/AuditLog.tsx`), reachable from the main nav alongside Settings — an admin no longer needs direct database access to read the trail. Its visibility is admin-configurable via `audit_log_ui_enabled` (env-default `True` — transparent by default, resolved per-request the same way as the guardrail/rate-limit switches — see `backend/app/services/audit_log_ui_config_service.py`), for forks that route audit consumption through an external SIEM instead and want the in-app view hidden. Changing this flag is itself audit-logged as `audit_log_ui.config_update`, same as every other admin-configurable switch.

## Pattern: adding a new audited action

1. **Confirm it belongs here.** Is this a security-relevant configuration change made by one user that affects data or behavior beyond that single request? If it's routine application data (a chat message, a thread rename), it doesn't belong in `AuditLog`.
2. **Pick an `action` name** in `<domain>.<verb>` form (e.g. `retention.update`, `apikey.revoke`). Keep the domain consistent with existing actions where one exists.
3. **Call `AuditLogRepository.record()` in the same transaction** as the change it documents — don't commit the audit entry separately, and don't commit before validating the change succeeded:
   ```python
   @router.post("/api/apikeys")
   async def create_apikey(
       payload: APIKeyCreate,
       user: dict = Depends(get_current_user),
       db: Session = Depends(get_db),
   ):
       key = APIKeyRepository(db).create(user_id=user["user_id"], ...)
       AuditLogRepository(db).record(
           actor_user_id=user["user_id"],
           action="apikey.create",
           field_name="api_key",
           old_value=None,
           new_value=key.id,
           now=utc_now(),
       )
       db.commit()  # one transaction covers both the change and its audit entry
       return key
   ```
4. **Pass `now` in**, don't call the clock inside the handler — see [docs/TIME_INJECTION.md](TIME_INJECTION.md). If a request writes several entries, compute `now` once and reuse it so they share a timestamp.
5. **Write the test first** (TDD, per [AGENTS.md](../AGENTS.md)): assert the entry's `action`, `field_name`, `old_value`/`new_value`, and that no entry is written when nothing changed.
6. **Add a row to the table above** in this document once the action ships.

## Non-goals

- **Not a general request/access log.** Every read or routine request does not need an audit entry — only changes to security-relevant configuration.
- **Not time-travel/replay.** The trail records that a change happened and its before/after values, not enough state to reconstruct or replay the full system at a point in time.
- **Not a substitute for retention documentation.** How long non-audit data lives is answered by [docs/SECURITY.md](SECURITY.md)'s retention table, not this document.
