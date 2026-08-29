# EAIStack

**A forkable, Kubernetes-native template for building offline/air-gapped enterprise AI applications.**

EAIStack gives you a working, end-to-end reference implementation of the pattern most enterprises actually need — a chat UI backed by a tool-calling LLM agent, grounded in your own documents, running entirely inside your network with no calls out to a third-party API. Fork it, replace the branding and business logic, and keep the plumbing: auth, session isolation, retrieval, guardrails, retention, and encryption are already built and tested.

## Why this exists

Most "build your own ChatGPT" tutorials assume you can call OpenAI's API and store data wherever is convenient. Regulated and air-gapped environments (defense, healthcare, finance, government) can't make either assumption. EAIStack is built for that harder case from day one:

- **No internet at runtime.** Every dependency — container images, Helm charts, LLM weights — is vendored and mirrored into a private registry before the cluster ever goes live.
- **Local inference only.** `llama.cpp` (`llama-server`) serves the chat model and embeddings; nothing leaves the cluster.
- **Kubernetes-native, but approachable.** Targets K3s specifically because it's production-grade without demanding a K8s expert to operate it.
- **Compliance is structural, not aspirational.** Session isolation, data retention, audit logging, and encryption are enforced by code structure and tests (see [AGENTS.md](AGENTS.md)), not by a policy document nobody rereads.
- **Built for a 10-year lifecycle.** Strict TDD, clear naming, and no shortcuts — see the [Development Standards](AGENTS.md) this repo holds itself to.

## What's inside

| Layer            | Technology                 | Role                                                                                                |
| ---------------- | -------------------------- | --------------------------------------------------------------------------------------------------- |
| Frontend         | React + TypeScript (Vite)  | Chat UI, document upload, admin settings                                                            |
| Backend          | FastAPI + LangGraph        | REST API, agent orchestration, guardrails                                                           |
| Auth             | Keycloak (OIDC)            | Login, JWT issuance/validation, RBAC (admin vs. user)                                               |
| Database         | PostgreSQL + pgvector      | Relational data, conversation checkpoints, vector search                                            |
| Object storage   | MinIO                      | Uploaded knowledge-base documents                                                                   |
| LLM inference    | llama.cpp (`llama-server`) | Local chat completion, OpenAI-compatible API                                                        |
| Embeddings       | nomic-embed (768-dim)      | Local embedding generation for retrieval                                                            |
| Tool integration | MCP (Streamable HTTP)      | `doc-search` server exposes `search_knowledge_base` to the agent as a separately deployable service |
| Deployment       | K3s + Helm                 | Production-grade, minimal-footprint Kubernetes                                                      |

### End-to-end flow

```
User (browser)
  → Frontend (React) — OIDC login via Keycloak
    → Backend API (FastAPI) — JWT validation
      → LangGraph agent — conversation state checkpointed in Postgres, keyed by (user_id, thread_id)
        → llama-server — local LLM inference (mocked at this boundary in unit tests)
        → doc-search (MCP, Streamable HTTP) — pgvector similarity search over the user's own documents
      → Guardrails — input/output validation
    → Response → Frontend
```

Documents uploaded through the knowledge base are stored in MinIO, text-extracted, chunked, embedded, and made searchable by the agent — scoped per user, with retention and audit logging enforced end to end.

## Current status

The vertical slice — **login → chat → agent-with-tool → grounded response** — is complete and further hardened with session persistence, retention, and document storage. Phases completed so far:

- **Phase 1 — Authentication & local dev loop**: Keycloak OIDC, JWT validation, protected endpoints.
- **Phase 2 — Agent orchestration & LLM integration**: `POST /api/agents/chat`, LangGraph agent, real `llama-server` + real embeddings, pgvector-backed `search_knowledge_base`.
- **Phase 3 — MCP server integration**: `search_knowledge_base` extracted into a standalone `doc-search` MCP server reached over Streamable HTTP, with independent JWT verification against Keycloak (doc-search never trusts a bare `user_id` from the backend).
- **Phase 4a — Conversation persistence & session isolation**: LangGraph state persists to Postgres via a custom checkpointer; `(user_id, thread_id)` ownership enforced structurally by `ThreadRepository`.
- **Phase 4b — Data retention & admin configuration**: every persisted store has a documented, enforced retention window (env default + DB override), a K8s CronJob sweep, and an append-only audit log.
- **Phase 4 (guardrails/prompts/agent scaffolding)** and **document storage (MinIO upload/extraction)** — both closed; see [Roadmap](#roadmap--whats-next) for what's still open around them.
- **Phase 5 — TLS, secrets, and K8s deployment**: Helm charts (postgres, minio, keycloak, backend, doc-search, frontend, llama-server, embedding-server, umbrella), cert-manager-issued mTLS between services, `sslmode=verify-full` to Postgres, no plaintext secrets — see [docs/SECURITY.md](docs/SECURITY.md) for the full decision log.

Streaming chat responses are deliberately deferred — tool-calling + streaming has known rough edges in llama.cpp.

## Getting started

### Prerequisites

- Python 3.10+
- Node.js 20 (LTS) — matches CI and `frontend/.nvmrc`
- Docker & Docker Compose
- Git

### Local development (docker-compose)

```bash
git clone <your-fork-url>
cd EAIStack
docker-compose up
# frontend: http://localhost:3000
```

Add `--profile llm` to also start the local `llama-server` (requires a GGUF model in `./models/` — see [docs/AIRGAP_SETUP.md](docs/AIRGAP_SETUP.md)).

### Backend only

```bash
cd backend
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -e ".[dev]"
uvicorn app.main:app --reload   # http://localhost:8000
pytest tests/unit/ -v
```

### Frontend only

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
npm test
```

### Database migrations

```bash
cd backend
alembic upgrade head
```

Full command reference (linting, type-checking, single-test invocations, e2e tests) is in [CLAUDE.md](CLAUDE.md#common-development-commands).

## Forking this template

1. **Read [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md) first.** They define the architecture, the phase history, and the non-negotiable development standards (TDD, the three-layer frontend architecture, the repository pattern for user isolation, retention field semantics). Deviating from these patterns silently is treated as a defect in this codebase, not a style choice.
2. **Swap branding and domain logic**, not the plumbing. Auth, session isolation, retention, and the MCP transport pattern are designed to be reused as-is.
3. **Follow the guides in the table in [AGENTS.md](AGENTS.md#detailed-implementation-guides)** before adding a new database model, backend service, frontend API integration, repository, or agent — each has a canonical shape with a worked example.
4. **Before deploying for real**: read [docs/SECURITY.md](docs/SECURITY.md) (encryption, TLS, and retention decision log) and [infra/k3s/README.md](infra/k3s/README.md) (K3s + encryption-at-rest walkthrough), and run [infra/scripts/bootstrap-airgap.sh](infra/scripts) against your own registry.
5. **Move hardcoded Keycloak secrets to K8s secrets** (`backend/app/core/config.py`) before any non-local deployment.

See also [CONTRIBUTING.md](CONTRIBUTING.md) for the day-to-day contribution workflow.

## Roadmap / what's next

Inferred from the repository's open GitHub issues, roughly in the order they'd unblock or logically follow each other. Fork maintainers should treat this as a starting backlog, not a commitment — prioritize what your deployment actually needs.

### In progress / near-term (Phase 5 follow-through)

- **[#9](../../issues/9) — K3s deployment walkthrough + encryption-at-rest verification.** The Helm charts exist and are validated in CI, but no one has deployed to a live cluster yet. This issue is where TLS and at-rest encryption get _proven_, not just implemented — cert SANs, LUKS-encrypted volumes, `sslmode=verify-full` actually rejecting plaintext, an auditor-facing verification script.
- **[#10](../../issues/10) — Air-gap bootstrap and image mirroring.** `infra/scripts/bootstrap-airgap.sh` is currently a stub. Needs to build/pull/tarball every image the Helm charts reference (the current hardcoded list is already stale — missing `doc-search` and `embedding-server` entirely), plus a CI assertion that no chart can silently reference an unmirrored image.
- **[#17](../../issues/17) — TLS-by-default in docker-compose.** Local dev still talks plaintext HTTP between services (MinIO included), unlike the TLS-hardened production Helm deployment. Needs dev-only certs so local dev exercises the same code paths as production.

### Compliance gaps (explicitly deferred, not forgotten)

- **[#12](../../issues/12) — Backup strategy, encryption, and retention reconciliation.** There is currently no backup path in the repo at all. Needs a documented mechanism (pg_dump vs. snapshots vs. replication), encrypted backups, MinIO object backups, restore verification, and reconciliation with the existing data-retention policy so purged data doesn't quietly survive in a backup.
- **[#16](../../issues/16) — Configurable guardrail thresholds.** Guardrail behavior (input length limits, prompt-injection heuristics) is currently hardcoded with no admin override, unlike every other tunable setting in the system (retention windows, LLM provider). Needs the same env-default + DB-override pattern, surfaced in the Settings UI, and audit-logged.

### Retrieval quality (RAG improvements)

- **[#7](../../issues/7) — Improve RAG for technical content.** A sequenced set of four improvements, each building on the last: (1) fix missing asymmetric embedding prefixes (`search_document:`/`search_query:`) that are silently degrading retrieval quality today; (2) structure-aware chunking so long documents aren't embedded as one truncated vector; (3) hybrid vector + BM25 (Postgres full-text) search for exact-token queries like error codes and version strings; (4) cross-encoder reranking, only if 1–3 prove insufficient. Includes a recommendation to build a small retrieval evaluation harness (Recall@k, MRR) before or alongside the first change, so later steps are justified by numbers rather than opinion.

### Exploratory / not yet scoped

- **[#5](../../issues/5) — Long-term/semantic memory.** Distinguishes session memory (already built, via LangGraph checkpoints) from cross-session semantic memory (facts/preferences persisted and retrieved by similarity) and knowledge graphs (structured entity relationships). Recommendation on record: start with semantic memory only, as a `user_memories` pgvector table reusing the existing embedding pipeline, and skip knowledge graphs until there's a concrete multi-hop reasoning need.
- **[#4](../../issues/4) — LLM observability.** Tracing agent runs (LLM calls, tool calls, latency, token counts), prompt/response inspection, and evaluation hooks. Self-hosted only, per the air-gap constraint; Arize Phoenix is the current leaning.

## Documentation map

- [CLAUDE.md](CLAUDE.md) — architecture, phase history, common commands
- [AGENTS.md](AGENTS.md) — development standards, TDD discipline, mandatory implementation patterns
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — key architecture decisions and rationale
- [docs/SECURITY.md](docs/SECURITY.md) — encryption, TLS, and retention policy/decision log
- [docs/DATABASE_MODELS.md](docs/DATABASE_MODELS.md), [docs/BACKEND_SERVICES.md](docs/BACKEND_SERVICES.md), [docs/FRONTEND_ARCHITECTURE.md](docs/FRONTEND_ARCHITECTURE.md), [docs/REPOSITORY_PATTERN.md](docs/REPOSITORY_PATTERN.md), [docs/TIME_INJECTION.md](docs/TIME_INJECTION.md), [docs/AGENT_LIBRARY.md](docs/AGENT_LIBRARY.md) — canonical shapes for new code, referenced from AGENTS.md
- [docs/AIRGAP_SETUP.md](docs/AIRGAP_SETUP.md) — vendoring dependencies and models for offline deployment
- [infra/k3s/README.md](infra/k3s/README.md) — K3s deployment and encryption-at-rest verification

## License

Licensed under the [Apache License, Version 2.0](LICENSE). Permissive, with an explicit patent grant — fork, modify, and deploy internally or commercially with no obligation to share changes back.
