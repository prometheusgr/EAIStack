# Logout & Keycloak Session Diagnostics

## Issue Report

**User Experience**: After logout, clicking login takes user straight to chat without requiring credentials.

**Root Cause**: Keycloak session cookie is still valid after logout, so when user clicks login:
1. App redirects to Keycloak
2. Keycloak checks session cookie (still valid)
3. Keycloak returns auth code without showing login form
4. App exchanges code for token and shows chat
5. User never entered credentials

## How Keycloak Authentication Works

### Login Flow
```
User clicks "Login"
    ↓
App redirects to Keycloak login
    ↓
Keycloak shows login form
    ↓
User enters credentials
    ↓
Keycloak validates and creates session cookie
    ↓
Keycloak redirects back with authorization code
    ↓
App exchanges code for token
    ↓
User sees chat
```

### Logout Flow (CORRECT)
```
User clicks "Logout"
    ↓
App clears localStorage tokens
    ↓
App resets auth state
    ↓
App calls keycloak.logout() with redirectUri
    ↓
Keycloak invalidates session cookie
    ↓
Keycloak redirects to home page
    ↓
User sees login page
    ↓
User clicks "Login" again
    ↓
Keycloak has NO valid session
    ↓
Keycloak shows login form
    ↓
User enters credentials (required)
```

### Logout Flow (BUGGY)
```
User clicks "Logout"
    ↓
App clears localStorage tokens
    ↓
App resets auth state
    ↓
App does NOT call keycloak.logout() ← BUG
    ↓
Keycloak session cookie STILL VALID
    ↓
User sees login page (but session active)
    ↓
User clicks "Login" again
    ↓
Keycloak HAS valid session
    ↓
Keycloak skips login form
    ↓
Keycloak returns auth code
    ↓
User sees chat WITHOUT entering credentials ← BUG
```

## Current Implementation Check

### What the code does:

In `frontend/src/context/AuthContext.tsx`, the `logout()` function:

```typescript
const logout = () => {
  // Step 1: Clear tokens
  localStorage.removeItem('access_token')
  localStorage.removeItem('token_type')
  localStorage.removeItem('refresh_token')

  // Step 2: Reset state
  setIsAuthenticated(false)
  setUser(null)
  setKeycloak(null)

  // Step 3: Clear Keycloak session
  if (keycloak) {
    keycloak.logout({ redirectUri: `${window.location.origin}/` })
  }
}
```

**Issue**: This SHOULD work correctly if:
1. `keycloak` instance exists when logout is called
2. `keycloak.logout()` properly redirects to Keycloak logout endpoint
3. The redirect completes before user clicks login again

## Diagnostic Steps

### 1. Check Browser DevTools

**Open Console (F12 → Console tab)**

After clicking logout, you should see:
```
[Auth] Logout called, keycloak: exists
[Auth] Logged out, tokens cleared
[Auth] Calling keycloak.logout() with redirectUri: http://localhost:3000/
```

**Check for**:
- ✅ "keycloak: exists" - keycloak instance available
- ✅ "Calling keycloak.logout()" - logout was called
- ❌ "keycloak: null" - instance was null, logout not called

### 2. Check localStorage

After logout, localStorage should be empty:
```javascript
// In console:
localStorage.getItem('access_token')  // Should be null
localStorage.getItem('token_type')    // Should be null
localStorage.getItem('refresh_token') // Should be null
```

### 3. Check Keycloak Session Cookie

After logout, Keycloak session cookie should be gone:
```javascript
// In console:
document.cookie  // Should NOT contain "KEYCLOAK_SESSION"
```

If you still see `KEYCLOAK_SESSION` cookie, logout didn't clear Keycloak session.

### 4. Watch Network Tab

**Open Network tab (F12 → Network)**

When you click logout:
1. Look for request to `/api/agents/...` - should NOT appear after logout
2. Look for redirects to `localhost:3000` - logout redirect
3. After logout, click login
4. Look for redirect to Keycloak
5. Should see Keycloak login form in browser

### 5. Backend Logs

Check backend logs (if applicable) - should show:
- Logout doesn't require backend API call
- But check if any auth endpoints are being hit unexpectedly

## Potential Fixes

### Fix 1: Ensure keycloak.logout() is called

**Current code does this - verify it's actually executing:**

```typescript
const logout = () => {
  console.log('[Auth] Logout: keycloak exists?', !!keycloak)
  
  localStorage.removeItem('access_token')
  setIsAuthenticated(false)
  
  if (keycloak) {
    console.log('[Auth] Calling keycloak.logout()')
    keycloak.logout({ redirectUri: `${window.location.origin}/` })
  } else {
    console.warn('[Auth] Keycloak instance not available!')
  }
}
```

### Fix 2: Ensure redirectUri is valid

The redirectUri must be in Keycloak client's `webOrigins` and `redirectUris`:

In `infra/keycloak/realm-import.json`:
```json
{
  "clientId": "eaistack-web",
  "redirectUris": [
    "http://localhost:3000",
    "http://localhost:3000/",
    "http://localhost:3000/*"
  ],
  "webOrigins": [
    "http://localhost:3000",
    "http://localhost:3000/"
  ]
}
```

Verify this includes `http://localhost:3000/`

### Fix 3: Handle async logout

If keycloak.logout() is async, ensure it completes:

```typescript
const logout = () => {
  localStorage.removeItem('access_token')
  setIsAuthenticated(false)
  
  if (keycloak && keycloak.logout) {
    // keycloak.logout() may redirect browser immediately
    // or return a promise
    try {
      const result = keycloak.logout({ redirectUri: `${window.location.origin}/` })
      // If it returns a promise, could await it
      if (result && typeof result.then === 'function') {
        console.log('[Auth] Logout is async')
      }
    } catch (err) {
      console.error('[Auth] Logout error:', err)
    }
  }
}
```

## Expected Behavior After Fix

### After clicking logout:
1. ✅ localStorage tokens cleared
2. ✅ Console shows `keycloak.logout()` called
3. ✅ Browser stays on login page (or redirects to home)
4. ✅ Keycloak session cookie cleared

### After clicking login again:
1. ✅ Redirects to Keycloak
2. ✅ Keycloak shows login form (NOT auto-login)
3. ✅ User must enter credentials
4. ✅ After credentials, shown chat

## Testing

Run diagnostics tests:
```bash
npm test -- logout-keycloak-session.test.ts --run
npm test -- logout-must-clear-session.test.ts --run
```

All tests pass, confirming logic is correct. If runtime behavior differs:
1. Check console logs during actual logout
2. Check if Keycloak instance is available
3. Verify redirectUri is configured in Keycloak
4. Check if keycloak.logout() is being called

## Keycloak Logout Endpoint

Keycloak logout URL:
```
http://localhost:8080/realms/eaistack/protocol/openid-connect/logout?redirect_uri=http://localhost:3000/
```

When logout is called, browser should redirect to this URL, which:
1. Invalidates session cookie
2. Clears server-side session
3. Redirects back to `redirect_uri`

## References

- Keycloak JavaScript Adapter: https://www.keycloak.org/docs/latest/securing_apps/#javascript-adapter
- Keycloak Logout: https://www.keycloak.org/docs/latest/securing_apps/#_logout
- OAuth2 Session Invalidation: https://tools.ietf.org/html/rfc6749#section-3.2.1

