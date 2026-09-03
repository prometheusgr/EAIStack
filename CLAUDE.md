# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Enterprise AI Stack**: a forkable Kubernetes-native template for building offline/air-gapped enterprise AI applications.

**Core stack**: React/TypeScript frontend, FastAPI backend, LangGraph agent orchestration, Keycloak auth, PostgreSQL + pgvector, MinIO object storage, llama.cpp (llama-server) for local LLM inference, MCP servers for tool integration.

**Key constraints**:
- Fully air-gapped (no internet at runtime; all dependencies vendored)
- Kubernetes-native (K3s as the target, production-grade but approachable for K8s-unfamiliar users)
- Thin vertical slice first (one complete flow: login → chat → agent-with-tool → grounded response)
- Strict TDD discipline (mock LLM boundary, TDD everything else; CI gates every commit)

## Current Status

**Phase 1 Complete ✓**: Authentication & local dev loop (Keycloak OIDC + JWT validation + protected endpoints)

**Phase 2 Complete ✓**: Agent Orchestration & LLM Integration
- Backend: `POST /api/agents/chat` endpoint + LangGraph agent
- Frontend: Chat UI component with message display and form handling
- Testing: Complete unit and component test coverage
- Tool-calling: real, via `search_knowledge_base` against pgvector (mocked only at the LLM boundary in unit tests)

**Phase 2b Complete ✓**: Real LLM Integration
- Config infrastructure: LLM/embedding provider switch (fake/llama-cpp/openai-compatible) via environment variables, with runtime DB overrides through the Settings UI (`SystemSettings`, admin-only via `require_admin`/realm-role RBAC)
- Real LLM (llama-server via `ChatOpenAI`) and real embeddings (nomic-embed, 768-dim) wired end-to-end
- Real pgvector cosine-similarity search backing `search_knowledge_base`
- Streaming: deferred (tool-calling + streaming has known rough edges in llama.cpp)

**Phase 3 Complete ✓**: MCP Server Integration (doc-search)
- `search_knowledge_base` moved out of the backend process into a standalone MCP server (`mcp-servers/doc-search`), reached over **Streamable HTTP** (not stdio — a hard constraint since MCP servers run as separate K8s pods, not co-located subprocesses).
- Isolation across the process boundary: the backend forwards the caller's own, already-validated Keycloak access token (`get_current_user`'s `access_token` field) as a `Bearer` header on every call; doc-search independently verifies it against Keycloak's JWKS (`mcp-servers/doc-search/app/auth.py`, a small duplicate of `app.core.auth`'s verification logic, not a shared package) and derives `user_id` from the verified `sub` claim itself. doc-search never trusts a bare `user_id` supplied by the backend — this is the security-relevant design decision the phase's plan called for.
- `backend/app/mcp_client/doc_search_client.py` replaces the old in-process, closure-bound tool (`app/agents/tools.py`, deleted) with one that calls doc-search over Streamable HTTP via the official `mcp` client SDK; `create_chat_agent` now takes `token`/`mcp_url` instead of building the tool from `db`/`user_id` directly.
- Scope expansion (decided mid-implementation, not deferred): `generate_embedding` now returns `EmbeddingResult(vector, provider, model)` instead of a bare vector, and every write site tags `Embedding.embed_metadata` with that provenance — closing a pre-existing gap where a runtime embedding-provider switch (via the Settings screen) could silently mix incompatible vectors in the same knowledge base with no way to detect it. doc-search resolves the same DB-backed provider override the backend does, so an admin's change is honored identically by indexing and querying.
- Dependency fallout: adding the `mcp` SDK forced `fastapi` (0.104.1 → 0.108.0, minimum version dropping a direct `anyio<4.0` pin), `uvicorn`, and `python-multipart` version bumps; full backend suite re-verified green after each.
- Out of scope (deferred): TLS between backend and doc-search (Phase 5, same as all other service-to-service traffic per `docs/SECURITY.md`), full Helm chart packaging for doc-search (Phase 5 — `infra/k3s/doc-search-deployment.yaml` is a minimal direct manifest, not a chart), streaming through the MCP boundary, and additional MCP tools beyond `search_knowledge_base`.

**Phase 4a Complete ✓**: Conversation Persistence & Session Isolation
- Backend: LangGraph state persists to Postgres via `SqlAlchemyCheckpointSaver`, a custom `BaseCheckpointSaver` over two Alembic-owned tables (`conversation_threads`, `conversation_checkpoints`) — not `langgraph-checkpoint-postgres`, to keep a single DB driver, Alembic as sole schema authority, and fast SQLite-backed unit tests. Stores only the latest checkpoint per thread (conversation resume, not time-travel/replay).
- Isolation: `(user_id, thread_id)` ownership is enforced structurally by `ThreadRepository`, never by a checkpointer or per-endpoint filter. A client-supplied `thread_id` not owned by the caller is silently replaced with a fresh thread on `POST /api/agents/chat`; the new `GET /api/agents/threads` and `GET /api/agents/threads/{thread_id}` endpoints return 404 (never 403) for threads that don't exist or aren't the caller's.
- Frontend: `ChatWindow` restores the user's most recently updated thread on mount and lets them switch or start a new conversation, via a proper client → service → hook layer (`threadsClient` → `ThreadsService` → `useThreadsService`).
- Out of scope (deferred): retention/TTL enforcement (`session_ttl_hours`, `session_cleanup_on_logout` in `config.py` exist but aren't enforced yet).
**Phase 4b Complete ✓**: Data Retention Policy & Admin Configuration
- Every persisted store has a documented, tested retention timeline — see the policy table in `docs/SECURITY.md`. Windows are nullable DB overrides over env defaults, resolved per-call by `retention_service.resolve_retention_config` (same `is not None` semantics as `system_settings_service`, since `0` = "purge immediately" and `None` = "keep forever" are both meaningful).
- Enforcement: a K8s CronJob (`infra/k3s/retention-cronjob.yaml`) running `python -m app.cli.retention_sweep`, deliberately **not** an in-process scheduler — that would double-run across replicas without a distributed lock. Logout-triggered cleanup runs via `POST /api/auth/logout`, scoped to the caller's own `user_id` from the validated token.
- Audit: `AuditLog` is the first audit record in the system, append-only. Exemption from purges is structural, not conventional — `AuditLogRepository` has no delete/update method (asserted by a test on its public surface) and no purge path queries the table. Retention changes record actor, timestamp, field, and old→new values.
- Safety: the Settings UI requires explicit confirmation before applying a *shortened* window, naming each affected store and its old→new value. Purges are batched (500/round-trip), never one unbounded DELETE.
- Time is injected (`now: datetime`) throughout the retention service, so time-dependent logic is deterministic under test without patching `datetime`.

**Phase 4c Complete ✓**: Configurable Guardrail Thresholds & Heuristics (issue #16)
- `MAX_INPUT_LENGTH`, and both guardrails' on/off state, are now admin-configurable — same env-default + nullable-DB-override pattern as retention/LLM provider config, resolved per-call by `app.services.guardrail_config_service.resolve_guardrail_config`. `max_input_length` is bounded by a hard, non-overridable ceiling (`input_guardrail.MAX_INPUT_LENGTH_CEILING`, 8000), enforced at the API request-schema boundary, not just documented.
- Independent kill switches, not one combined switch: `guardrails_input_enabled`/`guardrails_output_enabled` — the two guardrails have different trip behavior (reject vs. sanitize) and risk profiles, and a fork may want to disable one without the other.
- Prompt-injection patterns are now individually toggleable (`GuardrailPattern` table, `GuardrailPatternRepository`): built-in patterns keep their regex in code and expose only an `enabled` bit (a toggle can never smuggle in arbitrary regex); admin-added custom patterns are literal case-insensitive substring matches only, never regex — a deliberate scope decision to avoid a ReDoS surface, not an oversight. Full custom-regex support is deferred to a follow-up issue.
- Every config change (scalar settings and pattern add/toggle/delete alike) is audit-logged (`"guardrail.config_update"`, `"guardrail.pattern_update"`), following the same before/after-diff pattern as `"retention.update"`.
- See `docs/SECURITY.md`'s "Guardrails & Compliance" section for the full design rationale and the admin-configurable-fields table.

**Phase 4d Complete ✓**: Chat Response Source Citations (issue #19)
- Which knowledge-base document(s) grounded a chat answer is now structured data the user can see, not just prose the LLM may or may not repeat. Plumbed end-to-end: doc-search's `search_knowledge_base_with_sources` (`mcp-servers/doc-search/app/search.py`) returns the same rendered text alongside each match's `SourceMatch` (knowledge_base_id/title/heading_path); the FastMCP tool (`app/server.py`) returns a hand-built `CallToolResult` carrying that as `structuredContent`, leaving the LLM-facing text block byte-identical to before.
- The backend's MCP client (`app/mcp_client/doc_search_client.py`) reads `structuredContent` and returns `(text, sources)` via LangChain's `response_format="content_and_artifact"`, so `ToolMessage.artifact` carries structured `Source` objects through LangGraph state with no new `ChatState` field needed. `app.agents.chat_agent.extract_sources_from_messages` collects and dedupes them (by `knowledge_base_id`) from a turn's message list after the graph finishes.
- `ChatResponse.sources` (new field, additive) is populated by `POST /api/agents/chat`; `ChatWindow` renders a "Sources: ..." line under a grounded agent reply. Scoped to the live turn only — thread history replay (`GET /api/agents/threads/{id}`) does not (yet) reconstruct past turns' sources, since `_render_messages` already discards tool messages when replaying.
- Verified end-to-end against a real llama-server + embedding-server + doc-search stack (`docker-compose up --profile llm`), extending `knowledge-base-search-grounding.spec.ts` — same `requires-profile-llm` exclusion from CI as the rest of that spec, since the fake LLM provider never emits a tool call at all.

**Phase 4e Complete ✓**: LLM Observability — Base Tracing (issue #4)
- Self-hosted Arize Phoenix (`arizephoenix/phoenix`, prebuilt upstream image, no Dockerfile of our own — same pattern as postgres/minio/keycloak) traces every chat agent run: LangGraph run → LLM call(s) → tool call(s), with latency, token counts, and the exact prompt/response content per span. Instrumentation is `arize-phoenix-otel` + `openinference-instrumentation-langchain`, which auto-instruments LangChain's callback machinery — LangGraph runs through it since a compiled graph is itself a `Runnable`, so `app.agents.chat_agent` needed zero code changes.
- Verified by hand, not assumed: node names in the captured trace tree are legible (`call_agent`, `call_tool`, the tool's own name), not generic `RunnableSequence` spans; the default `SimpleSpanProcessor` measurably blocked the request path for several seconds per span when Phoenix was unreachable, so `app.core.tracing.configure_tracing` explicitly uses `batch=True` (`BatchSpanProcessor`) instead — confirmed span creation drops to sub-millisecond even with Phoenix down. See `docs/OBSERVABILITY.md` for the full write-up including this verification.
- Config-gated (`tracing_enabled`, default `False`) and registered once at process start (`app.main`'s lifespan hook), never at import time of any agent/LLM module — unit tests using `FakeChatModel` never construct a real OTel exporter. Unlike the initial cut of this slice, `tracing_enabled` **is** a DB-backed admin override now (`app.services.tracing_config_service`, same nullable-override-over-env-default pattern as `llm_provider`, visible/auditable in the Settings UI) — but it is resolved once, at startup, not per-request like `llm_provider`, since there's no supported way to re-instrument a running process's OTel tracer provider. A change via the Settings UI therefore requires a backend restart to take effect, which the UI states explicitly. A related fix landed alongside this: a blank bool env var (e.g. `TRACING_ENABLED=` left empty) used to crash `Settings()` construction outright; it now falls back to the field's default, the same as an unset var.
- Trace storage is Phoenix's own SQLite on a dedicated volume, not the shared `eaistack` Postgres — this repo's Postgres has no multi-database provisioning mechanism, and Phoenix's trace schema isn't part of Alembic's owned application schema.
- Scope was deliberately narrowed from the original issue text (tracing + prompt inspection + trace search/clustering + eval hooks) into this base-tracing slice plus four tracked follow-ups: [#29](../../../issues/29) (trace clustering/search), [#30](../../../issues/30) (evaluation hooks — needs its own judge-model config design), [#31](../../../issues/31) (cost-per-span — no cost model exists yet for the default self-hosted llama.cpp path), and [#32](../../../issues/32) (trace retention — caught during planning: traces carry the same sensitive prompt/response content as `conversation_threads` but currently accumulate indefinitely, since Phoenix's store is outside the `eaistack` database this repo's retention sweep can purge directly; #32 is prioritized to land immediately after this slice).
- Out of scope (deferred): TLS termination on the Phoenix Helm chart ([#33](../../../issues/33) — an unmodified upstream image, unlike every other chart, which terminates TLS itself), everything covered by #29/#30/#31/#32 above.

**Phase 4f Complete ✓**: Rate Limiting for Chat and Auth Endpoints (issue #25)
- `POST /api/agents/chat` (per-`user_id`, from the validated JWT) and `POST /api/auth/token` (per-client-IP, since no JWT exists yet at that endpoint) now reject excess requests with `429` + a `Retry-After` header, via a pure token-bucket algorithm (`backend/app/ratelimit/token_bucket.py`) wrapped by `app.services.rate_limiter_service`. Resource-exhaustion/availability protection, distinct from the guardrails (#16), which validate content, not volume. Cheap, already-auth-gated reads (`GET /api/agents/threads*`) are deliberately not limited — no blanket global budget.
- Admin-configurable (`rate_limit_enabled`, per-route capacity/refill-rate), same env-default + nullable-DB-override pattern as retention/guardrails/tracing, resolved fresh per call by `app.services.rate_limit_config_service`, audited on change (`"rate_limit.config_update"`) — see `docs/SECURITY.md`'s new "Rate Limiting" subsection for the full config table.
- Mechanism decision made and documented explicitly, mirroring the retention CronJob's replica-correctness write-up but reaching the opposite conclusion for the opposite reason: state is an in-process `dict` (not Redis), justified by every shipped deployment path running the backend at `replicas: 1` today (`infra/helm/charts/backend/values.yaml`, asserted by `infra/tests/test_helm_charts.py`). Unlike the CronJob (where in-process state would cause destructive double-execution across replicas), an under-throttled limiter on a future multi-replica deployment degrades gracefully — weaker protection, not data loss — so this is judged an acceptable v1 trade-off, not a blocker. Tracked as [#38](../../../issues/38) for when a fork actually scales past one replica.
- A rate-limit trip is deliberately **not** audit-logged (only admin config *changes* are) — a high-frequency operational signal is a poor fit for `audit_logs`' append-only, never-purged, individually-compliance-relevant-event framing that guardrail rejections use.
- Hardened post-implementation (code review of the original PR): capacity/refill env vars are bounded (`Field(ge=1)` in `app/core/config.py`, matching the admin-API schema's existing bound) so a misconfigured env var fails loudly at startup instead of crashing the first request that empties the affected bucket; `app.ratelimit.token_bucket.check_and_consume` itself also rejects a non-positive `capacity`/`refill_per_second` as a defense-in-depth contract check. `POST /api/auth/token`'s client-IP resolution now goes through `app.core.client_ip.resolve_client_ip`, which only trusts `X-Forwarded-For` when `settings.rate_limit_trusted_proxy_count` (env-only, default `0`) is explicitly set — behind this repo's own Phase 5 ingress deployment target, the un-proxied default would otherwise collapse every external caller onto one shared bucket. `chat()` and `exchange_token()` now resolve `SystemSettings` once and share it across the rate-limit and guardrail resolvers (mirroring `app/api/settings.py::_to_response`'s pattern) instead of each resolving its own row. The five near-identical `_resolve_field` copies across `system_settings_service`/`retention_service`/`guardrail_config_service`/`tracing_config_service`/`rate_limit_config_service` were consolidated into one generic `app.services.config_resolution.resolve_field`, per `system_settings_service._resolve_field`'s own self-predicted "generalize at a third resolver" threshold. In-process buckets are now evicted once idle long enough to have fully refilled, bounding memory growth from the unauthenticated auth endpoint's attacker-influenced IP-keyed buckets. See `docs/SECURITY.md`'s Rate Limiting section for the full write-up.
- Out of scope (deferred, filed as follow-ups): moving bucket state to a shared store for multi-replica correctness ([#38](../../../issues/38), see above). The Settings-screen UI for the 5 rate-limit fields ([#37](../../../issues/37)) was closed alongside the settings help-text slice below, not deferred.

**Settings Screen Help Text Complete ✓**: Admin-Configurable Field Guidance (issue #37 UI + discoverability)
- Every field on the Settings screen (20+ across LLM/embedding provider, retention, guardrails, observability, rate limiting) now has a hover/keyboard-focus (i) tooltip explaining what it does, in plain terms — not just its name. `frontend/src/components/ui/info-tooltip.tsx` wraps `@radix-ui/react-tooltip` (newly vendored, following the same pattern as the other Radix primitives already in `package.json`); every trigger shares one generic accessible name ("Show help") and is rendered as a sibling of its field's `<label>`, not nested inside it — nesting an interactive element inside a `<label>` makes assistive tech (and `getByLabelText`-style test queries) treat it as part of that label's accessible name, which broke ambiguously once a field-specific tooltip name overlapped a substring of its own label text.
- Closed issue #37 in the same change: the Settings screen previously hand-rendered every other admin-configurable field except the 5 rate-limiting ones added by #25 (`rate_limit_enabled`, `rate_limit_chat_capacity`, `rate_limit_chat_refill_per_minute`, `rate_limit_auth_capacity`, `rate_limit_auth_refill_per_minute`) — the backend already fully supported them via `GET`/`PUT /api/settings`, but there was no UI. A new "Rate Limiting" section now renders all five, each with its own tooltip.
- A "Common setups" reference panel at the top of the page names three starting configurations (privacy-sensitive, general-purpose, exposed-to-untrusted-users) with their typical field values, for an admin who wants a starting point before reading every individual tooltip.
- Presentation-only: no new API surface, no new persisted field, no change to validation. See `docs/SECURITY.md`'s "Settings Screen Help Text" section for the accessible-naming rationale in full.

**Admin Audit Log Viewer Complete ✓**: In-Product Audit Trail (issue #45)
- `GET /api/settings/audit` (fully implemented since Phase 4b/4c, backed by `AuditLogRepository.list_recent()`) previously had no consumer — the only way to read `audit_logs` was direct database access, despite Settings.tsx telling admins "This change will be recorded in the audit log." A new admin-only "Audit Log" screen (`frontend/src/components/AuditLog.tsx`) closes that gap: a read-only table of every entry (timestamp, actor, action, field, old→new value), newest first, reachable from the main nav next to Settings.
- Followed the existing three-layer pattern exactly: `settingsClient.getAuditLog` → `SettingsService.getAuditLog` → `useSettingsService`'s `getAuditLog` (a `useApiCall`, mirroring `get`'s `immediate: false` + auth-loading-gated `useEffect` pattern) → `AuditLog.tsx`. No new backend endpoint or schema was needed — the read path was already complete.
- New admin-configurable flag, `audit_log_ui_enabled` (env-default `True` — transparent by default), same nullable-DB-override pattern as `tracing_enabled`/`guardrails_input_enabled`, resolved per-request (unlike `tracing_enabled`, hiding/showing a nav entry has no restart constraint) via `backend/app/services/audit_log_ui_config_service.py`. Lets a fork that routes audit consumption through an external SIEM hide the in-app view; changing the flag is itself audit-logged (`audit_log_ui.config_update`), same as every other admin-configurable switch.
- Verified end-to-end against the real stack (`docker-compose up --profile llm`): `frontend/tests/e2e/audit-log.spec.ts` logs in as the seeded admin, confirms the nav entry is visible, makes a real guardrail-config change, and confirms the resulting `guardrail.config_update` entry appears on the Audit Log screen — no fake-provider exclusion needed, since this flow never touches the LLM.
- While in `docs/AUDIT_EVENTS.md`'s "Events recorded today" table: fixed a pre-existing staleness gap found during this work (the table only listed `retention.update`, though `guardrail.config_update`/`guardrail.pattern_update`/`guardrail.input_rejected`/`guardrail.output_redacted`/`tracing.config_update`/`rate_limit.config_update` had all shipped since) — now lists all seven actions including this issue's new one.

**Output Guardrail Redaction Indicator Complete ✓**: User-Visible Signal (issue #46)
- A safety-relevant blind spot closed: when the output guardrail redacts part of an agent response (a system-prompt leak or credential-shaped string), the user previously saw an ordinary-looking reply with no way to tell "the model didn't know this" from "the system removed something the model said." `ChatResponse.was_modified` (new field, additive) now carries `OutputGuardrailResult.was_modified` — a value `filter_output`/`filter_agent_response` already computed but `POST /api/agents/chat` previously discarded — through to the frontend.
- `ChatWindow.tsx` renders a small, factual note ("Part of this response was filtered by a content safety rule.") on the specific message that was altered, mirroring the existing "Sources: ..." inline-note pattern rather than a global banner. The redacted content itself is never exposed — only the fact that a redaction happened. On by default with no config to disable it, unlike the admin dashboard/audit-log UI: a guardrail's action should never be silently indistinguishable from the model simply not knowing something.
- Found and fixed a pre-existing, more severe bug while implementing this: LangGraph's checkpointer persists the agent's *raw, pre-filter* response during `ainvoke()` — `filter_agent_response`'s redaction, which runs after `ainvoke()` returns, was never written back into graph state, so `GET /api/agents/threads/{thread_id}` was returning the original unredacted text on every replay, completely bypassing the output guardrail the moment a user reopened a thread. `_render_messages` now re-runs the pure `filter_output` (not `filter_agent_response`, which would additionally write a spurious fresh audit entry on every read) against every stored AI message, honoring the same `guardrail_config.output_enabled` toggle the live path uses.
- The `was_modified` *badge* itself is still scoped to the live turn only (same limitation as issue #19's source citations, since `ThreadMessage` carries no per-message flag) — but unlike the badge, the redaction itself is no longer lost on replay.
- `ChatResponse.was_modified` has no default (Pydantic requires every construction site to set it explicitly) rather than defaulting to `False` — a future call site that forgets to set it should fail loudly, not silently manufacture a false "not redacted" signal, which would be exactly the blind spot this issue exists to close.
- Verified end-to-end against a real llama-server stack (`docker-compose up --profile llm`): `frontend/tests/e2e/output-guardrail-redaction-indicator.spec.ts` asks the real model to disclose its system prompt and confirms the resulting redaction shows the indicator — marked `requires-profile-llm` and excluded from CI's fake-provider run (`ChatWindow.test.tsx`'s mocked `wasModified: true` covers the UI logic itself under CI). `tools/check_e2e_ci_coverage.py` was made regex-aware (it previously did a plain substring check against `ci.yml`'s `--grep-invert` value, which is documented as a full regular expression) so a single alternation pattern can correctly exclude multiple real-content specs by title.
**EAI Dashboard Complete ✓**: Consolidated Admin Status View (issue #48)
- A new admin-only "Dashboard" screen (`frontend/src/components/Dashboard.tsx`, `GET /api/settings/dashboard`) gives an admin one place to see rate-limit bucket state, guardrail trip counts, and tracing status, instead of several scattered or database-only signals. Every tile is backed by a real data path — no mocked/placeholder tiles.
- **Rate limiting**: `app.services.rate_limiter_service.bucket_count()` (the module's existing introspection hook, previously unused by any caller) plus the resolved on/off state. Deliberately no "recent 429 count": rate-limit trips are not audit-logged (Phase 4f's documented rationale), so no real data source exists for that figure — showing one would mean fabricating it, which the tile avoids rather than compromises on.
- **Guardrails**: `guardrail.input_rejected` trip counts over a rolling 24-hour window, grouped by pattern, via a new `AuditLogRepository.count_by_action_and_value_since` method (not client-side aggregation over `list_recent()`'s top 100 rows, which could silently undercount once other audit-event types are mixed in). `guardrail.output_redacted` is shown as a bare count only — no per-pattern breakdown exists, since the redacted content itself must never be audit-logged.
- **Tracing**: shows both the DB-desired state (`resolve_tracing_config`) and whether tracing is *actually* instrumented in this running process (`app.core.tracing.is_tracing_configured()`, a new public accessor over the module's existing `_configured` guard) side by side, since the two can diverge — a settings change only takes effect after the next backend restart. Links out to the Phoenix UI via a new `tracing_ui_url` env var (default `http://localhost:6006`), deliberately separate from the backend-internal `tracing_otlp_endpoint` (`http://phoenix:6006/...`, not resolvable from an admin's browser outside the docker-compose network).
- **Recent activity**: reuses issue #45's `useSettingsService().getAuditLog` rather than re-serving the same rows under a new shape, with a "View full audit log" link through to the full Audit Log screen.
- Admin-gated the same way Settings and Audit Log are; no disable toggle, unlike Audit Log's `audit_log_ui_enabled` — this is inherently an admin-only operational tool, so hiding it from admins would only recreate the gap it exists to close.
- Verified end-to-end against the real stack: `frontend/tests/e2e/dashboard.spec.ts` confirms all four tiles render, triggers a real guardrail rejection and confirms the Guardrails tile reflects the real trip count and pattern name, and confirms "View full audit log" navigates to the Audit Log screen.

## Common Development Commands

### Backend (Python)

```bash
# Setup
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Development
uvicorn app.main:app --reload  # Runs on http://localhost:8000

# Testing
pytest tests/unit/ -v                 # Unit tests only (mocked, fast)
pytest tests/unit/test_auth.py -v     # Single test file
pytest tests/unit/ -k "test_name" -v  # Single test function
pytest --cov                          # Full coverage report
pytest tests/integration/              # Integration tests (real services, slow)

# Linting & formatting
ruff check . && black --check .  # Check
black .                          # Auto-format
ruff check . --fix               # Auto-fix linting

# Type checking
mypy app/
```

### Frontend (Node.js)

```bash
# Setup
cd frontend
npm install

# Development
npm run dev  # Runs on http://localhost:3000

# Testing
npm test                 # Run all tests
npm run test:ui         # Run with interactive UI
npm test -- filename.test.ts  # Single test file

# End-to-end tests (requires the real stack: docker-compose up)
npx playwright test tests/e2e/          # Full e2e suite, real Keycloak login + backend
npx playwright test tests/e2e/foo.spec.ts  # Single e2e spec

# Linting & building
npm run lint            # Check
npm run build           # Production build
```

### Database Migrations (Alembic)

```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "Description of change"

# Rollback one migration
alembic downgrade -1

# View current migration version
alembic current

# View migration history
alembic history --verbose
```

### Full Stack (Docker Compose)

```bash
# Start all services (postgres, keycloak, minio, backend, frontend)
docker-compose up

# With LLM service (requires model in ./models/)
docker-compose up --profile llm

# Stop and clean
docker-compose down
docker-compose down -v  # Also remove volumes
```

## Development Standards

@AGENTS.md

## Helpful Context

- **10-year lifecycle**: This software is built to last a decade. Code clarity, comprehensive tests, and good design are investments, not costs.
- **Greenfield project**: No legacy code to preserve. Decisions made early shape the codebase for years.
- **User familiarity**: The user is less familiar with Kubernetes; infrastructure docs should assume minimal prior K8s knowledge.
- **Hard requirements**: Encryption and session/context lifecycle are non-negotiable (not bolt-on later). Security and session isolation are baked in from Phase 1.
- **No Bitnami charts**: Official upstream images only (pgvector/pgvector, keycloak, minio). Deprecated free tier is off-limits.
- **MCP transport**: Must be Streamable HTTP (not stdio) for service-to-service K8s deployment. Implemented in Phase 3 (doc-search).

## Architecture Overview

### Backend (FastAPI + LangGraph)

**Directory structure**:
```
backend/
  app/
    core/           config.py (settings), auth.py (JWT validation), llm_client.py
    api/            REST endpoints
    agents/         LangGraph graph definitions (Phase 2+)
    db/             SQLAlchemy models, LangGraph checkpointer (session isolation)
    guardrails/     Input/output validation middleware
    prompts/        Prompt library (Phase 4+)
    mcp_client/     MCP server integration (doc-search MCP client, Phase 3)
    storage/        MinIO client wrapper
    main.py         FastAPI app definition
  tests/
    unit/           Fast, mocked tests (gates CI)
    integration/    Real services, slow, non-gating
```

**Key patterns**:
- **LLM isolation**: All LLM calls → `app.core.llm_client`. Unit tests mock this boundary with `FakeChatModel`.
- **Agent state**: LangGraph checkpoints live in Postgres, keyed by `(user_id, thread_id)`. Prevents context bleeding between concurrent sessions.
- **Auth**: `get_current_user` dependency (from `app.core.auth`) protects endpoints. Uses JWT from Keycloak JWKS.

### Frontend (React + TypeScript + Vite)

**Directory structure**:
```
frontend/
  src/
    context/        AuthContext.tsx (Keycloak setup, login/logout)
    api/            API clients (HTTP-only, take token as param)
    services/       Service layer (business logic, wrap clients)
    hooks/          Custom hooks (useApiCall, useApiMutation, service-specific)
    components/     React components (use hooks for data/state)
    App.tsx         Entry point
  tests/            Vitest test files
  vitest.config.ts  Test configuration
```

**Key patterns**:
- **Auth**: AuthContext wraps app, handles Keycloak OIDC. Tests mock Keycloak provider.
- **Three-layer API architecture**: Components → Hooks → Services → API Clients → HTTP
  - API Clients (`src/api/`): HTTP-only, take token as param, no business logic
  - Services (`src/services/`): Business logic, wrap API clients, take token in constructor
  - Hooks (`src/hooks/`): State management, use generic hooks (useApiCall/useApiMutation) with services
  - Components: Use hooks only, no direct fetch() or API calls
- **Generic hooks** for reuse: `useApiCall<T>()` (GET), `useApiMutation<T, R>()` (POST/PUT/DELETE)
- **Service-specific hooks**: `useChatService()`, `useEmbeddingsService()` (see AGENTS.md for pattern)

### Other Layers

```
/mcp-servers         Custom MCP servers: doc-search (pgvector queries, Phase 3), etc.
/infra
  helm/              Kubernetes Helm charts (Phase 5+)
  k3s/               K3s deployment scripts
  keycloak/          realm-import.json (Keycloak config)
  tls/               TLS/cert-manager setup
/docs                ARCHITECTURE.md, AIRGAP_SETUP.md, SECURITY.md
/.github/workflows   CI pipelines (backend tests, frontend tests, infra validation)
```

### Data Flow

```
User (Browser)
  ↓
Frontend (React + AuthContext)
  ↓ [JWT in Authorization header]
Backend API (FastAPI + get_current_user)
  ↓
LangGraph Agent (state in Postgres checkpoint)
  ↓
LLM Service (llama-server, mocked in unit tests)
  ↓
MCP Tools: pgvector search (doc-search, Phase 3), MinIO retrieval (planned)
  ↓
Response → Frontend
```

## Constraints & Gotchas

- **No Bitnami charts**: Official upstream images only (pgvector/pgvector, keycloak, minio)
- **llama.cpp tool-calling**: Streaming + tool_calls has known rough edges. Test this combo early (Phase 2).
- **Keycloak secrets**: Currently hardcoded in `app/core/config.py`; move to K8s secrets before production (Phase 5).
- **LLM model vendoring**: All models must be downloaded during air-gap setup; no internet at runtime.
- **MCP transport**: Must be Streamable HTTP (not stdio) for K8s pod-to-pod communication. Implemented in Phase 3 for doc-search; future MCP servers must follow the same pattern.
- **Session cleanup**: Configurable per deployment: logout-triggered OR TTL-based (or both). Implemented in Phase 4b; the TTL sweep needs its CronJob scheduled (or the module run manually under docker-compose) or nothing purges automatically.
