# Authentication Troubleshooting Guide

This guide explains the authentication flow and how to debug login/token issues.

## Authentication Flow

1. **Frontend Login (OIDC Code Flow)**
   - User clicks "Login" button
   - Browser redirects to Keycloak login page (`http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?...`)
   - User enters credentials (testuser / testpassword)
   - Keycloak validates credentials and redirects back with auth code
   - Frontend exchanges code for JWT token
   - Frontend stores JWT in Keycloak JS client

2. **Frontend Chat Request**
   - Frontend extracts JWT from Keycloak client
   - Frontend sends POST `/api/agents/chat` with `Authorization: Bearer <JWT>`
   - Frontend dev server proxies request to backend (`http://backend:8000`)

3. **Backend Token Validation**
   - Backend receives request with Bearer token
   - Backend fetches Keycloak realm public key
   - Backend validates JWT signature and claims
   - Backend extracts user info from token payload
   - Backend allows request if token is valid

## Common Issues

### Issue: After logout, clicking login doesn't require credentials

**Symptoms:**
- User logs in successfully
- User clicks logout
- Tokens are cleared from localStorage
- User clicks login again
- **Without** entering credentials, user is shown chat interface

**Root Cause:**
Keycloak's session cookie persists even after the logout endpoint is called. When the user clicks login again:
1. Frontend redirects to Keycloak with `prompt=login` parameter
2. Keycloak checks its session cookie
3. If valid and without `prompt=login`, Keycloak auto-generates auth code (skips login form)
4. Frontend exchanges code for token and shows chat
5. User never entered credentials

**Solution:**
This is expected behavior if the `prompt=login` parameter was not being sent. The fix is to ensure login includes `prompt=login`:

```typescript
const login = () => {
  const keycloakLoginUrl = new URL(`${baseUrl}/realms/eaistack/protocol/openid-connect/auth`)
  // ... other params ...
  keycloakLoginUrl.searchParams.set('prompt', 'login')  // ← CRITICAL
  window.location.href = keycloakLoginUrl.href
}
```

**What `prompt=login` does:**
- Tells Keycloak to ignore existing session cookies
- Forces login form display even if session exists
- Requires fresh authentication every time

**Verification in Browser:**
1. Open DevTools → Network tab
2. Click logout
3. Click login
4. Look for redirect to Keycloak
5. URL should contain `prompt=login`
6. Keycloak should show login form (not auto-login)

---

### Issue: Fresh instance shows "already logged in"

**Symptoms:**
- Fresh browser (no stored tokens)
- Navigate to app homepage
- User is shown chat interface (as if logged in)
- Try to send message → "No auth token" error

**Root Cause:**
Keycloak's SSO behavior: When `keycloak.init()` runs, it checks for a valid Keycloak session cookie from prior browser sessions. If found, Keycloak returns `authenticated=true` even though the app has no stored token.

**Solution:**
Make localStorage the authoritative source of truth for authentication, independent of Keycloak's session cookie:

```typescript
const kcAuthenticated = await kc.init({ ... })
const tokenFromStorage = localStorage.getItem('access_token')
const appAuthenticated = !!tokenFromStorage || (kcAuthenticated && kc.token)
setIsAuthenticated(appAuthenticated)
```

This ensures:
- If token in localStorage → authenticated
- OR if Keycloak says authenticated AND has token → authenticated
- Otherwise → not authenticated

**Result:**
- Fresh instances always show login page (no stored token)
- After logout, user sees login even if Keycloak session cookie exists

---

### Issue: "invalid_user_credentials" error during login

**Symptoms:**
- Keycloak logs show: `error=invalid_user_credentials`
- User cannot log in

**Causes:**
- Keycloak realm import didn't run (realm and user not created)
- Testuser credentials in realm-import.json don't match what Keycloak imported
- Keycloak pod crashed during startup

**Solutions:**

1. **Check Keycloak realm was imported**
   ```bash
   docker-compose logs keycloak | grep -i "import"
   ```
   Should see: `Added realm 'eaistack'`

2. **Verify testuser exists**
   - Go to http://localhost:8080/admin/master/console/
   - Login as admin/admin
   - Navigate to eaistack realm → Users
   - Should see "testuser"

3. **Reset realm (delete and reimport)**
   ```bash
   docker-compose down -v  # Remove volumes
   docker-compose up keycloak
   # Wait for startup
   ```

4. **Check realm-import.json syntax**
   - User credentials must have proper format
   - Run: `python -m json.tool infra/keycloak/realm-import.json` to validate

### Issue: "Token expired" or "Invalid token" on /api/agents/chat

**Symptoms:**
- Login works
- Chat request returns 401 Unauthorized
- Backend logs show: `Invalid token` or `Token expired`

**Causes:**
- JWT has expired (can happen if system time is wrong)
- Token validation is mocking verify_token (unit tests only)
- Keycloak realm public key fetch failed

**Solutions:**

1. **Check system time**
   ```bash
   date  # Should match NTP
   docker exec keycloak date
   ```

2. **Check if in unit test vs integration test**
   - Unit tests: `verify_token` is mocked (no real validation)
   - Integration tests: Real token validation against Keycloak
   - Run: `pytest tests/unit/test_agents_api.py -v` (should pass)

3. **Check backend can reach Keycloak**
   ```bash
   docker exec backend curl http://keycloak:8080/realms/eaistack
   ```

### Issue: Frontend can't reach backend API

**Symptoms:**
- Chat request fails with network error
- Browser console shows fetch errors

**Causes:**
- Vite proxy not configured correctly
- Backend dev server not running
- CORS issue

**Solutions:**

1. **Verify Vite proxy configuration** (`frontend/vite.config.ts`)
   ```typescript
   proxy: {
     '/api': {
       target: 'http://backend:8000',  // Service name in Docker
       changeOrigin: true,
     },
   }
   ```

2. **Check backend is running**
   ```bash
   docker-compose logs backend | tail
   ```

3. **Test API directly from backend container**
   ```bash
   docker exec backend curl -X POST http://localhost:8000/api/agents/chat
   # Should return 403 (missing auth header)
   ```

## Debugging Logout Issues

If logout isn't working (tokens not clearing, session not ending), use these diagnostic steps:

### Step 1: Check Browser Console
After clicking logout, open DevTools Console (F12 → Console) and verify logs:
```
[Auth] Logout called, keycloak: exists
[Auth] Logged out, tokens cleared
[Auth] Calling keycloak.logout() with redirectUri: http://localhost:3000/
```

**Check for:**
- ✅ "keycloak: exists" — keycloak instance available
- ✅ "Calling keycloak.logout()" — logout function executed
- ❌ "keycloak: null" — instance was null, logout didn't run

### Step 2: Check localStorage
After logout, localStorage should be empty:
```javascript
// In browser console:
localStorage.getItem('access_token')   // Should be null
localStorage.getItem('token_type')     // Should be null
localStorage.getItem('refresh_token')  // Should be null
```

### Step 3: Check Keycloak Session Cookie
After logout, the Keycloak session should be cleared:
```javascript
// In browser console:
document.cookie  // Should NOT contain "KEYCLOAK_SESSION"
```

If you still see `KEYCLOAK_SESSION`, the logout call didn't reach Keycloak's logout endpoint.

### Step 4: Watch Network Tab
1. Open Network tab (F12 → Network)
2. Click logout
3. Look for redirect requests (should see logout redirect)
4. After logout, click login
5. Should see redirect to Keycloak
6. Keycloak should show login form

### Step 5: Check Backend Logs
```bash
docker-compose logs backend | grep -i logout
```

---

## Testing

### Unit Tests (fast, mocked)
```bash
cd backend
pytest tests/unit/test_agents_api.py -v
```
Tests with mocked `verify_token` and `get_current_user`.

### Integration Tests (slow, real services)
```bash
# Make sure docker-compose is running
pytest tests/integration/test_keycloak_setup.py -v
```
Tests that validate Keycloak realm and token flow.

### Manual Testing

1. **Start the stack**
   ```bash
   docker-compose up
   ```

2. **In browser, go to http://localhost:3000**

3. **Click Login**
   - Should redirect to Keycloak
   - Login as testuser / testpassword

4. **After login, try chatting**
   - Open browser DevTools → Network tab
   - Verify request has `Authorization: Bearer <token>`
   - Verify response is 200 with chat response

5. **Check backend logs**
   ```bash
   docker-compose logs backend | grep -i "auth\|401\|error"
   ```

## Architecture Notes

- **Frontend → Backend**: Vite proxy (`/api` → `http://backend:8000`)
- **Backend → Keycloak**: JWKS endpoint for token validation
- **Token storage**: Keycloak JS client handles token internally
- **Token validation**: Backend validates with public key, no network needed after JWKS fetch
