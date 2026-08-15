# EAIStack — Claude Code Context

## Project Overview

**Enterprise AI Stack**: a forkable Kubernetes-native template for building offline/air-gapped enterprise AI applications.

**Core stack**: React/TypeScript frontend, FastAPI backend, LangGraph agent orchestration, Keycloak auth, PostgreSQL + pgvector, MinIO object storage, llama.cpp (llama-server) for local LLM inference, MCP servers for tool integration.

**Key constraints**:
- Fully air-gapped (no internet at runtime; all dependencies vendored)
- Kubernetes-native (K3s as the target, production-grade but approachable for K8s-unfamiliar users)
- Thin vertical slice first (one complete flow: login → chat → agent-with-tool → grounded response)
- Strict TDD discipline (mock LLM boundary, TDD everything else; CI gates every commit)

## Implementation Plan

See `/CLAUDE.md` (this file) and `/.claude/plans/indexed-tinkering-babbage.md` for the full architecture and phasing.

**Current phase**: Phase 0 — Testing & CI scaffolding.

## Development Standards

### Testing (TDD enforced by CI)

**Backend (FastAPI/LangGraph)**:
- Mock the LLM boundary (`FakeChatModel`); TDD all deterministic logic
- `tests/unit/` — fast, mocked, gates every commit
- `tests/integration/` — real llama-server, not gated, smoke-test only
- Fixtures: fake LLM, test Postgres (testcontainers), test MinIO

**Frontend (React/TypeScript)**:
- React Testing Library + Vitest
- Mock Keycloak provider for auth-flow tests
- Component and integration tests written first

**MCP doc-search server**:
- TDD pgvector query logic against test Postgres

**Infra (Helm/K3s)**:
- Write validation scripts before manifests (assertions about pod readiness, TLS cert validity, etcd encryption)
- CI runs infra tests against k3d

**CI pipeline**:
- GitHub Actions (or equivalent): runs unit tests + lint on every PR, fails on red
- Coverage threshold on changed code (baseline once Phase 1 code exists)

### Coding Standards

- No comments unless the *why* is non-obvious; well-named code is its own documentation
- Prefer deterministic, testable logic; hide non-determinism (LLM calls) behind mock boundaries
- No premature abstractions; three similar lines is better than a shared utility
- Don't add error handling for scenarios that can't happen; trust framework guarantees
- Avoid feature flags and backwards-compatibility shims; just change the code

### Commit Standards

- Descriptive commit messages (explain the *why*, not just what changed)
- One logical change per commit; squash before merge if needed
- Reference issue/plan context if relevant, but don't bury the actual change description

## Helpful Context

- This is a greenfield project; no legacy code to preserve
- The user is less familiar with Kubernetes; infrastructure docs should assume minimal prior K8s knowledge
- Encryption and session/context lifecycle are hard requirements (not bolt-on later)
- Bitnami Helm charts are off-limits (deprecated free tier); use official upstream charts
- MCP transport must be Streamable HTTP (not stdio) for service-to-service K8s deployment

## Directory Structure

```
/frontend                 React + TS frontend
/backend                  FastAPI backend + LangGraph + guardrails
/mcp-servers             Custom MCP tool servers
/infra                   Kubernetes (K3s), Helm charts, air-gap scripts
/docs                    Architecture, setup, security docs
/.github/workflows       CI pipelines
```

See plan file for detailed structure per layer.
