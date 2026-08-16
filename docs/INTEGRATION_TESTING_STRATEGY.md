# Integration Testing Strategy

This document describes how to test the full auth flow end-to-end, including Keycloak login → JWT token → backend chat endpoint.

## Testing Pyramid

```
                    E2E Tests (Browser automation)
                   /                                 \
                 Manual Testing              Playwright/Puppeteer
               (QA, demos)                      (slow, expensive)
                   /                                 \
        Integration Tests (Real services, but mocked browser)
       /                                              \
  Backend integration tests              Frontend integration tests
  (test with real Keycloak,             (test API client with mocks)
   mocked browser)                       
       \                                              /
        \______________________________________ ______/
                                                /
                        Unit Tests (Fast, mocked)
                       /                        \
              Backend tests            Frontend component tests
            (all mocked, ~100ms)      (mocked API, ~50ms)
```

## Recommended Approach: Layered Testing

### Layer 1: Unit Tests (Fast, Always Run) ✅ **DONE**

**Backend:**
```bash
pytest tests/unit/ -v
```
- Mock Keycloak token validation
- Mock LLM responses
- Test auth logic with fake tokens
- ~200ms total

**Frontend:**
```bash
npm test
```
- Mock Keycloak client
- Mock API responses
- Test components and hooks
- ~300ms total

### Layer 2: Integration Tests (Medium, Run on CI)

**Backend Integration:**
```bash
pytest tests/integration/ -v
```
Requires: Real Keycloak + Postgres
- Test Keycloak realm setup
- Test user login flow
- Test token generation
- Test backend validation with real tokens
- ~5 seconds total

**Frontend Integration:**
```bash
npm run test:integration
```
Requires: Real backend API running
- Test API client with real backend
- Test auth context with mocked Keycloak
- Don't test login form (use mocked auth)
- ~2 seconds total

### Layer 3: E2E Tests (Slow, Run manually before release)

**Option A: Playwright (Recommended for most cases)**
```bash
npm run test:e2e
```
- Test full browser automation
- Requires: Keycloak, Backend, Frontend all running
- ~10-30 seconds per test
- Can test login form, redirects, cookies

**Option B: Puppeteer (More lightweight)**
```bash
npm run test:puppeteer
```
- Headless Chrome automation
- Similar to Playwright but lighter
- ~10-30 seconds per test

**Option C: Cypress (Good UI/visual testing)**
- Interactive test runner
- Good for debugging
- ~20-40 seconds per test

## Test Implementation Guide

### Unit Test Example (Already Done)

```python
# backend/tests/unit/test_agents_api.py
@pytest.mark.unit
def test_chat_endpoint_with_valid_auth(client, mock_keycloak_token):
    """Chat endpoint with mocked auth token."""
    fake_user = {
        "user_id": mock_keycloak_token["sub"],
        "username": mock_keycloak_token["preferred_username"],
    }
    
    def override_get_current_user():
        return fake_user
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    response = client.post(
        "/api/agents/chat",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer mocked-token"},
    )
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
```

**Pros:** Fast, isolated, doesn't need Keycloak
**Cons:** Doesn't test real token validation

### Integration Test Example (Backend)

```python
# backend/tests/integration/test_keycloak_setup.py
@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_testuser_can_login():
    """Real Keycloak login flow."""
    import httpx
    
    async with httpx.AsyncClient() as client:
        # Get real token from Keycloak
        response = await client.post(
            f"{settings.keycloak_url}/realms/eaistack/protocol/openid-connect/token",
            data={
                "client_id": "eaistack-api",
                "client_secret": "eaistack-api-secret",
                "grant_type": "password",
                "username": "testuser",
                "password": "testpassword",
            },
        )
        
        assert response.status_code == 200
        token = response.json()["access_token"]
```

**Pros:** Tests real Keycloak flow, real token format
**Cons:** Requires Keycloak running, slower (~2 seconds)

### Integration Test Example (Frontend API)

```typescript
// frontend/tests/integration/api.test.ts
import { describe, it, expect } from 'vitest'
import { sendChatMessage } from '../src/api/agentsClient'

describe('Chat API Integration', () => {
  it('should send chat message with auth token', async () => {
    const token = 'eyJhbGc...' // Real token or valid JWT mock
    
    try {
      const response = await sendChatMessage(
        'Hello',
        undefined,
        token,
      )
      
      expect(response.response).toBeDefined()
      expect(response.threadId).toBeDefined()
    } catch (err) {
      // Expected if backend not running
      expect(err.message).toContain('Failed')
    }
  })
})
```

**Pros:** Tests real API client, real network calls
**Cons:** Requires backend running, needs valid token

### E2E Test Example (Playwright - Recommended)

```typescript
// frontend/tests/e2e/login.spec.ts
import { test, expect } from '@playwright/test'

test('user can login and chat', async ({ page }) => {
  // Navigate to app
  await page.goto('http://localhost:3000')
  
  // Should see login button
  const loginBtn = page.locator('button:has-text("Login")')
  await expect(loginBtn).toBeVisible()
  
  // Click login - redirects to Keycloak
  await loginBtn.click()
  await page.waitForURL('**/auth/realms/**')
  
  // Fill login form
  await page.fill('input[name="username"]', 'testuser')
  await page.fill('input[name="password"]', 'testpassword')
  await page.click('button[type="submit"]')
  
  // Should redirect back to app
  await page.waitForURL('http://localhost:3000')
  
  // Should see chat window
  const chatInput = page.locator('input[placeholder="Type your message..."]')
  await expect(chatInput).toBeEnabled()
  
  // Send message
  await chatInput.fill('What is 2+2?')
  await page.click('button:has-text("Send")')
  
  // Should see response
  const response = page.locator('text=4')
  await expect(response).toBeVisible({ timeout: 5000 })
})
```

**Pros:** Tests complete real-world flow, catches UI bugs
**Cons:** Slowest, most fragile, requires all services running

## Setup Instructions

### For Playwright E2E Tests

1. **Install Playwright:**
   ```bash
   cd frontend
   npm install -D @playwright/test
   ```

2. **Create test config:**
   ```typescript
   // frontend/playwright.config.ts
   import { defineConfig, devices } from '@playwright/test'
   
   export default defineConfig({
     testDir: './tests/e2e',
     fullyParallel: true,
     forbidOnly: !!process.env.CI,
     retries: process.env.CI ? 2 : 0,
     workers: process.env.CI ? 1 : undefined,
     reporter: 'html',
     use: {
       baseURL: 'http://localhost:3000',
       trace: 'on-first-retry',
     },
     projects: [
       { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
     ],
     webServer: {
       command: 'npm run dev',
       url: 'http://localhost:3000',
       reuseExistingServer: !process.env.CI,
     },
   })
   ```

3. **Add npm script:**
   ```json
   {
     "scripts": {
       "test:e2e": "playwright test",
       "test:e2e:ui": "playwright test --ui"
     }
   }
   ```

4. **Run tests:**
   ```bash
   # Requires: docker-compose up
   npm run test:e2e
   
   # Interactive UI mode
   npm run test:e2e:ui
   ```

### For Puppeteer E2E Tests (Lighter Alternative)

```bash
npm install -D puppeteer
```

```typescript
// frontend/tests/e2e/login.puppeteer.ts
import puppeteer from 'puppeteer'

describe('Login Flow', () => {
  test('user can login', async () => {
    const browser = await puppeteer.launch()
    const page = await browser.newPage()
    
    try {
      await page.goto('http://localhost:3000')
      await page.click('button:contains("Login")')
      
      // Wait for Keycloak redirect
      await page.waitForNavigation()
      
      // Fill form
      await page.type('input[name="username"]', 'testuser')
      await page.type('input[name="password"]', 'testpassword')
      await page.click('button[type="submit"]')
      
      // Check we're back at app
      const url = page.url()
      expect(url).toContain('localhost:3000')
    } finally {
      await browser.close()
    }
  })
})
```

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Backend unit tests
        run: |
          cd backend
          pip install -e ".[dev]"
          pytest tests/unit/ -v
      
      - name: Frontend unit tests
        run: |
          cd frontend
          npm install
          npm test

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: eaistack
      
      keycloak:
        image: quay.io/keycloak/keycloak:22.0.0
        env:
          KEYCLOAK_ADMIN: admin
          KEYCLOAK_ADMIN_PASSWORD: admin
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Backend integration tests
        run: |
          cd backend
          pip install -e ".[dev]"
          pytest tests/integration/ -v
      
      - name: Frontend integration tests
        run: |
          cd frontend
          npm install
          npm run test:integration

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Start services
        run: docker-compose up -d
      
      - name: Wait for services
        run: |
          timeout 60 bash -c 'until curl -f http://localhost:8080/realms/eaistack; do sleep 1; done'
      
      - name: Run E2E tests
        run: |
          cd frontend
          npm install
          npm run test:e2e
      
      - name: Stop services
        run: docker-compose down
      
      - name: Upload traces
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: frontend/playwright-report/
```

## Testing Decision Tree

```
Need to test...
│
├─ Token validation logic → Unit tests (mock token)
├─ Keycloak realm setup → Integration tests (real Keycloak)
├─ API client (sendChatMessage) → Integration tests (mock backend)
├─ Chat component → Unit tests (mock API)
├─ Login flow → E2E tests (browser automation)
└─ Full auth flow → E2E tests (browser automation)
```

## Running Tests Locally

### Quick Sanity Check (10 seconds)
```bash
# Backend
cd backend && pytest tests/unit/ -v

# Frontend
cd frontend && npm test
```

### Full Integration (30 seconds)
```bash
# Start services
docker-compose up -d

# Backend
cd backend && pytest tests/integration/ -v

# Frontend
cd frontend && npm run test:integration
```

### Full E2E (60+ seconds)
```bash
# Start services
docker-compose up -d

# Wait for Keycloak
sleep 10

# Run E2E tests
cd frontend && npm run test:e2e

# Cleanup
docker-compose down
```

## When to Use Each Test Type

| Test Type | Speed | Flakiness | Coverage | When to Use |
|-----------|-------|-----------|----------|------------|
| Unit | <100ms | Very low | Code paths | Always, on every commit |
| Integration | 1-5s | Low | API contracts | Before merge, in CI |
| E2E | 10-30s | Medium | Real flows | Before release, on main |

## Best Practices

1. **Unit tests** should cover:
   - All error cases
   - Token validation logic
   - Auth dependency injection
   - API client error handling

2. **Integration tests** should cover:
   - Keycloak realm setup
   - Real token generation
   - Backend token validation
   - API client with real backend

3. **E2E tests** should cover:
   - Complete login flow
   - Chat message flow
   - Error states (wrong password, expired token)
   - Redirect after login

4. **Avoid in E2E tests:**
   - Testing every edge case (use unit tests)
   - Testing implementation details
   - Hard-coded waits (use `waitForNavigation`, `waitForURL`)
   - Overlapping tests (use integration tests instead)

## Debugging Failed Tests

### Backend Integration Test Fails
```bash
# Check if Keycloak is running
docker-compose logs keycloak | tail -50

# Check realm was imported
curl http://localhost:8080/realms/eaistack

# Check test user exists
docker exec keycloak /opt/keycloak/bin/kcadm.sh get users
```

### Frontend E2E Test Fails
```bash
# Check if services are running
docker-compose ps

# Run with headed browser
npx playwright test --headed

# Run single test with trace
npx playwright test login.spec.ts --trace on

# View trace
npx playwright show-trace trace.zip
```

## Summary

- **Use unit tests for fast feedback** on auth logic
- **Use integration tests for contract validation** between services
- **Use E2E tests sparingly** for critical user flows
- **Don't test implementation details** with E2E (use unit/integration)
- **Mock external dependencies** at lower levels (Keycloak, LLM)
- **Real services** only at integration and E2E level
