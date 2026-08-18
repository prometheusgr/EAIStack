# Development Standards & Process

This file defines coding standards and development process for EAIStack contributors. It is referenced by both Claude Code (via CLAUDE.md import) and GitHub Copilot (via .github/copilot-instructions.md).

## Testing (TDD enforced by CI)

**TDD is mandatory.** Tests are the specification. Every feature and bug fix is driven by a test written first.

### TDD Discipline

**For new features**:
1. Write a failing test that specifies the desired behavior
2. Run the test and confirm it fails (red)
3. Implement the minimum code to make it pass (green)
4. Refactor for clarity and maintainability without changing behavior (refactor)

**For bugs**:
1. Write a failing test that reproduces the bug
2. Run the test and confirm it fails (red)
3. Research and fix the root cause
4. Run the test and confirm it passes (green)
5. Refactor if needed for clarity

**Test outcomes define correctness.** If a test passes, the function behaves as specified. If it fails, the implementation is wrong. There is no other source of truth.

All unit tests must pass locally before pushing. Every commit must have corresponding tests.

### What NOT to Test

**Tests are for logic, not build artifacts.** Don't write tests for:
- **Dependency resolution**: If `npm install` fails or a module can't be imported, that's a build error caught by the compiler/CI, not a logic error. Write a test when there's logic to verify (e.g., "does this function handle the data correctly").
- **Type checking**: TypeScript catches type errors at compile time. Don't write tests to verify types work.
- **Configuration/setup**: Environment setup, webpack/vite config, CI pipelines — these belong in validation scripts, not unit tests.
- **Import/export mechanics**: The module system handles this; a successful build means it works.

**Tests must specify behavior.** A good test says "when I call this function with X, it returns Y." A bad test says "this function exists and doesn't crash." Unit tests should verify business logic, not implementation details.

### Backend (FastAPI/LangGraph)

- Mock the LLM boundary (`FakeChatModel` in tests); TDD all deterministic logic
- `tests/unit/` — fast, mocked, gates every commit (CI requirement)
- `tests/integration/` — real llama-server, not gated, smoke-test only
- Fixtures: fake LLM, test Postgres (testcontainers), test MinIO

**Test commands**:
```bash
pytest tests/unit/                    # Unit tests only (mocked, fast)
pytest tests/unit/test_auth.py -v     # Single test file
pytest tests/unit/ -k "test_name" -v  # Single test function
pytest --cov                          # Full coverage report
pytest tests/integration/              # Integration tests (real services, slow)
```

### Effective Unit Tests (All Platforms)

**A unit test should:**
1. **Test behavior, not implementation** — If you rewrote the function but kept the same logic, the test should still pass.
2. **Be deterministic** — Same input → same output, every time. No randomness, no mocking of time (unless testing time-dependent behavior). No mocked LLM calls in business logic tests (mock only at the LLM boundary).
3. **Use real data paths** — If testing database queries, use a real test database (e.g., testcontainers). If testing API calls, use real HTTP clients. Mocking should be minimal and only at external boundaries (LLM service, third-party APIs).
4. **Have clear failure messages** — If a test fails, the error message should tell you what went wrong, not just "assertion failed."
5. **Test one thing** — A single test should verify one behavior. If your test has "and" in the name, split it.

**Example (what NOT to do):**
```python
def test_api_key_form_works():  # ❌ Too vague
    form = APIKeyForm()
    assert form is not None  # ❌ Useless
```

**Example (what TO do):**
```python
def test_api_key_form_rejects_empty_name():  # ✓ Specific behavior
    form = APIKeyForm()
    result = form.validate({'name': '', 'provider': 'openai', 'secret': 'key'})
    assert result.is_valid is False  # ✓ Clear what we're checking
    assert 'name' in result.errors  # ✓ Shows which field failed
```

### Frontend (React/TypeScript)

- React Testing Library + Vitest
- Mock Keycloak provider for auth-flow tests
- Component and integration tests written first
- Test user interactions and data flow, not DOM internals

**Test commands**:
```bash
npm test                 # Run all tests
npm run test:ui         # Run with interactive UI
npm test -- filename.test.ts  # Single test file
```

### MCP doc-search server (Phase 3+)

- TDD pgvector query logic against test Postgres

### Infra (Helm/K3s) (Phase 5+)

- Write validation scripts before manifests (assertions about pod readiness, TLS cert validity, etcd encryption)
- CI runs infra tests against k3d

### CI Pipeline

GitHub Actions (see `.github/workflows/ci.yml`) runs on every PR:
- **Backend**: `pytest tests/unit/` + `ruff check` + `black --check`
- **Frontend**: `npm test` + `npm run lint`
- Coverage enforced on changed code (baseline exists in Phase 1)

## Coding Standards

**Code must be maintainable for a 10-year lifecycle.** This is not a throwaway project. Every line should be clear enough that someone reading it in 2034 understands intent without archaeological investigation.

### Readability & Intent

- **Clear, descriptive names**: Variables, functions, classes should reveal intent. A reader should understand *what* code does and *why* it matters without needing to trace execution.
- **No clever tricks**: Avoid obfuscation, cryptic patterns, or "clever" optimizations that require footnotes to understand. Clarity beats cleverness.
- **Comments only for *why*, not *what***; well-named code documents the what. Only comment non-obvious decisions, constraints, or workarounds.
- **One responsibility per function**: Functions should do one thing well. Long functions with multiple concerns are a maintenance burden.

### Logic & Testability

- **Prefer deterministic, testable logic**: Hide non-determinism (LLM calls, I/O, time-dependent behavior) behind mock boundaries so logic can be tested in isolation.
- **No mocking of LLM at the wrong boundary**: Should only mock at the LLM service boundary (`app.core.llm_client`), not in business logic. Keeps mocks honest.
- **Trust framework guarantees**: Don't add error handling for scenarios that can't happen. Trust that FastAPI validates inputs, SQLAlchemy handles transactions correctly, etc. Add error handling only at system boundaries (user input, external APIs).

### Design & Abstraction

- **No premature abstractions**: Three similar lines is better than a shared utility. Don't extract a function unless you have a second caller or a strong reason to isolate logic.
- **Avoid feature flags and backwards-compatibility shims**: Just change the code. Feature flags add cognitive load and technical debt. If code needs to work two ways, it needs refactoring.
- **Prefer composition over inheritance**: Simpler to understand, test, and modify.

## Commit Standards

- **Descriptive commit messages**: explain the *why*, not just what changed
- **One logical change per commit**; squash before merge if needed
- **Reference issue/plan context** if relevant, but don't bury the actual change description

**Commit message format**:
```
Brief one-line summary

Longer explanation of why this change matters. Reference the plan or
issue if applicable. Focus on the decision, not the implementation.
```

## Code Review Checklist

### TDD & Testing

- [ ] Tests written first (TDD) — test exists and fails before implementation
- [ ] All unit tests pass locally and in CI
- [ ] Tests specify behavior, not implementation (would pass if refactored correctly)
- [ ] No test-only mocking that wouldn't apply to production code
- [ ] Coverage: all new code paths have corresponding tests

### Readability & Maintainability

- [ ] Variable, function, and class names are clear and reveal intent
- [ ] No comments unless explaining *why*; the code itself documents *what*
- [ ] Functions do one thing well (single responsibility)
- [ ] No clever tricks, obfuscation, or cryptic patterns
- [ ] Logic is deterministic and testable; non-determinism is isolated behind boundaries

### Design & Correctness

- [ ] No mocking of LLM at the wrong boundary (only mock at `app.core.llm_client`)
- [ ] No unnecessary abstractions (no function extracted for a single caller)
- [ ] No feature flags or backwards-compat shims
- [ ] Error handling only at system boundaries (user input, external APIs)
- [ ] Follows the phase scope (don't add features outside the current phase)

### For Bug Fixes

- [ ] Failing test reproduces the bug (red)
- [ ] Root cause identified and documented
- [ ] Fix makes the test pass (green)
- [ ] No regression — existing tests still pass

## Development Workflow

1. **Create a feature branch**: `git checkout -b feature/your-feature`
2. **Write a failing test** (TDD discipline)
3. **Implement to make it pass**
4. **Run full test suite locally** before committing
5. **Commit** with a descriptive message (see Commit Standards above)
6. **Push and open a PR** — CI gates merging on red tests or lint failures

## Adding Database Models & Migrations

**New database tables or schema changes must follow this workflow:**

### 1. Write a Failing Test First (TDD)
```python
# tests/unit/test_new_model.py
def test_new_model_creation():
    """Test that new model persists to database."""
    model = NewModel(user_id="user-1", field="value")
    session.add(model)
    session.commit()
    
    retrieved = session.query(NewModel).filter_by(user_id="user-1").first()
    assert retrieved is not None
    assert retrieved.field == "value"
```

### 2. Define the SQLAlchemy Model
```python
# app/db/models.py
class NewModel(Base):
    """Description of what this model represents."""
    __tablename__ = "new_models"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    field = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    
    def __repr__(self):
        return f"<NewModel(id={self.id}, user_id={self.user_id}, field={self.field})>"
```

**Model best practices:**
- Always include `id` (UUID primary key), `user_id` (for data isolation), `created_at`, `updated_at`
- Add `index=True` to frequently queried columns (user_id, doc_id, etc.)
- Use proper types (String, Text, DateTime, JSON, Vector for pgvector)
- Include foreign keys with `ondelete='CASCADE'` for referential integrity
- Add soft-delete support with optional `deleted_at` column if needed

### 3. Generate the Alembic Migration
```bash
cd backend
# Alembic inspects models and generates migration
alembic revision --autogenerate -m "Add NewModel table"
```

This creates a new file in `alembic/versions/`.

### 4. Review the Generated Migration
Always review the generated migration file:
```python
# alembic/versions/xxx_add_new_model_table.py
def upgrade() -> None:
    op.create_table(
        'new_models',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False, index=True),
        sa.Column('field', sa.String(255), nullable=False),
        # ... other columns
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('new_models')
```

**Verify:**
- All columns are present with correct types
- Indexes are on the right columns
- Foreign keys have proper `ondelete` behavior
- Primary keys are defined correctly

### 5. Test the Migration Locally
```bash
cd backend

# Apply the migration
alembic upgrade head

# Run your new test to verify it works
pytest tests/unit/test_new_model.py -v

# Test rollback
alembic downgrade -1

# Re-apply to verify idempotency
alembic upgrade head
```

### 6. Commit Both Files
**Always commit the model AND the migration together:**
```bash
git add app/db/models.py
git add alembic/versions/xxx_add_new_model_table.py
git commit -m "Add NewModel with user isolation

- Stores new_field data per user
- Includes user_id index for query performance
- Soft-delete ready with deleted_at column
"
```

### 7. Run Full Test Suite
```bash
pytest tests/unit/ -v
```

All tests must pass, including the new model test and existing database tests.

## Adding Backend Services

**Business logic should live in the service layer (`app/services/`), not in API endpoints.** Services isolate reusable logic, enable testing without HTTP/FastAPI concerns, and prevent inter-API coupling.

### When to Create a Service

Create a service when:
- Logic is used by **more than one API endpoint**
- Logic is **independent of HTTP concerns** (request/response handling)
- Logic should be **unit-testable in isolation** (no FastAPI mocking needed)
- Logic is a **distinct responsibility** that could live in another context (e.g., embedding generation, search, validation)

Do NOT create a service for:
- Simple DTO conversions (leave in the endpoint)
- Single-use endpoint logic (keep in the endpoint until it's needed elsewhere)
- HTTP concerns (auth, headers, status codes—these belong in endpoints)

### Pattern: Create a Service

**1. Write a Failing Test First (TDD)**
```python
# tests/unit/test_embedding_service.py
from app.services import generate_embedding

def test_generate_embedding_deterministic():
    """Test: Same text always produces same embedding."""
    text = "Hello world"
    emb1 = generate_embedding(text)
    emb2 = generate_embedding(text)
    assert emb1 == emb2

def test_generate_embedding_different_texts():
    """Test: Different texts produce different embeddings."""
    emb1 = generate_embedding("Text A")
    emb2 = generate_embedding("Text B")
    assert emb1 != emb2
```

**2. Create the Service Module**
```python
# app/services/embedding_service.py
"""Service for embedding generation and management."""

import random


def generate_embedding(text: str) -> list[float]:
    """Generate a deterministic mock embedding from text.

    For MVP, we use a simple hash-based approach that's deterministic
    so the same text always produces the same embedding.

    Args:
        text: The text to generate an embedding for.

    Returns:
        A list of 1536 floating point values representing the embedding.
    """
    random.seed(hash(text) % (2**32))
    return [random.gauss(0, 0.1) for _ in range(1536)]
```

**Key design principles:**
- **No FastAPI imports** — Services are business logic, not HTTP handlers
- **Pure functions where possible** — Deterministic, testable, no side effects
- **Clear type hints** — Use Python 3.9+ style (`list[float]` not `List[float]`)
- **Docstring for public API** — Explain *what* and *why*, not implementation details
- **One responsibility per function** — A service function should do one thing well

**3. Export from Services `__init__.py`**
```python
# app/services/__init__.py
"""Backend service layer for business logic."""

from app.services.embedding_service import generate_embedding

__all__ = ["generate_embedding"]
```

**4. Update API Endpoints to Use the Service**
```python
# app/api/embeddings.py
from app.services import generate_embedding

@router.post("/search")
async def search_embeddings(payload: SemanticSearchRequest, ...):
    """Perform semantic search."""
    # Use the service
    query_embedding = generate_embedding(payload.query_text)
    # ... rest of logic
```

**5. Update Any Other Endpoints Using This Logic**
```python
# app/api/knowledge_base.py
from app.services import generate_embedding

@router.post("")
async def create_knowledge_base(payload: KnowledgeBaseCreate, ...):
    """Create knowledge base with auto-generated embeddings."""
    # Use the service
    embedding_vector = generate_embedding(payload.content)
    # ... rest of logic
```

**6. Remove the Old Implementation**
- Delete the old function from the API module (e.g., `_generate_mock_embedding` from knowledge_base.py)
- Update any tests that imported the old function to use the service instead

**7. Run Tests**
```bash
pytest tests/unit/ -v
```

All tests must pass, including:
- New service tests
- Existing API endpoint tests
- Any other tests that use this logic

### Example: Refactoring Existing Code to a Service

**Before (coupled):**
```python
# app/api/embeddings.py
from app.api.knowledge_base import _generate_mock_embedding  # ❌ Inter-API import

query_embedding = _generate_mock_embedding(payload.query_text)
```

**After (decoupled):**
```python
# app/api/embeddings.py
from app.services import generate_embedding  # ✓ Service import

query_embedding = generate_embedding(payload.query_text)
```

And:
```python
# app/api/knowledge_base.py
from app.services import generate_embedding  # ✓ Service import

embedding_vector = generate_embedding(payload.content)
```

Result: No inter-API imports, reusable logic, easier to test.

### Code Review Checklist for Services

- [ ] Service has no FastAPI imports (is pure business logic)
- [ ] Service functions have clear, descriptive names and docstrings
- [ ] All functions are unit-tested independently (no mocking of HTTP/database at this level)
- [ ] Type hints are present and accurate (Python 3.9+ style)
- [ ] No mutable global state or side effects (where possible)
- [ ] Service is exported from `app/services/__init__.py`
- [ ] All API endpoints using this logic import from the service, not from each other
- [ ] No inter-API imports remain (check with: `grep -r "from app.api.X import" app/api/Y.py`)

## Migration Troubleshooting

**If a migration fails:**

1. **Column type mismatch** — Check that SQLAlchemy column types match database types. Use `compare_type=True` in env.py.
2. **Foreign key constraints** — Ensure parent table exists before creating child table. Alembic respects table order.
3. **Default values** — Use `server_default=` for database-level defaults, `default=` for Python-side defaults.
4. **pgvector columns** — Use raw SQL for Vector types: `op.execute("ALTER TABLE ... ADD COLUMN embedding vector(1536)")`

**To reset migrations in development (WARNING: loses data):**
```bash
# Drop all tables and version history
alembic downgrade base

# Re-apply from scratch
alembic upgrade head
```

**To inspect current schema:**
```bash
# View current migration version
alembic current

# View full history
alembic history --verbose

# Generate offline SQL (don't apply it)
alembic upgrade head --sql
```

## Linting & Formatting

### Backend (Python)

```bash
ruff check .            # Check linting issues
black --check .         # Check formatting
black .                 # Auto-format
ruff check . --fix      # Auto-fix linting issues
mypy app/               # Type checking
```

### Frontend (Node.js)

```bash
npm run lint            # Check linting issues
npm run build           # Production build
```

## Key Constraints

- **LLM mock boundary**: All LLM calls go through `app.core.llm_client`. Unit tests mock this boundary only; don't mock at higher levels.
- **Agent state isolation**: LangGraph checkpoints live in Postgres, keyed by `(user_id, thread_id)`. Prevents context bleeding between sessions.
- **Phase scope**: Don't add features outside the current phase (see CLAUDE.md Current Status). Stick to thin vertical slices.
- **No Bitnami charts**: Official upstream images only (pgvector/pgvector, keycloak, minio).
- **MCP transport**: Must be Streamable HTTP (not stdio) for K8s pod-to-pod communication (Phase 3+).

## Code Maintenance & 10-Year Lifecycle

This software is built to last a decade. Every commit should reflect that perspective.

### What This Means

- **Clarity over brevity**: A few extra lines of clear code beat a dense line of clever code. Your future self (and the person who inherits this code in 2034) will thank you.
- **Tests as living documentation**: A well-written test shows exactly how a function is supposed to be used. It's a form of documentation that can't get out of sync with the code.
- **Refactor for readability**: If you understand how to make code clearer without changing behavior, do it. This is not waste; it's maintenance.
- **Avoid technical debt**: Don't cut corners to ship faster. A quick hack today is a burden for years. TDD, clear naming, and good design cost the same on day 1 but pay dividends forever.
- **Document decisions**: In commit messages and (rarely) in code comments, explain *why* a design choice was made. Future maintainers need to know what constraints or trade-offs led to the current implementation.

### Red Flags

These patterns signal code that will be painful to maintain in year 5:

- **Long functions** (>50 lines): Break them down. Each function should do one thing.
- **Unclear variable names** (e.g., `x`, `temp`, `data`, `config`): Use names that reveal intent.
- **Tight coupling** (functions that depend on implementation details of other functions): Hide complexity behind clear boundaries.
- **Missing or outdated tests**: Tests are the only thing you can trust won't rot. If a test fails, you know something broke. If there's no test, you don't know.
- **Comments that explain *what* the code does**: That's a sign the code is unclear. Rename variables or break up functions instead.
- **Premature optimization**: Profile before optimizing. Unoptimized-but-clear code is faster to understand, maintain, and fix than optimized spaghetti.
