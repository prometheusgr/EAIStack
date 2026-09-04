# EAIStack Architecture

## Overview

EAIStack is a forkable template for building offline/air-gapped enterprise AI applications on Kubernetes.

**Core stack**:
- Frontend: React + TypeScript
- Backend: FastAPI + LangGraph
- Auth: Keycloak (OIDC)
- Storage: PostgreSQL + pgvector (structured data + embeddings)
- Object storage: MinIO (documents)
- LLM: llama.cpp (llama-server) for local inference
- MCP: Custom Streamable HTTP servers for tool integration
- Deployment: K3s (production-grade, minimal Kubernetes)

## Key Architecture Decisions

### Authentication & Token Management

**Frontend auth state** is decoupled from Keycloak's session cookie. `localStorage` is the authoritative source of truth:

```typescript
const tokenFromStorage = localStorage.getItem('access_token')
const appAuthenticated = !!tokenFromStorage || (kcAuthenticated && kc.token)
setIsAuthenticated(appAuthenticated)
```

**Why this matters**:
1. **Fresh instances show login**: Even if Keycloak has a cached session cookie, app requires explicit token in localStorage
2. **Logout is decisive**: Clearing localStorage immediately unauthenticates, independent of Keycloak session state
3. **Multiple users**: Each browser user has their own localStorage token
4. **Resilience**: If Keycloak session dies, app still works (token persists)

**Login flow** includes `prompt=login` in the OAuth2 authorization request to force Keycloak to show the login form and ignore existing session cookies:

```typescript
keycloakLoginUrl.searchParams.set('prompt', 'login')
```

**Token lifecycle**:
1. User clicks login → redirected to Keycloak with `prompt=login`
2. User enters credentials → Keycloak issues auth code
3. Frontend exchanges code for token via backend `/api/auth/token`
4. Token stored in localStorage + synced to keycloak.token instance
5. Chat requests include token in `Authorization: Bearer <token>` header
6. User logs out → localStorage cleared, app shows login page

See [docs/AUTH_TROUBLESHOOTING.md](./AUTH_TROUBLESHOOTING.md) for debugging logout and fresh-instance issues.

**User lifecycle (creating, disabling, deleting a user; granting the `admin` role) is entirely a Keycloak admin-console operation** — EAIStack's frontend has no in-app screen for it, only an admin-gated "User Management" nav entry that deep-links to Keycloak's own console. The full URL (realm and admin-console path included) is composed server-side by `backend/app/services/nav_config_service.py` from `keycloak_console_url`/`keycloak_realm` in `backend/app/core/config.py` and served by `GET /api/settings/nav-config`, so the realm name is resolved in one place rather than duplicated in the frontend. See [docs/USER_MANAGEMENT.md](./USER_MANAGEMENT.md) for the full walkthrough, including why no in-app editor was built and where Keycloak's own admin/login event history (enabled by default in this realm's config) lives.

---

### Fully Air-Gapped

No internet access at runtime. All dependencies (container images, Helm charts, models) are pre-fetched and mirrored into a private registry on the air-gapped network.

### LLM Isolation

The local LLM (llama-server) runs as its own Kubernetes pod with dedicated CPU/RAM allocation. The backend communicates via OpenAI-compatible HTTP API (`/v1/chat/completions`).

**Why**: Decouples model lifecycle from API service, simplifies GPU scheduling, allows model updates without redeploying the backend.

### Session & Context Isolation

Each conversation thread is a LangGraph "checkpoint" keyed by `(user_id, thread_id)` and stored in Postgres. This prevents context bleeding between concurrent sessions.

**Cleanup policy**: Configurable per-deployment:
- `SESSION_CLEANUP_ON_LOGOUT`: Purge checkpoint on Keycloak logout
- `SESSION_TTL_HOURS`: TTL-based cleanup for abandoned sessions (both can be enabled together)

### Tenancy Scope: Single-Organization, Not Multi-Tenant SaaS

Isolation in this template is **per-user, within a single organization**: every
row is scoped by `user_id` (derived from the validated Keycloak `sub` claim),
enforced structurally by `ThreadRepository`/`APIKeyRepository` and the doc-search
MCP boundary (see [docs/REPOSITORY_PATTERN.md](./REPOSITORY_PATTERN.md) and
[docs/SECURITY.md](./SECURITY.md)'s "MCP Server Isolation"). There is no
organization/tenant concept anywhere in the schema, auth flow, or Keycloak realm
config.

**The supported deployment pattern is one Keycloak realm + one EAIStack
deployment per organization** — separate Postgres, separate MinIO bucket,
separate K8s namespace (or cluster) per customer, exactly the isolation
boundary the rest of this document already assumes. This is correct for that
shape and shouldn't be casually extended: a single deployment serving multiple
customer organizations against a shared Postgres instance / knowledge base pool
is **out of scope** and not something this schema or auth flow defends against
today. A user's `user_id` uniquely identifies them only within one realm; two
different organizations' Keycloak realms could in principle mint tokens with
colliding `sub` values, and nothing in this codebase would tell them apart.

**Upgrade path for a fork that needs true multi-tenant SaaS isolation**
(same treatment as "No KMS in v1" above — a documented path, not built in, to
keep the template's complexity down for the common case):
1. Add a `tenant_id` column to every tenant-scoped table (`knowledge_base`,
   `embeddings`, `conversation_threads`, `api_keys`, `system_settings`, etc.)
   and thread it through every repository query alongside `user_id` — the same
   structural-enforcement pattern `docs/REPOSITORY_PATTERN.md` already uses for
   `user_id`, extended by one column.
2. Resolve `tenant_id` from the token, not a client-supplied parameter: either
   a claim in a shared Keycloak realm's tokens (e.g. a custom `tenant_id`
   claim mapped per user/group) or the realm itself if using one Keycloak
   realm per tenant against a shared backend deployment.
3. Add Postgres row-level security (RLS) policies keyed on `tenant_id` as a
   defense-in-depth backstop below the application layer, so a bug in a
   repository's `WHERE` clause can't leak another tenant's rows outright.
4. Extend doc-search's own token verification (see "MCP Server Isolation" in
   `docs/SECURITY.md`) to also check `tenant_id`, not just `user_id` — the same
   "never trust an identity claim handed to it by another service" principle
   applies to tenant identity, not just user identity.
5. Re-audit `docs/SECURITY.md`'s retention, audit-log, and rate-limiting
   sections: each currently reasons about isolation only at the `user_id`
   level and would need a `tenant_id` dimension added to their own scoping.

### MCP Transport

Custom MCP tool servers (e.g., document search) expose **Streamable HTTP** (stateless, K8s-native), not stdio (which assumes co-located processes). This allows MCP servers to scale horizontally and live in separate pods.

**Implemented in Phase 3** (`mcp-servers/doc-search`): `search_knowledge_base` runs as a standalone MCP server rather than in-process in the backend. The security-relevant design decision is how user isolation survives the process boundary: the backend forwards the caller's own, already-validated Keycloak access token (not a bare `user_id`) as a `Bearer` header on every call, and doc-search independently verifies that token against Keycloak's JWKS (a small, deliberately duplicated copy of `backend/app/core/auth.py`'s verification logic — these are separately deployed services, not two callers in one codebase) before deriving `user_id` from the verified `sub` claim. doc-search never trusts an identity claim handed to it by another service. See `mcp-servers/doc-search/README.md` for the full security model.

### Encryption Posture (Phase 5)

**In transit**: TLS everywhere. cert-manager with self-signed internal CA (no external ACME in air-gap).

**At rest**:
- Secrets: K3s native etcd encryption (`--secrets-encryption` flag)
- Volumes: Encrypted StorageClass (LUKS or host-provided mechanism)
- No separate KMS (e.g., Vault) in v1; documented upgrade path for forks with stricter compliance.

### No Bitnami Helm Charts

As of Aug 2025, Bitnami free tier moved to deprecated unmaintained images. Using instead:
- PostgreSQL: official `pgvector/pgvector` image
- Keycloak: Keycloak's official chart
- MinIO: MinIO's official chart

## Data Flow

```
User (browser)
  → Frontend (React) — OIDC login via Keycloak
    → Backend API (FastAPI) — JWT validation
      → LangGraph agent (state in Postgres checkpoint)
        ↓
        LLM (llama-server) ← Mocked in unit tests
        ↓
        MCP tool server (Streamable HTTP, separate pod — doc-search)
          → pgvector (document search)
          → MinIO (document retrieval, planned)
      → Response to frontend (streaming)
```

## Phases

1. **Phase 0**: Test & CI scaffolding
2. **Phase 1**: Local dev (docker-compose, all services running)
3. **Phase 2**: LangGraph + llama-server integration
4. **Phase 3**: MCP + pgvector doc search ✓ complete
5. **Phase 4**: Guardrails, prompt library, agent library scaffolding ✓ complete
6. **Phase 4a**: Session/context lifecycle (configurable cleanup) ✓ complete
7. **Phase 5**: Kubernetes + air-gap packaging + encryption

See `/.claude/plans/indexed-tinkering-babbage.md` for detailed phase breakdown.

## Known Inconsistencies

### Frontend data-fetching: React Query vs. custom hooks

`frontend/src/components/apikeys/APIKeys.tsx` (and `frontend/src/api/apiKeysClient.ts`) use `@tanstack/react-query` for data fetching and mutation state. Every other component uses the project's `useApiCall`/`useApiMutation` hooks (see [FRONTEND_ARCHITECTURE.md](./FRONTEND_ARCHITECTURE.md), "Frontend Custom Hooks for State & API Management"). This is the only place React Query is used in the codebase.

This has not been unified: it's an open decision whether to adopt React Query project-wide (replacing `useApiCall`/`useApiMutation`) or migrate `APIKeys.tsx` to the custom-hook pattern for consistency. Until decided, treat React Query as scoped to the API keys feature only — don't introduce it elsewhere.

## Testing Standards

- **Backend**: Mock LLM boundary; TDD all deterministic logic. Real LLM integration tests separate and non-blocking.
- **Frontend**: React Testing Library + Vitest; mock Keycloak provider.
- **Infra**: Write validation assertions before manifests (e.g., "pod reaches Ready").
- **CI**: Enforced from day one; blocks on red tests.

See [CLAUDE.md](../CLAUDE.md) for full development standards.
