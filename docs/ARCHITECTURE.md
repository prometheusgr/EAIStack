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
