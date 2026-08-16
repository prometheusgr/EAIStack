# Testing Quick Start Guide

## The Three Layers

### 1. Unit Tests (Fast - Run Every Commit) ⚡

```bash
# Backend unit tests (~200ms)
cd backend
pytest tests/unit/ -v

# Frontend unit tests (~300ms)
cd frontend
npm test
```

**What they test:**
- Auth logic with mocked Keycloak
- API client with mocked responses
- Component behavior with mocked data

**Why use them:**
- Fast feedback
- No external services needed
- Test error cases easily

### 2. Integration Tests (Medium - Run Before Merge) 🔌

```bash
# Start services first
docker-compose up -d

# Backend integration tests (~5s)
cd backend
pytest tests/integration/ -v

# Frontend integration tests (~2s)
cd frontend
npm run test:integration
```

**What they test:**
- Real Keycloak realm and token generation
- Backend token validation with real tokens
- API client with real backend

**Why use them:**
- Validates contracts between services
- Tests real JWT flow
- Catches integration issues

### 3. E2E Tests (Slow - Run Before Release) 🎬

```bash
# Start services first
docker-compose up -d

# Install Playwright (one time)
npm install -D @playwright/test

# Run E2E tests (~30s)
cd frontend
npm run test:e2e

# Interactive UI mode for debugging
npm run test:e2e:ui
```

**What they test:**
- Complete browser-based login flow
- User interactions and redirects
- Full chat message flow
- Error states

**Why use them:**
- Tests real-world user experience
- Catches UI/navigation bugs
- Validates Keycloak redirects and cookies

## Testing Strategy (Recommended)

```
Local Development
├─ Run unit tests on every save (auto with vitest --watch)
└─ Run integration tests before committing

CI/CD (GitHub Actions)
├─ Run unit tests (fast feedback)
├─ Run integration tests (validates contracts)
└─ Run E2E tests on main/release branches (slow, run selectively)

Before Release
├─ All tests pass
├─ E2E tests pass
└─ Manual QA testing
```

## Quick Commands

### Development Loop

```bash
# Terminal 1: Start services
docker-compose up

# Terminal 2: Backend unit tests (watch mode)
cd backend && pytest tests/unit/ -v --lf  # --lf = last failed

# Terminal 3: Frontend unit tests (watch mode)
cd frontend && npm test -- --watch
```

### Before Commit

```bash
# Run all unit tests
cd backend && pytest tests/unit/ -v
cd frontend && npm test

# If you changed auth logic:
cd backend && pytest tests/integration/test_keycloak_setup.py -v
```

### Before Merge

```bash
# Run everything
docker-compose up -d
cd backend && pytest tests/integration/ -v
cd frontend && npm run test:integration

# Optional: Run E2E tests
cd frontend && npm run test:e2e
```

### Before Release

```bash
# Full test suite
docker-compose up -d

# Wait for services
sleep 10

# Run all tests
cd backend && pytest tests/ -v
cd frontend && npm test && npm run test:e2e

# Cleanup
docker-compose down
```

## Understanding Test Results

### Unit Test Failure Example

```
FAILED backend/tests/unit/test_auth.py::test_extract_user_from_payload_missing_sub
AssertionError: Should raise 401
```

**What to do:**
1. Check the test - what was it expecting?
2. Check the code - did you change auth logic?
3. If test is wrong, update it
4. If code is wrong, fix it

### Integration Test Failure Example

```
FAILED backend/tests/integration/test_keycloak_setup.py::test_keycloak_testuser_can_login
Error: Failed to obtain token: 401 invalid_user_credentials
```

**What to do:**
1. Check Keycloak is running: `docker-compose logs keycloak | tail`
2. Check realm was imported: `curl http://localhost:8080/realms/eaistack`
3. Check credentials: realm-import.json has `testuser`/`testpassword`
4. If needed, restart: `docker-compose down -v && docker-compose up`

### E2E Test Failure Example

```
E2E Test Failed: user can login and access chat
timeout 10000ms exceeded

Wait for "button:has-text("Send")" exceeded timeout
```

**What to do:**
1. Check frontend loaded: `curl http://localhost:3000`
2. Check backend running: `curl http://localhost:8001/health`
3. Run with UI mode: `npm run test:e2e:ui` to see what's happening
4. Check browser console in test UI for JavaScript errors

## Test Structure

```
tests/
├── unit/                           # Fast, mocked (always run)
│   ├── test_auth.py                # Token validation logic
│   ├── test_agents_api.py          # Chat endpoint with mocked auth
│   └── test_chat_agent.py          # LangGraph agent logic
│
├── integration/                    # Medium, real services (before merge)
│   ├── test_keycloak_setup.py      # Realm, user, token generation
│   ├── test_auth_flow.py           # Health checks
│   └── test_chat_auth_flow.py      # Full API flow
│
└── e2e/ (frontend)                 # Slow, browser automation (before release)
    ├── auth.spec.ts                # Login/logout/chat flow
    ├── global-setup.ts             # Pre-test health checks
    └── playwright.config.ts        # Configuration
```

## When Each Test Type Catches Issues

| Issue | Unit | Integration | E2E |
|-------|------|-------------|-----|
| JWT audience validation | ✅ | ✅ | ✅ |
| Keycloak realm not imported | ❌ | ✅ | ✅ |
| Token expired | ✅ | ✅ | ❌* |
| Login redirect URL wrong | ❌ | ❌ | ✅ |
| Chat API returns error | ✅ | ✅ | ✅ |
| Frontend loses token on refresh | ❌ | ❌ | ✅ |
| Keycloak cookie not set | ❌ | ❌ | ✅ |

*E2E doesn't test token expiration because tests run quickly

## Debugging Failed E2E Tests

### Interactive Mode (Best for Debugging)

```bash
npm run test:e2e:ui
```

This opens a browser and test runner side-by-side so you can:
- Watch the test run step-by-step
- Inspect elements
- Check console for JavaScript errors
- Pause/resume tests

### Debug Mode (Step Through Code)

```bash
npm run test:e2e:debug
```

Opens inspector for debugging JavaScript in tests.

### View Test Report

```bash
# After tests run, open HTML report
npx playwright show-report
```

Shows:
- Screenshots of each test step
- Video of test execution
- Traces of network calls
- Console logs

### Check Service Health

```bash
# Terminal to check services while test runs
docker-compose logs -f

# Another terminal to manually test flow
curl http://localhost:8080/realms/eaistack
curl http://localhost:8001/health
curl http://localhost:3000
```

## CI/CD Integration

See [CI/CD workflow example in INTEGRATION_TESTING_STRATEGY.md](./INTEGRATION_TESTING_STRATEGY.md#github-actions-example)

Key points:
- Unit tests run on every commit (fast feedback)
- Integration tests run on PR (validate contracts)
- E2E tests run on main/release (slow, selective)
- Tests in CI have strict timeouts and retries

## Tips & Tricks

### Running Specific Tests

```bash
# Backend: single test
pytest tests/unit/test_auth.py::test_verify_token_accepts_web_client_audience -v

# Frontend: single test file
npm test -- auth.test.ts

# E2E: single test
npx playwright test auth.spec.ts
```

### Running Only Failed Tests

```bash
# Backend: rerun last failed
pytest tests/unit/ -v --lf

# Frontend: only failed tests
npm test -- --failed-only
```

### Increasing Timeouts for Slow CI

```bash
# E2E with longer timeouts
npx playwright test --timeout=60000  # 60 seconds per test
```

### Collecting Test Coverage

```bash
# Backend coverage
pytest tests/unit/ --cov=app --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Troubleshooting

### Tests Can't Find Services

```bash
# Make sure docker-compose is running
docker-compose ps

# If containers aren't running
docker-compose up -d

# Check service health
curl http://localhost:8080/health  # Keycloak
curl http://localhost:8001/health  # Backend
curl http://localhost:3000          # Frontend
```

### Tests Pass Locally But Fail in CI

Common causes:
1. **Timing issues** - add explicit waits instead of sleeps
2. **Port conflicts** - CI services might use different ports
3. **Database state** - integration tests might need cleanup
4. **Browser differences** - test in Chrome/Chromium like CI does

### Flaky E2E Tests

Signs:
- Test passes/fails randomly
- Timing-related failures
- "Element not found" errors

Fixes:
1. Use explicit waits: `page.waitForURL()` not `sleep()`
2. Use proper locators: `page.locator()` not `page.querySelector()`
3. Increase timeouts: `{ timeout: 10000 }`
4. Run test multiple times: `npm run test:e2e -- --repeat-each=3`

## Summary

```
┌─ Unit Tests ─────────────────────┐
│ Fast, mocked, run every commit   │
│ pytest / npm test                │
└─────────────────────────────────┘
                ↓
┌─ Integration Tests ──────────────┐
│ Real services, before merge      │
│ pytest tests/integration/        │
└─────────────────────────────────┘
                ↓
┌─ E2E Tests ──────────────────────┐
│ Browser automation, before ship  │
│ npm run test:e2e                 │
└─────────────────────────────────┘
```

Each layer catches different issues.
Use all three for confident releases! 🚀
