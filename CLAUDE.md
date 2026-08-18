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
- Backend: `POST /api/agents/chat` endpoint + LangGraph agent with mocked LLM
- Frontend: Chat UI component with message display and form handling
- Testing: Complete unit and component test coverage with deterministic mocked responses
- Tool-calling: Mocked tool calls working; real MCP integration is Phase 3

**Phase 2b Complete ✓**: Real LLM + Streaming Foundation (Deferred to Phase 3+)
- Config infrastructure: LLM provider switch (fake/llama-cpp/openai-compatible) via environment variables
- `ChatOpenAI` integration ready: factory function supports real LLM clients
- Streaming architecture: identified, designed, deferred (tool-calling + streaming has known rough edges in llama.cpp)
- Dependencies upgraded: LangChain ecosystem to v1.x stable (langchain, langchain-core, langgraph, langchain-openai)

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
- **MCP transport**: Must be Streamable HTTP (not stdio) for service-to-service K8s deployment (Phase 3+).

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
