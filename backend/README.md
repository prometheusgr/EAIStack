# EAIStack Backend

FastAPI service with LangGraph agent orchestration, guardrails, and MCP client integration.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Running Locally

### With docker-compose (full stack)
```bash
cd ..
docker-compose up
```

### Backend only (for development)
```bash
uvicorn app.main:app --reload
```

## Testing

```bash
# Unit tests only (mocked LLM)
pytest tests/unit/

# Integration tests (real llama-server required)
pytest tests/integration/

# Full test run with coverage
pytest --cov
```

## Project Structure

- `app/api/` — REST endpoints
- `app/agents/` — LangGraph graph definitions
- `app/guardrails/` — Input/output validation middleware
- `app/mcp_client/` — MCP tool client wiring
- `app/prompts/` — Prompt library and loader
- `app/db/` — SQLAlchemy models, migrations, session cleanup
- `app/storage/` — MinIO client wrapper
- `app/core/` — Configuration, auth middleware
- `tests/unit/` — Fast, mocked tests
- `tests/integration/` — End-to-end tests (slow)
- `tests/fixtures/` — Shared test utilities

## Key Patterns

### Mocking the LLM Boundary

All LLM calls go through a single client configured at `app.core.llm_client`. Tests use a `FakeChatModel` fixture to avoid real calls:

```python
def test_agent(mock_llm):
    """mock_llm is a FakeChatModel with canned responses."""
    # Your test here
```

### Session Isolation (LangGraph Checkpointer)

Each conversation thread is tied to a user session, stored in Postgres. This prevents context bleeding:

```python
from app.db.checkpointer import PostgresCheckpointer
checkpointer = PostgresCheckpointer(db_session, user_id)
```

## Dependencies

See `pyproject.toml` for locked versions. Key libraries:

- **FastAPI**: async web framework
- **LangGraph**: agent orchestration and state management
- **SQLAlchemy**: ORM for Postgres + pgvector
- **Pydantic**: request/response validation
- **MiniO**: S3-compatible object storage client
