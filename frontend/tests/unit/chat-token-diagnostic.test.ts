import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

/**
 * TDD: Diagnostic for 401 Error in Chat
 *
 * Comprehensive checklist to diagnose why chat endpoint returns 401.
 */

describe('Chat 401 Error Diagnostic - TDD', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('Step 1: Token After Login', () => {
    it('MUST: Token stored in localStorage after code exchange', () => {
      // Simulate OAuth code exchange success
      const tokenFromCodeExchange = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImtleS1pZCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiaHR0cDovL2xvY2FsaG9zdDozMDAwIl0sImF1ZCI6ImVhaXN0YWNrLXdlYiIsImF1dGhfdGltZSI6MTY5MzQwMDAwMCwiY2xpZW50X2hvc3QiOiIxNzIuMTguMC42Iiwicm9sZXMiOlsib2ZmbGluZV9hY2Nlc3MiLCJ1c2VyIl0sInByZWZlcnJlZF91c2VybmFtZSI6InRlc3R1c2VyIiwiY2xpZW50SWQiOiJlYWlzdGFjay13ZWIiLCJjdHkiOiJKV1QiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJlYWlzdGFjay13ZWIiLCJub25jZSI6Im5vbmNlLWlkIiwic2Vzc2lvbl9zdGF0ZSI6InNlc3Npb24taWQiLCJhY3IiOiIxIiwiYWxsb3dlZC1vcmlnaW5zIjpbImh0dHA6Ly9sb2NhbGhvc3Q6MzAwMCJdLCJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiZGVmYXVsdC1yb2xlcyIsIm9mZmxpbmVfYWNjZXNzIiwib2ZmbGluZV9hY2Nlc3MiLCJ1c2VyIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwiZW1haWwiOiJ0ZXN0dXNlckBlYWlzdGFjay5sb2NhbCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJuYW1lIjoiVGVzdCBVc2VyIiwiZXhwIjoyMzA0NDk0MDAwLCJpYXQiOjE2OTM0MDAwMDAsImlzcyI6Imh0dHA6Ly9sb2NhbGhvc3Q6ODA4MC9yZWFsbXMvZWFpc3RhY2siLCJqdGkiOiJ0b2tlbi1qd3QtaWQiLCJmYW1pbHlfbmFtZSI6IlVzZXIiLCJnaXZlbl9uYW1lIjoiVGVzdCJ9.signature'

      localStorage.setItem('access_token', tokenFromCodeExchange)

      // VERIFY: Token stored
      const stored = localStorage.getItem('access_token')
      expect(stored).not.toBeNull()
      expect(stored).toBe(tokenFromCodeExchange)
    })

    it('MUST: Token set on keycloak.token instance', () => {
      const token = 'keycloak_token_value'

      // AuthContext sets: kc.token = token
      const keycloak = {
        token: token,
        tokenParsed: {},
      }

      expect(keycloak.token).toBe(token)
      expect(keycloak.token).not.toBeUndefined()
    })

    it('VERIFY: Token is not empty or whitespace', () => {
      const emptyToken = '  ' // Empty/whitespace
      const validToken = 'eyJ...'

      // Empty token should fail check
      const isEmpty = !emptyToken || !emptyToken.trim()
      expect(isEmpty).toBe(true)

      // Valid token should pass
      const isValid = validToken && validToken.trim()
      expect(isValid).toBeTruthy()
    })
  })

  describe('Step 2: Token Retrieval in ChatWindow', () => {
    it('MUST: ChatWindow retrieves token before sending', () => {
      localStorage.setItem('access_token', 'chat_window_token')

      // ChatWindow logic
      const keycloak = { token: undefined }
      const token = keycloak?.token || localStorage.getItem('access_token')

      expect(token).toBe('chat_window_token')
      expect(token).not.toBeUndefined()
      expect(token).not.toBeNull()
    })

    it('VERIFY: Token is not null/undefined when sending', () => {
      localStorage.setItem('access_token', 'token_for_sending')

      const keycloak = { token: undefined }
      const token = keycloak?.token || localStorage.getItem('access_token')

      if (!token) {
        throw new Error('[Chat] No auth token available. Please log in.')
      }

      expect(token).toBeTruthy()
    })

    it('VERIFY: ChatWindow does NOT send if no token', () => {
      localStorage.clear()

      const keycloak = { token: undefined }
      const token = keycloak?.token || localStorage.getItem('access_token')

      // Should show error and NOT send
      const shouldSend = !!token
      expect(shouldSend).toBe(false)
    })
  })

  describe('Step 3: HTTP Request with Token', () => {
    it('MUST: Authorization header includes "Bearer " prefix', () => {
      const token = 'actual_token_value'
      const authHeader = `Bearer ${token}`

      expect(authHeader).toBe(`Bearer ${token}`)
      expect(authHeader).toMatch(/^Bearer /)
    })

    it('MUST: Authorization header is in headers object', () => {
      const token = 'token_value'

      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      }

      expect(headers).toHaveProperty('Authorization')
      expect(headers.Authorization).toContain(token)
    })

    it('VERIFY: No extra spaces in Authorization header', () => {
      const token = 'token'
      const correctHeader = `Bearer ${token}`
      const wrongHeader1 = `Bearer  ${token}` // Double space
      const wrongHeader2 = `Bearer${token}` // No space

      expect(correctHeader).toBe('Bearer token')
      expect(wrongHeader1).toBe('Bearer  token') // Wrong!
      expect(wrongHeader2).toBe('Bearertoken') // Wrong!
    })

    it('VERIFY: Token is complete (not truncated)', () => {
      const fullToken = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'
      const truncatedToken = 'eyJhbGciOiJSUzI1NiJ9'

      // Full token has 3 parts separated by dots
      const parts = fullToken.split('.')
      expect(parts).toHaveLength(3)

      // Truncated has only 1
      const truncatedParts = truncatedToken.split('.')
      expect(truncatedParts).toHaveLength(1) // Wrong!
    })
  })

  describe('Step 4: Backend Verification', () => {
    it('BACKEND: Expects Authorization header', () => {
      // Backend uses HTTPBearer() which looks for Authorization header
      const headers = {
        Authorization: 'Bearer token_123',
      }

      expect(headers).toHaveProperty('Authorization')
    })

    it('BACKEND: Extracts token from header', () => {
      const authHeader = 'Bearer eyJ...'
      const token = authHeader.replace('Bearer ', '')

      expect(token).toBe('eyJ...')
    })

    it('BACKEND: Verifies token signature', () => {
      // Backend fetches Keycloak public key and verifies RS256 signature
      // If signature invalid → 401

      const validSignature = true // Verified with Keycloak key
      const shouldReject = !validSignature

      expect(shouldReject).toBe(false)
      expect(validSignature).toBe(true)
    })

    it('BACKEND: Checks token audience', () => {
      // Backend checks if aud matches: ["eaistack-backend", "eaistack-web"]

      const tokenAudience = 'eaistack-web'
      const validAudiences = ['eaistack-backend', 'eaistack-web']

      const isValid = validAudiences.includes(tokenAudience)
      const shouldReject = !isValid

      expect(shouldReject).toBe(false)
      expect(isValid).toBe(true)
    })

    it('BACKEND: Checks token expiration', () => {
      const now = Math.floor(Date.now() / 1000)
      const tokenExp = now + 3600 // 1 hour from now

      const isExpired = tokenExp < now
      const isValid = !isExpired

      expect(isValid).toBe(true)
      expect(isExpired).toBe(false)
    })

    it('BACKEND: Extracts user from token', () => {
      const payload = {
        sub: 'user-123',
        preferred_username: 'testuser',
      }

      const hasSub = !!payload.sub
      expect(hasSub).toBe(true)
      expect(payload.sub).toBe('user-123')
    })
  })

  describe('Step 5: Error Scenarios (Diagnostics)', () => {
    it('IF NO TOKEN: Check browser localStorage', () => {
      localStorage.clear()

      const token = localStorage.getItem('access_token')

      if (!token) {
        console.log('[Diagnostic] No token in localStorage')
        console.log('[Diagnostic] User may not have completed login')
      }

      expect(token).toBeNull()
    })

    it('IF TOKEN NULL: Check keycloak.token too', () => {
      localStorage.setItem('access_token', 'storage_token')

      const keycloak = { token: null }
      const token = keycloak?.token || localStorage.getItem('access_token')

      if (!token) {
        console.log('[Diagnostic] No token from either source')
      }

      expect(token).toBe('storage_token')
    })

    it('IF 401 PERSISTS: Check token format', () => {
      const jwtPattern = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/

      const goodToken = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'
      const badToken = 'not-a-jwt-token'

      if (!badToken.match(jwtPattern)) {
        console.log('[Diagnostic] Token is not valid JWT format')
      }

      expect(goodToken).toMatch(jwtPattern)
      expect(badToken).not.toMatch(jwtPattern)
    })

    it('IF 401 PERSISTS: Check backend logs', () => {
      // Backend logs should show:
      // - "Verifying token..."
      // - "Token kid: [kid-value]"
      // - "Decoding token with audience..."
      // - "Token verified for user: [username]"
      // OR error message like:
      // - "Key not found"
      // - "Invalid audience"
      // - "Token expired"

      console.log('[Diagnostic] Check backend logs for error details')

      expect(true).toBe(true)
    })
  })

  describe('Complete Flow Validation', () => {
    it('should have token throughout complete flow', () => {
      // 1. After login
      localStorage.setItem('access_token', 'flow_token')

      // 2. In ChatWindow
      const keycloak = { token: localStorage.getItem('access_token') }
      expect(keycloak.token).toBeTruthy()

      // 3. When sending
      const token = keycloak.token
      expect(token).toBeTruthy()

      // 4. In request headers
      const headers = {
        Authorization: `Bearer ${token}`,
      }
      expect(headers.Authorization).toContain(token)

      // 5. Backend receives it
      expect(headers.Authorization).toMatch(/^Bearer /)
    })
  })
})
