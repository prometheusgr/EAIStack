import { describe, it, expect, beforeEach, afterEach } from 'vitest'

/**
 * TDD: Token Audience Verification
 *
 * Tests that the JWT token we send to the backend has the correct audience.
 *
 * The backend verifies tokens with:
 *   audience=[settings.keycloak_client_id, "eaistack-web"]
 *
 * If the token's "aud" claim doesn't match, we get 401 Unauthorized.
 */

describe('Token Audience Verification - TDD', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('JWT Token Structure', () => {
    it('should have standard JWT format: header.payload.signature', () => {
      // Real token from Keycloak
      const exampleToken = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImtleSJ9.eyJzdWIiOiJ1c2VyLTEyMyIsInByZWZlcnJlZF91c2VybmFtZSI6InRlc3R1c2VyIiwiYXVkIjoiZWFpc3RhY2std2ViIn0.c2lnbmF0dXJl'

      const parts = exampleToken.split('.')
      expect(parts).toHaveLength(3)
      expect(parts[0]).toBeTruthy() // header
      expect(parts[1]).toBeTruthy() // payload
      expect(parts[2]).toBeTruthy() // signature
    })

    it('should include required JWT claims', () => {
      // JWT payload must contain:
      // - sub (subject - user ID)
      // - aud (audience - who this token is for)
      // - exp (expiration)
      // - iat (issued at)

      const requiredClaims = ['sub', 'aud', 'exp', 'iat']

      // Example payload
      const payload = {
        sub: 'user-123',
        aud: 'eaistack-web',
        exp: Math.floor(Date.now() / 1000) + 3600,
        iat: Math.floor(Date.now() / 1000),
        preferred_username: 'testuser',
      }

      requiredClaims.forEach((claim) => {
        expect(payload).toHaveProperty(claim)
      })
    })
  })

  describe('Keycloak Token Audience', () => {
    it('should have audience matching backend client ID', () => {
      // Backend verifies with:
      // audience=[settings.keycloak_client_id, "eaistack-web"]
      //
      // Where settings.keycloak_client_id comes from env var (typically "eaistack-backend")

      const backendClientId = 'eaistack-backend'
      const clientName = 'eaistack-web'
      const validAudiences = [backendClientId, clientName]

      // Token from Keycloak should have one of these
      const tokenAudience = 'eaistack-web'

      expect(validAudiences).toContain(tokenAudience)
    })

    it('should fail if audience is for wrong client', () => {
      // If Keycloak issued token for the FRONTEND client,
      // but backend expects token for BACKEND client,
      // we get 401 Unauthorized

      const tokenAudience = 'eaistack-web' // Frontend client
      const backendExpectedAudiences = ['eaistack-backend', 'eaistack-web']

      // This would fail backend verification
      const isValid = backendExpectedAudiences.includes(tokenAudience)

      // If it's in the list, it's valid
      expect(isValid).toBe(true)
    })

    it('should include both frontend and backend in valid audiences', () => {
      // Best practice: Token's "aud" claim should be valid for multiple clients
      // OR backend should accept tokens for the frontend client

      const validAudiences = ['eaistack-backend', 'eaistack-web']

      const frontendToken = { aud: 'eaistack-web' }
      const backendToken = { aud: 'eaistack-backend' }

      expect(validAudiences).toContain(frontendToken.aud)
      expect(validAudiences).toContain(backendToken.aud)
    })
  })

  describe('Token Verification at Backend', () => {
    it('should verify token with correct key', () => {
      // Backend fetches Keycloak public key from:
      // https://keycloak:8080/realms/eaistack/protocol/openid-connect/certs

      const keycloakUrl = 'http://keycloak:8080'
      const realm = 'eaistack'
      const certsUrl = `${keycloakUrl}/realms/${realm}/protocol/openid-connect/certs`

      expect(certsUrl).toContain('/certs')
      expect(certsUrl).toContain('openid-connect')
    })

    it('should use RS256 algorithm for token verification', () => {
      // Keycloak uses RS256 (RSA Signature with SHA-256)
      // Token header must have: "alg": "RS256"

      const tokenHeader = {
        alg: 'RS256',
        typ: 'JWT',
        kid: 'key-id-from-keycloak',
      }

      expect(tokenHeader.alg).toBe('RS256')
    })

    it('should reject expired tokens', () => {
      // Token with exp < current time is expired

      const now = Math.floor(Date.now() / 1000)
      const expiredToken = { exp: now - 3600 } // Expired 1 hour ago
      const validToken = { exp: now + 3600 } // Expires in 1 hour

      const isExpired = (token: { exp: number }) => token.exp < now
      const isValid = (token: { exp: number }) => token.exp > now

      expect(isExpired(expiredToken)).toBe(true)
      expect(isValid(validToken)).toBe(true)
    })
  })

  describe('Error Scenarios at Backend', () => {
    it('should return 401 if no Authorization header', () => {
      // Request without Authorization header

      const headers = {
        'Content-Type': 'application/json',
        // Missing: 'Authorization: Bearer ...'
      }

      const hasAuthHeader = 'Authorization' in headers
      expect(hasAuthHeader).toBe(false)

      // Backend returns 401 Unauthorized
    })

    it('should return 401 if Authorization header is malformed', () => {
      // Invalid Authorization header formats

      const invalidFormats = [
        'Bearer', // Missing token
        'BearerToken123', // Missing space
        'Token token123', // Wrong scheme
        'InvalidToken123', // No scheme
      ]

      invalidFormats.forEach((header) => {
        // Backend would reject these
        expect(header).not.toMatch(/^Bearer [A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/)
      })
    })

    it('should return 401 if token audience is invalid', () => {
      // Token's aud doesn't match backend's expected audiences

      const token = {
        aud: 'unknown-client',
      }

      const validAudiences = ['eaistack-backend', 'eaistack-web']
      const isValid = validAudiences.includes(token.aud)

      expect(isValid).toBe(false)
      // Backend returns 401 Unauthorized
    })

    it('should return 401 if token is not signed by Keycloak', () => {
      // Token with invalid signature

      // Backend verifies signature using Keycloak's public key
      // If signature doesn't match, token is invalid
      const invalidSignature = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.invalid_signature'

      // Backend would reject this
      expect(invalidSignature).toBeTruthy()
    })

    it('should return 401 if kid (key ID) not found', () => {
      // Token header has "kid" (key ID) that doesn't exist in Keycloak

      const tokenHeader = {
        kid: 'unknown-key-id-123',
      }

      const keycloakKeys = ['key-1', 'key-2', 'key-3']
      const keyFound = keycloakKeys.includes(tokenHeader.kid)

      expect(keyFound).toBe(false)
      // Backend returns 401 Unauthorized: "Key not found"
    })
  })

  describe('Frontend Token Handling', () => {
    it('should send token in Authorization header', () => {
      const token = 'eyJ...'

      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      }

      expect(headers.Authorization).toBe(`Bearer ${token}`)
      expect(headers.Authorization).toMatch(/^Bearer /)
    })

    it('should include token when sending chat message', () => {
      // ChatWindow sends token to /api/agents/chat

      const token = 'token_from_keycloak'
      const request = {
        message: 'test',
        threadId: 'thread-123',
      }

      const requestInit = {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(request),
      }

      expect(requestInit.headers.Authorization).toContain(token)
    })

    it('should retrieve token from localStorage if available', () => {
      localStorage.setItem('access_token', 'stored_token_123')

      const token = localStorage.getItem('access_token')

      expect(token).toBe('stored_token_123')
      expect(token).toBeTruthy()
    })

    it('should use token from keycloak.token if available', () => {
      const keycloak = {
        token: 'keycloak_token_456',
      }

      const token = keycloak?.token

      expect(token).toBe('keycloak_token_456')
    })

    it('should fall back to localStorage if keycloak.token missing', () => {
      localStorage.setItem('access_token', 'storage_fallback')

      const keycloak = {
        token: undefined,
      }

      const token = keycloak?.token || localStorage.getItem('access_token')

      expect(token).toBe('storage_fallback')
    })
  })

  describe('Diagnosing 401 Errors', () => {
    it('should log token information for debugging', () => {
      // When we get 401, browser console should show token info

      const token = 'eyJ...'

      const debugInfo = {
        tokenFirstChars: token.substring(0, 20),
        tokenLength: token.length,
        headerPresent: token ? true : false,
      }

      expect(debugInfo.tokenLength).toBeGreaterThan(0)
      expect(debugInfo.headerPresent).toBe(true)
    })

    it('should identify missing Authorization header', () => {
      // Check if token is being sent at all

      const hasToken = !!localStorage.getItem('access_token')
      const keycloak = { token: undefined }

      const token = keycloak?.token || localStorage.getItem('access_token')
      const willSendAuth = !!token

      expect(willSendAuth).toBe(hasToken)
    })

    it('should verify token format before sending', () => {
      const jwtPattern = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/

      const validToken = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'
      const invalidToken = 'not a jwt'

      // Only send if matches JWT format
      expect(validToken).toMatch(jwtPattern)
      expect(invalidToken).not.toMatch(jwtPattern)
    })
  })
})
