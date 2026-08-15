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
        MCP tool server (Streamable HTTP)
          → pgvector (document search)
          → MinIO (document retrieval)
      → Response to frontend (streaming)
```

## Phases

1. **Phase 0**: Test & CI scaffolding
2. **Phase 1**: Local dev (docker-compose, all services running)
3. **Phase 2**: LangGraph + llama-server integration
4. **Phase 3**: MCP + pgvector doc search
5. **Phase 4**: Guardrails, prompt library, agent library scaffolding
6. **Phase 4a**: Session/context lifecycle (configurable cleanup)
7. **Phase 5**: Kubernetes + air-gap packaging + encryption

See `/.claude/plans/indexed-tinkering-babbage.md` for detailed phase breakdown.

## Testing Standards

- **Backend**: Mock LLM boundary; TDD all deterministic logic. Real LLM integration tests separate and non-blocking.
- **Frontend**: React Testing Library + Vitest; mock Keycloak provider.
- **Infra**: Write validation assertions before manifests (e.g., "pod reaches Ready").
- **CI**: Enforced from day one; blocks on red tests.

See [CLAUDE.md](../CLAUDE.md) for full development standards.
