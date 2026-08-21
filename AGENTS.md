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

### Time-Dependent Functions (No Global Mocking)

If a function's behavior changes based on time, **accept `now: datetime` as a parameter** instead of calling `datetime.now()` inside the function. This makes tests deterministic without mocking:

**Pattern:**
```python
def calculate_expiry(issue_date: datetime, ttl_days: int, now: datetime) -> datetime:
    """Calculate token expiry. Accept now for testability."""
    return now + timedelta(days=ttl_days)

# Test: no mocking needed
def test_calculate_expiry():
    issue = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
    expiry = calculate_expiry(issue, ttl_days=7, now=now)
    assert expiry == datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
```

**Why this works:** Tests pass fixed `now` values; no mock setup needed. The function signature is honest about its dependency on time. Use pytest fixtures `now_fixed` and `now_fixed_naive` from `conftest.py` for standard test times.

**Linter compliance:** `python tools/lint_time_injection.py` flags functions calling `datetime.now()` without accepting `now` as a parameter (warning mode; gates CI at error severity).

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

### Retention Field Semantics (is not None, Not Truthiness)

When `None`, `0`, and `False` are all meaningful, distinct values for a field, use `is not None` checks, never truthiness. `if retention_hours:` silently treats `0` the same as `None`/unset — a real bug when `0` means something specific ("purge immediately") rather than "no value."

**Pattern:**
```python
from typing import Annotated

RetentionHours = Annotated[
    int | None,
    "None='keep forever', 0='purge immediately'",
]

class SystemSettings(Base):
    conversation_retention_hours: Mapped[RetentionHours]
```

**Semantics** (document this for every field with this shape):
- `None` = keep forever (no retention limit)
- `0` = purge immediately (very aggressive)
- `1+` = keep for this many hours

**Checklist:**
```
- [ ] Is there a truthiness check on a nullable field?
  ✗ `if retention_hours:`
  ✓ `if retention_hours is not None:`
- [ ] Are None, 0, and positive values all handled?
```

**Tests:** parametrize edge-case fields over `[None, 0, 1, 24]` (or the equivalent boundary values) so a truthiness regression fails a test immediately, not silently in production:
```python
@pytest.mark.parametrize("retention_hours", [None, 0, 1, 24])
def test_retention_hours_edge_cases(retention_hours):
    ...  # verify each value is handled correctly
```

**Linter:** `python tools/lint_edge_case_truthiness.py` flags `if <name>:` / `if not <name>:` where `<name>` is a parameter or attribute annotated `int | None` / `Optional[int]` (warning mode; parse errors gate CI). Runs automatically in CI, alongside `lint_time_injection.py`.

### Repository Checklist (Structural Enforcement, Not Policy)

A repository's public surface is the enforcement mechanism, not a comment or a code review note. Two constraints are enforced this way today:

1. **User isolation** (`ThreadRepository`, `APIKeyRepository`): every read/write method takes `user_id` and filters on it. There is no method that returns or mutates a row without proving ownership first. See [docs/REPOSITORY_PATTERN.md](../docs/REPOSITORY_PATTERN.md).
2. **Append-only audit/log stores** (`AuditLogRepository`): the class defines no `update`, `delete`, `remove`, or `purge` method. A purge path or bugfix literally cannot call a method that doesn't exist.

**Pattern for a new append-only store:**
```python
class WidgetAuditRepository:
    """Append-only. No update/delete/remove/purge method by design."""

    def record(self, *, now: datetime, ...) -> WidgetAuditEntry:
        ...  # only ever inserts

    def list_recent(self, limit: int = 100) -> list[WidgetAuditEntry]:
        ...  # read-only
```

**Checklist:**
```
- [ ] Does this repository back an audit trail, log, or other store that must never be mutated or purged?
- [ ] If so, does its class name contain "Audit" or "Log" (so the linter covers it)?
- [ ] Does the class define only insert/read methods — no update, delete, remove, or purge?
- [ ] Is there a test asserting the class's public method set, so an accidental addition fails a test even before the linter runs?
```

**Linter:** `python tools/lint_repositories.py` flags any `*Repository` class whose name contains `Audit` or `Log` if it defines a method named (or prefixed) `update`, `delete`, `remove`, or `purge` (error severity; gates CI). Naming-convention scoped — a new append-only store is covered automatically as long as its class name says so. Runs automatically in CI, alongside `lint_time_injection.py` and `lint_edge_case_truthiness.py`.

### Frontend (React/TypeScript)

- React Testing Library + Vitest
- Mock Keycloak provider for auth-flow tests
- Component and integration tests written first
- Test user interactions and data flow, not DOM internals
- Use custom hooks for all API calls (no scattered fetch() calls)

**Test commands**:
```bash
npm test                 # Run all tests
npm run test:ui         # Run with interactive UI
npm test -- filename.test.ts  # Single test file
```

### React Unmount Guard Pattern (No setState After Unmount)

Any hook or component that sets state after an `await` (an API call, a token refresh, an auth check) must guard against the component having unmounted while that call was in flight. Calling `setState` after unmount doesn't crash in modern React, but it silently leaks the closure and signals a race the test suite should be catching.

**Pattern:** use the shared `useIsMounted()` hook (`src/hooks/useIsMounted.ts`) and check it immediately before every `setState` that follows an awaited call:

```ts
import { useIsMounted } from './useIsMounted'

function useThing() {
  const isMounted = useIsMounted()
  const [data, setData] = useState<Thing | null>(null)

  useEffect(() => {
    fetchThing().then((result) => {
      if (isMounted()) setData(result)
    })
  }, [])

  return data
}
```

**Why this works:** `useIsMounted()` flips a ref to `false` in its cleanup function, so the check reflects the current mount state at the moment the awaited call resolves — not the state when the effect was scheduled.

**Checklist:**
```
- [ ] Does this hook/component call setState after an await (fetch, async auth check, timer)?
- [ ] Is every such setState guarded by `if (isMounted())`?
- [ ] Does a test exercise unmounting mid-request and assert no post-unmount state update/warning?
```

Applied in `AuthContext.tsx` (auth init, token refresh, logout) and available to any hook via `useApiCall`/`useApiMutation` or direct use of `useIsMounted()`.

### MCP doc-search server (Phase 3+)

- TDD pgvector query logic against test Postgres

### Infra (Helm/K3s) (Phase 5+)

- Write validation scripts before manifests (assertions about pod readiness, TLS cert validity, etcd encryption)
- CI runs infra tests against k3d

### CI Pipeline

GitHub Actions (see `.github/workflows/ci.yml`) runs on every PR:
- **Backend**: `pytest tests/unit/` + `ruff check` + `black --check` + `mypy app/`
- **Frontend**: `npm test` + `npm run lint` + `npm run build`
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

## Detailed Implementation Guides

The patterns below are **mandatory shapes**, not suggestions — each has a canonical worked example in `docs/`. Before writing a new database model, service, frontend API integration, or repository, **read the matching guide and copy its shape**. Do not improvise a variant structure; a new file that "does its own thing" is an anti-pattern even if it works, because it breaks consistency for the next person (or agent) who has to extend it.

| If you are about to... | Read this first | Covers |
|---|---|---|
| Add or change a database table | [docs/DATABASE_MODELS.md](../docs/DATABASE_MODELS.md) | SQLAlchemy model shape, Alembic migration workflow, migration troubleshooting |
| Add backend business logic used by 2+ endpoints | [docs/BACKEND_SERVICES.md](../docs/BACKEND_SERVICES.md) | When to create a service, service module shape, refactoring endpoints to use it |
| Add or change a frontend API call | [docs/FRONTEND_ARCHITECTURE.md](../docs/FRONTEND_ARCHITECTURE.md) | API client → service → hook → component layering, full worked example, testing each layer |
| Add a new database query used by an endpoint | [docs/REPOSITORY_PATTERN.md](../docs/REPOSITORY_PATTERN.md) | Repository class shape, user-isolation and soft-delete query patterns |
| Write a time-dependent function | [docs/TIME_INJECTION.md](../docs/TIME_INJECTION.md) | Time injection pattern, pytest fixtures, testability without mocking |

**Why this matters:** these four areas are exactly where inconsistent one-off implementations creep in — a service with FastAPI imports, a component with a raw `fetch()`, a query written inline in an endpoint instead of a repository. The guides exist so every instance looks the same. If you find yourself deviating from the documented shape, that's a signal to either follow it or flag the guide as outdated — not to invent a new shape silently.

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
