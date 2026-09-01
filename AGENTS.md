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
5. If the feature is user-facing (a new UI flow, or a change to an existing one), add or update an e2e test against the real running stack once the UI exists (see "End-to-End (E2E) Tests" below) — this step comes after green, not before, since there's normally no working UI to drive until the feature is built

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

### End-to-End (E2E) Tests

Unit tests (backend `tests/unit/`, frontend Vitest) mock at the LLM boundary and, for the frontend, mock the Keycloak provider and API clients — by design, so they stay fast and gate every commit. Neither layer ever proves the real stack works together: a real Keycloak login, a real JWT reaching the real backend, a real chat request through the real guardrails. That gap is what `frontend/tests/e2e/` (Playwright) closes.

**TDD-first doesn't cleanly apply here, but TDD-after does — don't skip the test because you can't write it first.** There is normally no UI to drive until the feature exists, so the usual red-green-refactor order inverts for e2e specifically:
1. Build the feature and its unit tests as usual (red → green → refactor)
2. Once the UI/flow is real and running, write (or update) an e2e spec that exercises it exactly the way a user would
3. Run it against the real dev stack (`docker-compose up`) and confirm it passes for the right reason — not just that it doesn't crash

A UI feature isn't done until this step happens. "We can't TDD the UI" is not a reason to skip validating it end-to-end; it's a reason the e2e test comes after, not before.

**When to add or update an e2e spec:**
- A new user-facing flow (a new page, a new guardrail behavior visible in the UI, a new auth path)
- A change to how an existing flow behaves from the user's perspective (not internal refactors that don't change behavior)
- A bug that could only have been caught by driving the real UI against the real backend (a unit test with mocks wouldn't have reproduced it)

**Conventions** (see `frontend/tests/e2e/*.spec.ts` for worked examples):
- Real login through the real Keycloak flow (seeded `testuser`/`testpassword` from `infra/keycloak/realm-import.json`), real backend, no mocked service layer — that's the entire point of this layer.
- Assert on user-visible behavior (text on screen, a banner, an element's visibility), never on internal state or implementation details.
- A test documenting a known, intentional gap (e.g. "PII is not yet redacted") is legitimate and valuable: write it as an explicit assertion of today's behavior, with a comment explaining why, so closing the gap later fails the test on purpose instead of the gap silently persisting forever.
- **Start each test from a clean, known state it controls** (e.g. click "New chat" before sending a message) rather than assuming an empty page. The seeded test account's data (chat threads, uploaded documents, etc.) persists in the same Postgres across every run and every spec file — a fixed message string or an assumption of zero prior history will eventually collide with another test's leftover state or a prior run's data, and a growing page can even cause unrelated elements (like a footer) to intercept clicks.
- Prefer resilient locators (`getByText`, `getByRole`, a stable `placeholder`/`aria-label`) over CSS classes, which drift as components are restyled. When a selector assumption turns out to be wrong (e.g. a login form's submit control being an `<input type="submit">`, not a `<button>`), fix it at the root across every spec that shares it, not just the one you're currently writing — a stale selector fails the same way (silently, via timeout) in every other spec depending on the same page.
- **A spec that asserts on real LLM/embedding *content* (not just that a response rendered) must not assume it runs against a real model.** CI's `e2e-tests` job runs the default `docker-compose up` profile — `LLM_PROVIDER`/`EMBEDDING_PROVIDER` default to `"fake"` (no GGUF download, no llama-server) — so an assertion like "the answer contains the retrieved fact" can never pass there no matter how correct the app is. Before writing such a spec: (1) add a `// requires-profile-llm` marker comment at the top of the file (see `knowledge-base-search-grounding.spec.ts`), naming the environment requirement in the same comment block, (2) exclude the spec from `.github/workflows/ci.yml`'s `e2e-tests` step via `--grep-invert "<a substring of its test title>"` so CI doesn't run a check that's guaranteed to fail regardless of code correctness, and (3) keep the assertion real rather than weakening it to fit the fake provider — a test that can't mean anything against a mock should be scoped out, not gutted. This isn't just a convention: `tools/check_e2e_ci_coverage.py` structurally enforces it — it fails the build if any spec carrying the `requires-profile-llm` marker doesn't have a test title matching CI's current `--grep-invert` pattern, the same way `lint_repositories.py` enforces append-only repositories by structure rather than review vigilance.

**Test commands**:
```bash
docker-compose up                                  # Fake LLM/embedding provider — matches CI exactly
docker-compose up --profile llm                     # Real llama-server + embedding-server (needs GGUF models in ./models/, see docs/LLM_SETUP.md)
cd frontend
npx playwright test tests/e2e/                                        # Full e2e suite (needs --profile llm for every spec to mean something)
npx playwright test tests/e2e/ --grep-invert "grounded in a document"  # Same subset CI runs — passes against the default (fake) profile
npx playwright test tests/e2e/knowledge-base-search-grounding.spec.ts  # The one real-content spec — needs --profile llm, or it fails for the wrong reason
npm run test:e2e:ui                                                    # Interactive UI mode
```

**CI coverage and its one exception.** `e2e-tests` in `.github/workflows/ci.yml` gates every PR, running the full stack (no LLM profile) against `LLM_PROVIDER=fake`. One spec, `knowledge-base-search-grounding.spec.ts`, is excluded there via `--grep-invert "grounded in a document"`: its whole purpose is proving a real LLM answer is grounded in a real retrieved document, and a full local model isn't viable in a GitHub-hosted runner (multi-GB download, CPU-only inference latency, and — confirmed by hand against the real 8B model — non-deterministic tool-use behavior that would make the check itself flaky rather than trustworthy). Weakening its assertion to pass against the fake provider would make it stop testing what it exists to test, so it's excluded instead, not gutted.

**Run it before merging any change that touches retrieval (chunking, embedding, hybrid search) or the chat agent's tool-calling**, with a real GGUF model in `./models/` (see `docs/LLM_SETUP.md`):
```bash
docker-compose up --profile llm
cd frontend
npx playwright test tests/e2e/knowledge-base-search-grounding.spec.ts
```
A tiny (sub-1B) model was considered to bring this spec into CI, but tool-calling reliability generally gets *worse*, not better, as models shrink — evaluating a specific small model for this is a deliberate follow-up, not a default to reach for.

### MCP doc-search server (Phase 3+)

- TDD pgvector query logic against test Postgres

### Infra (Helm/K3s) (Phase 5+)

- Write validation scripts before manifests (assertions about pod readiness, TLS cert validity, etcd encryption)
- CI runs infra tests against k3d

### CI Pipeline

GitHub Actions (see `.github/workflows/ci.yml`) runs on every PR:
- **Backend**: `pytest tests/unit/` + `ruff check` + `black --check` + `mypy app/` + `lint_time_injection.py`/`lint_edge_case_truthiness.py`/`lint_repositories.py`
- **doc-search**: `pytest tests/unit/` + `ruff check` + `black --check` + `mypy app/`
- **Frontend**: `npm test` + `npm run lint` + `npm run build`
- **Infra**: Helm chart lint + `pytest infra/tests/`
- **E2e**: the real stack (`docker-compose up`, fake LLM/embedding provider) + `npx playwright test tests/e2e/`, minus the one spec excluded per "End-to-End (E2E) Tests" above
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
- [ ] If this change is user-facing: an e2e spec exists or was updated, run against the real stack (see "End-to-End (E2E) Tests")

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
6. **Push and open a PR** — merge only once it meets the Definition of Done below

## Definition of Done — Merging to Master

**Feature branches are mandatory.** Nothing is committed directly to `master`. A branch is only mergeable once every item below is true — this list is the actual merge gate, not a suggestion, and it applies equally to a human contributor or an agent working autonomously. Don't merge (or advise merging) with any box unchecked.

- [ ] **All unit tests pass** — backend (`pytest tests/unit/`) and frontend (`npm test`), and green in CI on the PR itself, not just on a local machine. CI is the source of truth; "passed for me locally" is not sufficient if the PR's own pipeline run is red or hasn't run.
- [ ] **Lint, format, and type checks pass** — `ruff check .`, `black --check .`, `mypy app/` on the backend; `npm run lint` and a successful `npm run build` (TypeScript compilation) on the frontend. These are distinct gates from "tests pass" and must be checked explicitly, not assumed bundled into the test run.
- [ ] **An e2e test validates the functionality, run against the real dev stack** (`docker-compose up`, real Keycloak/backend/frontend, not mocks) — required for any user-facing change (new flow, changed behavior visible to a user). See "End-to-End (E2E) Tests" above for when this applies and how to write one. Internal refactors with no user-visible behavior change are exempt, but say so explicitly in the PR description rather than silently omitting the spec. CI's `e2e-tests` job runs this automatically on every PR (against `LLM_PROVIDER=fake`, per that section's "CI coverage and its one exception") — but for any change touching retrieval (chunking, embedding, hybrid search) or the chat agent's tool-calling, that alone is not enough: also run `docker-compose up --profile llm` and the real-content spec locally (see the E2E section's "Run it before merging..." block) before merging, and say in the PR description that you did. A green fake-provider CI run proves the plumbing didn't break; it cannot prove retrieval quality or grounding didn't regress — that gap is exactly why issue #7's retrieval changes had to be verified by hand against a real embedding server after CI alone couldn't settle the question.
- [ ] **The PR description states how this change is observable to the end user.** Every feature, fix, or behavior change has *some* user-facing effect — otherwise it did nothing worth shipping. That effect doesn't have to be a new screen or interaction: a bug fix might mean an error that used to fail silently now shows a message, a backend hardening change might mean a request that used to hang now returns a clear `429` with a `Retry-After`, a config change might mean a new field appears in the Settings UI. Name the specific user-visible signal (error message, banner, status code + body the frontend surfaces, log line an admin would see, or "none — purely internal, here's why") rather than describing only the internal mechanism. If the honest answer is "the user cannot tell this happened, ever, under any condition," treat that as a prompt to reconsider the change, not a box to check past — a silent success or a silently swallowed failure is usually a gap, not a feature. This is what caught rate limiting (#25) shipping a `429` response with no corresponding UI treatment, and should be the first thing that prevents a repeat.
- [ ] **A code review has been performed against clean code / clean architecture standards**, treating this repo as the reference implementation other forks will copy. Use the Code Review Checklist above as the concrete rubric (TDD & Testing, Readability & Maintainability, Design & Correctness, and For Bug Fixes where applicable). The bar is "would a maintainer forking this template hold this code up as the pattern to imitate" — not merely "does it work."
- [ ] **Branch is up to date with `master`** (rebased or merged) before the final CI run that gates merge, so the tests, lint, and review that approved the PR reflect the code as it will actually land — not a stale base that could hide a conflict-introduced regression.
- [ ] **Docs reflect the change.** If the change affects `CLAUDE.md`'s Current Status/Phase section, a guide in `docs/` (e.g. `DATABASE_MODELS.md`, `BACKEND_SERVICES.md`, `FRONTEND_ARCHITECTURE.md`, `REPOSITORY_PATTERN.md`, `SECURITY.md`), or introduces a new mandatory pattern, update the relevant doc in the same PR. If nothing needs updating, that's a conscious check, not a default assumption.
- [ ] **No unresolved scope creep**: the diff matches the stated phase/issue scope (see "Phase scope" under Key Constraints) — no unrelated refactors, features, or cleanups bundled in without being called out.

**Why this is a gate, not a checklist to skim:** this repository is a template other teams fork. Every merge to `master` is a pattern someone else will copy under time pressure without reading this file first. A shortcut here isn't scoped to this repo — it propagates.

## Detailed Implementation Guides

The patterns below are **mandatory shapes**, not suggestions — each has a canonical worked example in `docs/`. Before writing a new database model, service, frontend API integration, or repository, **read the matching guide and copy its shape**. Do not improvise a variant structure; a new file that "does its own thing" is an anti-pattern even if it works, because it breaks consistency for the next person (or agent) who has to extend it.

| If you are about to... | Read this first | Covers |
|---|---|---|
| Add or change a database table | [docs/DATABASE_MODELS.md](../docs/DATABASE_MODELS.md) | SQLAlchemy model shape, Alembic migration workflow, migration troubleshooting |
| Add backend business logic used by 2+ endpoints | [docs/BACKEND_SERVICES.md](../docs/BACKEND_SERVICES.md) | When to create a service, service module shape, refactoring endpoints to use it |
| Add or change a frontend API call | [docs/FRONTEND_ARCHITECTURE.md](../docs/FRONTEND_ARCHITECTURE.md) | API client → service → hook → component layering, full worked example, testing each layer |
| Add a new database query used by an endpoint | [docs/REPOSITORY_PATTERN.md](../docs/REPOSITORY_PATTERN.md) | Repository class shape, user-isolation and soft-delete query patterns |
| Write a time-dependent function | [docs/TIME_INJECTION.md](../docs/TIME_INJECTION.md) | Time injection pattern, pytest fixtures, testability without mocking |
| Add a second LangGraph agent alongside `chat_agent` | [docs/AGENT_LIBRARY.md](../docs/AGENT_LIBRARY.md) | Agent module/prompt module shape, factory signature, registry, no-premature-abstraction guidance |

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
