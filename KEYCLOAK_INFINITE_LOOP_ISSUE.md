# Keycloak Infinite Redirect Loop - Troubleshooting Guide

## Issue Summary

**Symptom:** When user navigates to `http://localhost:3000`, the page immediately gets caught in an infinite redirect loop to Keycloak with `error=login_required`.

**Current Behavior:**
```
User visits http://localhost:3000
  ↓
Page loads, AuthContext initializes
  ↓
kc.init() is called
  ↓
Keycloak redirects to http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?...
  ↓
Keycloak returns error=login_required
  ↓
Redirects back to http://localhost:3000/#error=login_required
  ↓
(repeat infinitely)
```

**Expected Behavior:**
```
User visits http://localhost:3000
  ↓
Page loads, shows "Login" button
  ↓
User clicks Login button
  ↓
Redirects to Keycloak login form
  ↓
User enters testuser/testpassword
  ↓
Keycloak redirects back with authorization code
  ↓
App exchanges code for token
  ↓
Show authenticated UI (chat)
```

## Attempted Fixes (Did Not Work)

1. Changed `onLoad: 'check-sso'` to `onLoad: 'none'` - **Still looping**
2. Removed `redirectUri` from `kc.init()` - **Still looping**
3. Added error detection for `error=login_required` in URL - **Still looping**
4. Added `checkLoginIframe: false` - **Still looping**
5. Added `pkceMethod: 'S256'` - **Still looping**

## Environment Details

**Services Running:**
- Keycloak: http://localhost:8080
- Backend: http://localhost:8001
- Frontend: http://localhost:3000
- All services confirmed running via: `docker-compose ps`

**Keycloak Configuration:**
- File: `infra/keycloak/realm-import.json`
- Realm: `eaistack`
- Client: `eaistack-web`
- Client Type: `publicClient: true`
- Redirect URIs: `["http://localhost:3000", "http://localhost:3000/"]`
- Test User: `testuser` / `testpassword`

**Frontend Code:**
- File: `frontend/src/context/AuthContext.tsx`
- Current init call:
```typescript
const authenticated = await kc.init({
  checkLoginIframe: false,
  onLoad: 'none',
  pkceMethod: 'S256',
})
```

## Diagnostic Steps to Perform

### 1. Check Keycloak Realm Configuration

```bash
# Verify realm exists
curl http://localhost:8080/realms/eaistack

# Should return JSON with realm details
# Look for: "realm": "eaistack"
```

### 2. Check Keycloak Client Configuration

```bash
# Check if realm-import.json was actually imported
# Go to http://localhost:8080/admin/master/console/
# Login as admin/admin
# Navigate to: eaistack realm → Clients → eaistack-web
# Check:
#   - Enabled: true
#   - Client Type: public
#   - Redirect URIs: includes http://localhost:3000/
#   - Web Origins: includes http://localhost:3000
```

### 3. Check Browser Network Tab

Open DevTools (F12) → Network tab, refresh page:

**Look for:**
- Initial request to `http://localhost:3000/` - should return HTML
- Check if page immediately redirects
- Follow redirect chain to see WHERE it's redirecting

**Expected first request:**
- GET http://localhost:3000/ → 200 (HTML page loads)
- Should NOT immediately redirect

**If it redirects immediately:**
- Check the redirect Location header
- Is it going to Keycloak?
- What parameters is it sending?

### 4. Check Browser Console

Open DevTools (F12) → Console tab:

**Look for logs starting with `[Auth]`:**
```
[Auth] Configured Keycloak URL: http://localhost:8080/
[Auth] Keycloak instance created
[Auth] Init complete, authenticated: false
```

**If you see redirect errors:**
```
[Auth] Detected login_required error - possible session issue
```

### 5. Check Keycloak Logs

```bash
docker-compose logs keycloak | grep -i "error\|login\|redirect" | tail -50
```

Look for:
- Any error messages about the client
- Redirect URI mismatch errors
- Session errors

### 6. Test Keycloak Directly

Try to get auth endpoint directly to see what Keycloak returns:

```bash
curl -i "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http://localhost:3000/&response_type=code&response_mode=query"
```

Should return a redirect (302) to login form or error message.

## Possible Root Causes

### Theory 1: Keycloak Client Not Properly Configured
- Redirect URIs don't match exactly what's being sent
- Client is disabled
- Client doesn't have proper flow enabled

**Test:** Go to Keycloak admin console and manually verify client config

### Theory 2: Realm Import Didn't Run Properly
- Keycloak container started but realm wasn't imported
- Docker volume not mounted correctly

**Test:**
```bash
docker exec eaistack-keycloak-1 /opt/keycloak/bin/kcadm.sh get realms
# Should list 'eaistack' realm
```

### Theory 3: Keycloak JS Client Has Bug with This Config
- Maybe need to use different initialization method
- Maybe keycloak-js library has incompatibility

**Test:** Check Keycloak JS client version in `frontend/package.json`
- Current: `"keycloak-js": "^22.0.0"`
- Try upgrading or downgrading if needed

### Theory 4: Frontend Code Issue
- AuthContext is being called multiple times
- init() is being called in a loop
- Some hook is re-running

**Test:** Add console.log at top of useEffect to see if it runs multiple times
```typescript
useEffect(() => {
  console.log('[Auth] useEffect running - init will be called')
  const initKeycloak = async () => {
    // ...
  }
  initKeycloak()
}, [])
```

If log appears multiple times = React StrictMode or dependency issue

### Theory 5: Docker Network Isolation
- Frontend can't actually reach Keycloak
- Keycloak returning error due to unreachable redirect_uri

**Test:**
```bash
docker exec eaistack-frontend-1 curl -i http://keycloak:8080/realms/eaistack
# Frontend container should be able to reach Keycloak at http://keycloak:8080
```

## Questions for Another Agent

When investigating, answer:

1. **What exact URL does the browser redirect to after the initial page load?**
   - Is it Keycloak auth endpoint?
   - What parameters are in the URL?

2. **What does Keycloak return?**
   - Is it a login form?
   - Is it an error?
   - What error message?

3. **Does the Keycloak admin console show the realm and client?**
   - Are redirect URIs configured?
   - Are they exact matches?

4. **How many times does `[Auth]` log appear in console?**
   - Once (correct)
   - Multiple times (infinite loop in React)

5. **What does `curl http://localhost:8080/realms/eaistack` return?**
   - Valid JSON? (realm is imported)
   - 404? (realm doesn't exist)

6. **Can you manually visit Keycloak login URL in browser?**
   ```
   http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http://localhost:3000/&response_type=code
   ```
   - Does it show login form?
   - Does it show error?

## Recent Changes Made

**TDD-Based Fixes Applied:**
1. Fixed JWT audience validation (accept both eaistack-web and eaistack-api)
2. Changed `onLoad: 'check-sso'` → `'none'`
3. Changed `keycloak.login()` to direct navigation
4. Added error detection for login_required
5. Added PKCE support
6. Upgraded Node to v20 in Dockerfile
7. Fixed docker-entrypoint.sh to use npx vite

**All still result in infinite loop on page load.**

## Files Modified

- `frontend/src/context/AuthContext.tsx` - Auth initialization and login logic
- `frontend/src/components/ChatWindow.tsx` - Chat UI (sends auth token)
- `frontend/src/api/agentsClient.ts` - API client with token in headers
- `frontend/vite.config.ts` - Proxy config to backend
- `frontend/docker-entrypoint.sh` - Env var generation
- `frontend/Dockerfile` - Node v20
- `docker-compose.yml` - Keycloak config and env vars
- `infra/keycloak/realm-import.json` - Keycloak realm and user setup

## Git Commits for Reference

Recent commits related to auth:
- `6f62a10` - Fix: Use onLoad='none' to prevent infinite redirect on page load
- `324f62f` - Fix: Replace keycloak.login() with direct Keycloak navigation
- `e197d39` - Fix: Infinite redirect loop in Keycloak auth with TDD approach
- `1721ca1` - Fix: Accept both eaistack-web and eaistack-api audiences in token validation
- `0b32700` - Fix Keycloak URL configuration for frontend

## What to Try Next

1. **Add extensive logging** to see where the redirect is actually happening
2. **Check Keycloak health** - maybe it's returning errors for all requests
3. **Try disabling the realm import** temporarily - see if default realm works
4. **Test with different Keycloak version** - current is 22.0.0
5. **Check Keycloak logs** for why it's rejecting the auth request
6. **Verify realm-import.json** is being mounted correctly in Docker
7. **Test Keycloak client config manually** in admin console - maybe realm-import isn't working

## Copy/Paste for Agent

> Hey, we have an infinite redirect loop on `http://localhost:3000`. Every time the page loads, Keycloak immediately redirects back with `error=login_required`. We need to figure out WHY Keycloak is rejecting the auth request.
>
> Start by:
> 1. Check if Keycloak realm and client are properly configured (admin console)
> 2. Check browser network tab to see exact redirects
> 3. Check Keycloak logs for error messages
> 4. Test manual auth URL in browser
>
> See KEYCLOAK_INFINITE_LOOP_ISSUE.md for full details and diagnostic steps.
