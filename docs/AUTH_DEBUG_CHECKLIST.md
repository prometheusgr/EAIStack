# Auth Flow Debug Checklist

When you encounter 401 Unauthorized on `/api/agents/chat`, use this checklist to isolate the problem.

## Quick Diagnosis

1. **Can you log in?** (Does Keycloak form appear and accept testuser/testpassword?)
   - YES → Go to Step 2
   - NO → See "Keycloak Login Fails" below

2. **After login, does the chat input become enabled?**
   - YES → Go to Step 3
   - NO → Token isn't being retrieved after login

3. **Does the error appear immediately when you send a message?**
   - YES → Backend is rejecting the token immediately
   - NO → Check if request is even reaching backend

## Debug Steps

### Step 1: Check Browser Console

Open DevTools (F12) → Console tab and look for:

```
[Auth] Initialized with user: testuser
```

If you see this: Frontend successfully authenticated
If NOT: Keycloak init failed or session lost

Also check for chat logging:
```
[Chat] Sending message with token: eyJhbGc...
[agentsClient] Sending request to /api/agents/chat
[agentsClient] Response status: 401
```

### Step 2: Check Browser Network Tab

Go to Network tab, send a message, and inspect the `/api/agents/chat` request:

**Headers → Request Headers:**
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Content-Type: application/json
```

If Authorization header is missing → Issue in ChatWindow.tsx token handling
If Authorization header is present → Issue in backend token validation

### Step 3: Test Keycloak Directly

**Option A: Test user exists**
```bash
# From host machine
curl -s http://localhost:8080/realms/eaistack | jq .
# Should return realm details with 200
```

**Option B: Get a token directly**
```bash
# This simulates what the frontend should be doing
curl -X POST http://localhost:8080/realms/eaistack/protocol/openid-connect/token \
  -d "client_id=eaistack-web&grant_type=authorization_code&..." \
  ...
# (This is complex; the frontend's JavaScript client handles it)
```

### Step 4: Test Backend Token Validation

**Option A: With mocked auth (quick)**
```bash
# This bypasses Keycloak and uses fake user
curl -X POST http://localhost:8001/api/agents/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-token" \
  -d '{"message":"hello"}'
# Response should be 200 if unit tests pass
```

**Option B: With real Keycloak (slow)**
```bash
# This requires a real Keycloak token
# Get a token manually, then test backend validation
TOKEN=$(curl ... keycloak-token-request)
curl -X POST http://localhost:8001/api/agents/chat \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"hello"}'
```

### Step 5: Check Backend Logs

```bash
docker-compose logs backend | grep -i "token\|401\|auth\|keycloak" | tail -50
```

Look for any of these messages:
- `Token verification error:` → Exception in verify_token
- `Invalid audience:` → Token has wrong audience claim
- `Key not found` → Kid mismatch between token and JWKS
- `Keycloak public key` → Whether it's trying to fetch JWKS

### Step 6: Test with Debug Endpoint

Once you can log in, try calling the debug endpoint:

```bash
# In browser console, after login:
fetch('/api/auth/me', {
  headers: {
    'Authorization': `Bearer ${keycloak.token}`
  }
}).then(r => r.json()).then(console.log)
```

Or:
```bash
# From terminal - this shows what the backend sees
curl -X GET http://localhost:8001/debug/token \
  -H "Authorization: Bearer <your-token-here>"
```

If this works: Backend can validate tokens properly
If this fails: Issue in verify_token or token format

## Common Issues & Fixes

### Issue: "Token missing key ID"

**Cause:** Token doesn't have a `kid` (key ID) in JWT header
**Fix:** Verify Keycloak is issuing proper RS256 tokens
**Check:** Look at the base-64 decoded token header

### Issue: "Key not found"

**Cause:** Backend's JWKS doesn't have key matching token's `kid`
**Fix:** Keycloak JWKS might not have been fetched correctly
**Check:** `docker-compose logs keycloak | grep -i key`

### Issue: "Invalid audience" or just "401 Unauthorized"

**Cause:** Token audience doesn't match expected value
**Expected:** Token has `aud: "eaistack-web"` and backend allows both "eaistack-web" and "eaistack-api"
**Fix:** Verify in `backend/app/core/auth.py` line 57-59 both audiences are listed
**Check:** Decode token: `jq -R 'split(".")[1] | @base64d' <<<'<token>'`

### Issue: Refresh loses authentication

**Cause:** Session/token not persisted properly
**Fix:** Keycloak JavaScript client should store token in localStorage
**Check:** Browser DevTools → Application → Local Storage → look for keycloak-related keys

## Debugging Logs

### Frontend Logs

Enable in `frontend/src/context/AuthContext.tsx`:
```typescript
console.log('[Auth] ...') // At key points
console.log('[Chat] ...')  // In ChatWindow
```

### Backend Logs

Already enabled - look for patterns:
```
[INFO] Token verified for user: testuser, audience: eaistack-web
[WARNING] Audience validation failed
[ERROR] Token verification error: InvalidTokenError
```

## Full Token Inspection

To decode and inspect a JWT:

1. Get the token from browser console:
   ```javascript
   console.log(keycloak.token)
   ```

2. Paste at [jwt.io](https://jwt.io) to see:
   - Header: alg, kid, typ
   - Payload: sub, aud, iat, exp, preferred_username, email
   - Signature: RS256 signature

3. Verify:
   - `aud` should be "eaistack-web"
   - `exp` should be in future (not expired)
   - `iat` should be recent

## CI/CD: TDD Validation

Run unit tests (these should always pass):
```bash
cd backend
pytest tests/unit/test_agents_api.py -v
pytest tests/unit/test_auth.py -v
```

Run integration tests (these require Keycloak):
```bash
# Make sure docker-compose is running
pytest tests/integration/test_keycloak_setup.py -v
pytest tests/integration/test_chat_auth_flow.py -v
```

## Next Steps

If you're still stuck after this checklist:
1. Post the **exact** error message from backend logs
2. Share token from browser console (paste at jwt.io, share the header/payload claims)
3. Confirm Keycloak realm is accessible: `curl http://localhost:8080/realms/eaistack`
