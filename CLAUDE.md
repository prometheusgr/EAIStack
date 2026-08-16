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
- Backend: `POST /api/agents/chat` endpoint + LangGraph agent with mocked LLM (no real llama-server yet)
- Frontend: Chat UI component with message display
- Testing: End-to-end flow with deterministic (mocked) responses and TDD-first implementation
- Scope note: Streaming (SSE/WebSocket), persistence (Postgres checkpointer), and real llama-server wiring deferred to Phase 2b/3
- Tool-calling: Mocked tool calls work; real MCP integration and pgvector search is Phase 3

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

# Linting & building
npm run lint            # Check
npm run build           # Production build
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

### Testing (TDD enforced by CI)

**Backend (FastAPI/LangGraph)**:
- Mock the LLM boundary (`FakeChatModel` in tests); TDD all deterministic logic
- `tests/unit/` — fast, mocked, gates every commit (CI requirement)
- `tests/integration/` — real llama-server, not gated, smoke-test only
- Fixtures: fake LLM, test Postgres (testcontainers), test MinIO
- For Phase 2: Agent endpoint tests must mock LLM responses; add integration smoke-test for real llama-server

**Frontend (React/TypeScript)**:
- React Testing Library + Vitest
- Mock Keycloak provider for auth-flow tests
- Component and integration tests written first
- For Phase 2: Chat UI component tests with mocked API responses

**MCP doc-search server** (Phase 3+):
- TDD pgvector query logic against test Postgres

**Infra (Helm/K3s)** (Phase 5+):
- Write validation scripts before manifests (assertions about pod readiness, TLS cert validity, etcd encryption)
- CI runs infra tests against k3d

**CI pipeline**:
- GitHub Actions (see `.github/workflows/ci.yml`): runs unit tests + lint on every PR, fails on red
- Backend: `pytest tests/unit/` + `ruff check` + `black --check`
- Frontend: `npm test` + `npm run lint`
- Coverage enforced on changed code (baseline exists in Phase 1)

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
    mcp_client/     MCP server integration (Phase 3+)
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
    components/     React components (Phase 2+: ChatWindow, MessageList)
    App.tsx         Entry point
  tests/            Vitest test files
  vitest.config.ts  Test configuration
```

**Key patterns**:
- **Auth**: AuthContext wraps app, handles Keycloak OIDC. Tests mock Keycloak provider (`tests/setup.ts`).
- **API calls**: Fetch from `http://localhost:8001` (backend). Protected endpoints include auth token in headers.

### Other Layers

```
/mcp-servers         Custom MCP servers (Phase 3+): doc-search (pgvector queries), etc.
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
MCP Tools (Phase 3+): pgvector search, MinIO retrieval
  ↓
Response → Frontend
```

## Constraints & Gotchas

- **No Bitnami charts**: Official upstream images only (pgvector/pgvector, keycloak, minio)
- **llama.cpp tool-calling**: Streaming + tool_calls has known rough edges. Test this combo early (Phase 2).
- **Keycloak secrets**: Currently hardcoded in `app/core/config.py`; move to K8s secrets before production (Phase 5).
- **LLM model vendoring**: All models must be downloaded during air-gap setup; no internet at runtime.
- **MCP transport**: Must be Streamable HTTP (not stdio) for K8s pod-to-pod communication (Phase 3+).
- **Session cleanup**: Configurable per deployment: logout-triggered OR TTL-based (or both). Implemented in Phase 4a.
