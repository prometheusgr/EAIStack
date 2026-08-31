# Technology Stack

A layer-by-layer reference for engineers who need to understand what EAIStack is built from, how the pieces fit together, and — for each technology — what's actually implemented today versus still open. For *why* key decisions were made, see [ARCHITECTURE.md](ARCHITECTURE.md) and [SECURITY.md](SECURITY.md). For the phase-by-phase build history, see [CLAUDE.md](../CLAUDE.md#current-status).

Status legend: ✅ done and tested · 🚧 partial / deferred · ❌ not started

## At a glance

```
User (browser)
  → Frontend: React + TypeScript (Vite)             — OIDC login via Keycloak
    → Backend: FastAPI                              — JWT validation
      → LangGraph agent                             — conversation state checkpointed in Postgres
        → llama-server (chat model)                 — local LLM inference, OpenAI-compatible API
        → llama-server (embedding model)             — separate instance/port, nomic-embed
        → doc-search (MCP, Streamable HTTP)          — pgvector similarity search, own JWT verification
      → Guardrails                                   — input/output validation
    → Response → Frontend
```

Everything below the browser runs inside the cluster; nothing calls out to a third-party API at runtime.

---

## Frontend

**Location:** `frontend/`

| Concern | Technology | Status |
|---|---|---|
| Framework | React 18.2, TypeScript 5.2 | ✅ |
| Build tool | Vite 5.4 (`tsc -b && vite build`) | ✅ |
| Styling | Tailwind CSS 3.4 + Radix UI primitives (dialog, select, scroll-area, form, label) + `class-variance-authority` + `lucide-react` icons | ✅ |
| Data/forms | `@tanstack/react-query`, `@tanstack/react-table`, `react-hook-form` + `zod` schemas | ✅ |
| HTTP | Hand-rolled `authorizedFetch` wrapper (`src/api/authorizedFetch.ts`) around native `fetch`, with a typed `ApiErrorImpl` | ✅ |
| Routing | None — single-view SPA | — (by design, no multi-page navigation needed yet) |
| Unit/component tests | Vitest 1.0 + React Testing Library + jsdom | ✅ |
| E2E tests | Playwright 1.62, single Chromium project, sequential workers | ✅ (5 specs; **not run in CI**, local-only against `docker-compose up`) |

**Architecture** — strict three-layer pattern (`docs/FRONTEND_ARCHITECTURE.md` is canonical):

```
src/
  api/         HTTP-only clients, one per resource (agentsClient, threadsClient, settingsClient, ...)
  services/    Business logic, wrap clients, take token in constructor
  hooks/       useApiCall / useApiMutation (generic) + service-specific hooks
  components/  Use hooks only, never call fetch() directly
  context/     AuthContext (Keycloak OIDC)
  auth/, lib/, types/
```

Components never call `services/` or `api/` directly — only through a hook. This is enforced by convention and code review, not a linter.

**Known gap:** `axios` is declared in `package.json` but has zero imports anywhere in `src/` or `tests/` — a vestigial dependency left over from before `authorizedFetch` existed. Safe to remove; not yet cleaned up.

## Backend

**Location:** `backend/`

| Concern | Technology | Status |
|---|---|---|
| Web framework | FastAPI 0.108.0, `uvicorn[standard]` | ✅ |
| Validation | Pydantic 2.7+, `pydantic-settings` | ✅ |
| ORM / migrations | SQLAlchemy 2.0.23, Alembic 1.13.0, `psycopg2-binary` | ✅ |
| Agent orchestration | LangGraph 1.0+, `langchain-core`, `langchain-openai` (chat model client) | ✅ |
| Vector search | `pgvector` 0.2.4 (Python bindings) | ✅ |
| Object storage client | `minio` 7.2.0 | ✅ |
| Auth / JWT | `pyjwt` 2.13.0 (the library actually used) — `python-jose` is also a declared dependency but unused in `auth.py` | ✅ (jose dep is dead weight, same category of issue as frontend's axios) |
| MCP client | `mcp` SDK 1.29.0 | ✅ |
| Document parsing | `pypdf`, `python-docx` | ✅ |
| Testing | pytest, `pytest-asyncio`, `pytest-mock`, `testcontainers[postgres]` | ✅ |
| Lint / format / types | `ruff`, `black`, `mypy` (not strict — `disallow_untyped_defs = false`), `pylint` | ✅ |

**Directory map** (`backend/app/`):

| Directory | Purpose |
|---|---|
| `api/` | FastAPI routers — `agents`, `apikeys`, `auth`, `embeddings`, `knowledge_base`, `settings` |
| `agents/` | LangGraph chat agent + `checkpointer.py` (custom Postgres-backed `BaseCheckpointSaver`) |
| `core/` | `config.py` (Settings), `auth.py` (JWT/Keycloak), `llm_client.py`, `security.py`, `tls.py` |
| `db/` | SQLAlchemy models, session/engine setup |
| `repositories/` | One repository per table — see [REPOSITORY_PATTERN.md](REPOSITORY_PATTERN.md) |
| `services/` | Business logic used by 2+ endpoints — see [BACKEND_SERVICES.md](BACKEND_SERVICES.md) |
| `guardrails/` | Input/output validation middleware |
| `mcp_client/` | Client calling the doc-search MCP server over Streamable HTTP |
| `storage/` | MinIO client, document text extraction, object-key scheme |
| `prompts/` | Prompt templates for the chat agent |
| `cli/` | `retention_sweep.py` — the retention CronJob's entry point |

**Custom static-analysis gates** (`backend/tools/`, run in CI on every PR, not just style checks):

- `lint_time_injection.py` — flags functions calling `datetime.now()` without accepting `now:` as a parameter (see [TIME_INJECTION.md](TIME_INJECTION.md)).
- `lint_edge_case_truthiness.py` — flags `if x:` on nullable int fields where `None`/`0`/positive are all distinct, meaningful states (retention windows).
- `lint_repositories.py` — flags `update`/`delete`/`remove`/`purge` methods on any `*Repository` class named `*Audit*` or `*Log*`, enforcing append-only stores structurally.

**Known gaps:**
- Chat streaming is deferred — `agents.py`'s endpoint docstring states this explicitly; llama.cpp's tool-calling + streaming combination has known rough edges.
- `storage/minio_client.py` has an open TODO: local docker-compose MinIO is still plaintext HTTP, unlike the TLS-hardened Helm/production path ([#17](../../../issues/17)).
- The custom LangGraph checkpointer stores only the latest checkpoint per thread by design (conversation resume, not time-travel/replay); `put_writes` is a documented no-op and `filter`/`before`/`limit` raise `NotImplementedError`.

## Auth

**Location:** `infra/keycloak/realm-import.json` (dev-seed realm `eaistack`), `backend/app/core/auth.py`

| Concern | Technology | Status |
|---|---|---|
| Identity provider | Keycloak (OIDC) | ✅ |
| Realm config | `realm-import.json` — clients `eaistack-api` (backend, confidential) and `eaistack-web` (frontend, public), `admin` realm role, `audience-eaistack-api` client-scope mapper | ✅ |
| JWT validation | `pyjwt` + `PyJWK`, JWKS fetched from Keycloak and cached in-process (10-min TTL), retried once on unknown `kid` | ✅ |
| RBAC | `require_admin` dependency checks `realm_access.roles` for `"admin"` | ✅ |
| Session isolation | `(user_id, thread_id)` enforced structurally by `ThreadRepository` — no endpoint or checkpointer filters independently | ✅ |
| Frontend token handling | `localStorage` is authoritative (decoupled from Keycloak's session cookie); see [ARCHITECTURE.md](ARCHITECTURE.md#authentication--token-management) | ✅ |

**Known gap:** `config.py`'s `keycloak_client_secret` default is an explicitly-documented dev-only placeholder. Helm deployments require overriding it via a K8s Secret, but a bare local `uvicorn` run with no env var silently uses the placeholder — there's no "required in production" settings split yet to catch that at startup.

## Database

**Location:** `backend/app/db/models.py`, `backend/alembic/`

| Concern | Technology | Status |
|---|---|---|
| RDBMS | PostgreSQL (via `pgvector/pgvector:pg16` image — see [Constraints](#constraints--gotchas)) | ✅ |
| Vector search | `pgvector` extension, `Vector(768)` column on `Embedding` (dimension matches nomic-embed-text-v1.5) | ✅ |
| Migrations | Alembic, sole schema authority — 6 migrations applied to date | ✅ |

**Tables:** `api_keys`, `knowledge_base`, `embeddings`, `conversation_threads`, `conversation_checkpoints`, `audit_logs`, `system_settings`.

Alembic history: initial schema → embedding dimension fix (768) → system settings → conversation threads → retention & audit log → knowledge-base object storage.

## Object storage

**Location:** `backend/app/storage/`

| Concern | Technology | Status |
|---|---|---|
| Store | MinIO (S3-compatible, official upstream image — no Bitnami) | ✅ |
| Client | `minio` Python SDK, wrapped in `MinioClient` | ✅ |
| Flow | Upload → text extraction (`pypdf`/`python-docx`) → chunk → embed → pgvector row, all scoped per user | ✅ |
| Retention | Purge order fixed to delete DB rows before MinIO objects (avoids orphaned DB references to deleted objects) | ✅ |
| TLS | Production (Helm) uses cert-manager mTLS; local docker-compose is still plaintext | 🚧 ([#17](../../../issues/17)) |

## LLM inference & embeddings

**Location:** `backend/app/core/llm_client.py`, `backend/app/services/embedding_service.py`, `backend/app/core/config.py`

| Concern | Technology | Status |
|---|---|---|
| Local inference engine | `llama.cpp` (`llama-server`), OpenAI-compatible HTTP API | ✅ |
| Chat provider switch | `llm_provider`: `fake` \| `llama-cpp` \| `openai-compatible` — both real providers share code via `langchain_openai.ChatOpenAI` | ✅ |
| Embedding provider switch | `embedding_provider`: `fake` \| `llama-cpp` | ✅ |
| Embedding model | nomic-embed-text-v1.5 (Q4_K_M GGUF), 768-dim | ✅ |
| Config resolution | DB override (Settings UI, admin-only) wins over env default, resolved fresh per request — no caching | ✅ |
| Deployment topology | Chat and embedding models run as **separate** llama-server instances/ports/pods (different weights) | ✅ |
| Provenance tracking | Every `EmbeddingResult` records `provider`/`model` into `Embedding.embed_metadata`, so a runtime provider switch can't silently mix incompatible vectors in one knowledge base | ✅ |
| Streaming | Config flag (`enable_streaming`) exists but the chat endpoint is non-streaming | 🚧 (deferred — see Backend gaps above) |

**LLM boundary discipline:** every LLM call goes through `app.core.llm_client`. Unit tests mock only at this boundary (`FakeChatModel`) — never in business logic. This is a hard rule, not a convention (see [AGENTS.md](../AGENTS.md#key-constraints)).

## Tool integration (MCP)

**Location:** `mcp-servers/doc-search/`

| Concern | Technology | Status |
|---|---|---|
| Protocol | MCP over **Streamable HTTP** (not stdio — required for pod-to-pod K8s communication) | ✅ |
| SDK | `mcp` 1.29.0 (same version pinned in both backend and doc-search) | ✅ |
| Servers implemented | `doc-search` only — exposes `search_knowledge_base` | ✅ (only tool so far) |
| Auth model | Backend forwards the caller's own validated Keycloak access token as a `Bearer` header; doc-search independently re-verifies against Keycloak's JWKS and derives `user_id` from the verified `sub` claim — never trusts a bare `user_id` from the backend | ✅ |
| Deployment | Own Dockerfile, own Helm chart (`infra/helm/charts/doc-search/`), own k3s manifest | ✅ |

Adding a second MCP server (a second tool, or a different backing store) should follow this same shape — see [AGENT_LIBRARY.md](AGENT_LIBRARY.md) for the equivalent guidance on agents.

## Observability

**Location:** `backend/app/core/tracing.py`, docker-compose's `phoenix` service, `infra/helm/charts/phoenix/`

| Concern | Technology | Status |
|---|---|---|
| Tracing backend | Self-hosted Arize Phoenix (`arizephoenix/phoenix`, prebuilt upstream image, no Dockerfile of our own) | ✅ |
| Instrumentation | OpenTelemetry via `arize-phoenix-otel` + `openinference-instrumentation-langchain`, auto-instruments LangChain's callback machinery (which LangGraph runs through) | ✅ |
| What's captured | Full trace tree per chat turn (LangGraph run → LLM calls → tool calls), latency, token counts, and the exact prompt/response content | ✅ (verified by hand — see [docs/OBSERVABILITY.md](OBSERVABILITY.md)) |
| Config | `tracing_enabled` (default `false`) / `tracing_otlp_endpoint`, env-only — not a DB-backed admin override, since instrumentation registers once at process start | ✅ |
| Storage | Phoenix's own SQLite on a dedicated `phoenix_data` volume, not the shared `eaistack` Postgres (no multi-database provisioning in this repo, and it isn't part of Alembic's owned schema) | ✅ |
| Deployment | No Dockerfile (prebuilt image), Helm chart (`infra/helm/charts/phoenix/`), off by default in the umbrella chart | ✅ |

**Known gaps:** no retention policy for trace data yet ([#32](../../../issues/32) — traces carry the same sensitive prompt/response content as `conversation_threads` but currently accumulate indefinitely); no TLS termination on the Phoenix Helm chart yet ([#33](../../../issues/33) — an unmodified upstream image, unlike every other chart, which terminates TLS itself). Trace clustering/search ([#29](../../../issues/29)), evaluation hooks ([#30](../../../issues/30)), and cost-per-span ([#31](../../../issues/31)) are separate, unimplemented follow-ups. See [docs/OBSERVABILITY.md](OBSERVABILITY.md) for the full design writeup.

## Data retention & audit

**Location:** `backend/app/services/retention_service.py`, `backend/app/cli/retention_sweep.py`, `backend/app/repositories/audit_log_repository.py`

| Concern | Technology | Status |
|---|---|---|
| Retention config | Per-store nullable DB override over env default (`None` = keep forever, `0` = purge immediately) | ✅ |
| Enforcement | K8s CronJob running `python -m app.cli.retention_sweep` — deliberately not an in-process scheduler (would double-run across replicas without a distributed lock) | ✅ |
| Logout cleanup | `POST /api/auth/logout`, scoped to the caller's own `user_id` | ✅ |
| Audit trail | `AuditLog`, append-only — enforced structurally, not by convention (`AuditLogRepository` has no update/delete/purge method, checked by `lint_repositories.py` and a test asserting its public method set) | ✅ |
| Purge safety | Batched deletes (500/round-trip), never one unbounded `DELETE`; Settings UI requires explicit confirmation before *shortening* a retention window | ✅ |

## Infrastructure & deployment

**Location:** `infra/`

| Concern | Technology | Status |
|---|---|---|
| Target platform | K3s (production-grade, minimal-footprint K8s) | ✅ Helm charts validated in CI; 🚧 not yet proven on a live cluster ([#9](../../../issues/9)) |
| Package format | Helm — `eaistack-umbrella` parent chart + 8 subcharts (postgres, keycloak, minio, backend, doc-search, frontend, llama-server, embedding-server) | ✅ all charts have real templates, not stubs |
| TLS | cert-manager-issued mTLS between services (`certificate.yaml` in every chart), `sslmode=verify-full` to Postgres | ✅ in Helm/production path; 🚧 local docker-compose still plaintext ([#17](../../../issues/17)) |
| Secrets | K8s Secrets per chart (no plaintext in manifests) | ✅ |
| k3s raw manifests | `infra/k3s/` — only 2 files (`doc-search-deployment.yaml`, `retention-cronjob.yaml`); Helm is the primary deployment path, not raw manifests | 🚧 sparse by design |
| Air-gap image mirroring | `infra/scripts/bootstrap-airgap.sh` | ❌ explicit stub — defines an `IMAGES` list but doesn't build/pull/tarball anything yet, and the list is already missing `doc-search`/`embedding-server` ([#10](../../../issues/10)) |
| Manifest validation | `infra/scripts/validate-rendered-manifests.py`, tested and CI-gated | ✅ |
| Backup strategy | — | ❌ no backup path exists anywhere in the repo yet ([#12](../../../issues/12)) |

**No Bitnami charts anywhere** — official upstream images only (`pgvector/pgvector`, `keycloak`, `minio`). This is a hard constraint, not a preference (deprecated Bitnami free tier).

## CI/CD

**Location:** `.github/workflows/ci.yml` (the only workflow file — no separate CD/release/scheduled workflows)

| Job | What it gates |
|---|---|
| `backend-tests` | `pytest tests/unit/` (with coverage) against a real `pgvector/pgvector:pg16` service container, `ruff`, `black --check`, `mypy app/`, plus the three custom lint scripts. **`tests/integration/` does not run in CI** (needs Docker/testcontainers — local-only). |
| `doc-search-tests` | Same shape as backend, scoped to `mcp-servers/doc-search`. Integration tests likewise excluded from CI. |
| `frontend-tests` | `npm test` (Vitest, unit + integration, excludes e2e), `npm run lint`, `npm run build`. **Playwright e2e does not run in CI** — needs the full `docker-compose` stack including real Keycloak. |
| `infra-validation` | `helm lint` on every chart, `pytest infra/tests/` (rendered-manifest assertions). |

Practical implication for contributors: passing CI proves unit-level correctness and chart validity. It does **not** prove the real stack works together — that's what `frontend/tests/e2e/` is for, and it must be run manually against `docker-compose up` before merging any user-facing change (see [AGENTS.md](../AGENTS.md#end-to-end-e2e-tests)).

## Testing footprint (rough counts, August 2026)

| Suite | Location | Files | Gates CI? |
|---|---|---|---|
| Backend unit | `backend/tests/unit/` | ~40 | ✅ |
| Backend integration | `backend/tests/integration/` | ~8 | ❌ local-only |
| Frontend unit/component | `frontend/tests/unit/` + top-level | ~11 | ✅ |
| Frontend integration | `frontend/tests/integration/` | 2 | ✅ |
| Frontend e2e (Playwright) | `frontend/tests/e2e/` | 5 specs | ❌ local-only |
| Infra | `infra/tests/` | chart + manifest tests | ✅ |

## Where to go next

- New to the repo? Start with [ARCHITECTURE.md](ARCHITECTURE.md) for the *why* behind the choices above, then [CLAUDE.md](../CLAUDE.md) for phase history.
- Adding code in any layer? [AGENTS.md](../AGENTS.md#detailed-implementation-guides) has a mandatory canonical shape for each — don't improvise a new pattern.
- Deploying for real? [SECURITY.md](SECURITY.md) and [infra/k3s/README.md](../infra/k3s/README.md) before you touch a live cluster.
- Wondering what's next? The README's [Roadmap](../README.md#roadmap--whats-next) tracks open issues in priority order — several of the ❌/🚧 items above (`bootstrap-airgap.sh`, backup strategy, k3s TLS-by-default) are already tracked there.
