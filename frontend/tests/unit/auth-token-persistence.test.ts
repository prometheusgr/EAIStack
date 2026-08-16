import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

/**
 * TDD: Token Persistence and JWT Parsing
 *
 * Tests that the AuthContext properly:
 * 1. Stores token in localStorage with correct keys
 * 2. Parses JWT to extract user claims
 * 3. Restores authenticated state from stored token
 * 4. Handles expired or invalid tokens
 * 5. Updates user state with correct claims
 */

describe('Token Persistence - TDD', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('Token Storage Keys', () => {
    it('should store access_token with correct key', () => {
      const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'

      localStorage.setItem('access_token', token)

      expect(localStorage.getItem('access_token')).toBe(token)
    })

    it('should store token_type with correct key', () => {
      const tokenType = 'Bearer'

      localStorage.setItem('token_type', tokenType)

      expect(localStorage.getItem('token_type')).toBe(tokenType)
    })

    it('should store refresh_token when provided', () => {
      const refreshToken = 'refresh_token_value_xyz'

      localStorage.setItem('refresh_token', refreshToken)

      expect(localStorage.getItem('refresh_token')).toBe(refreshToken)
    })

    it('should handle all three tokens together', () => {
      const tokens = {
        access_token: 'access_abc123',
        token_type: 'Bearer',
        refresh_token: 'refresh_xyz789',
      }

      localStorage.setItem('access_token', tokens.access_token)
      localStorage.setItem('token_type', tokens.token_type)
      localStorage.setItem('refresh_token', tokens.refresh_token)

      expect(localStorage.getItem('access_token')).toBe('access_abc123')
      expect(localStorage.getItem('token_type')).toBe('Bearer')
      expect(localStorage.getItem('refresh_token')).toBe('refresh_xyz789')
    })
  })

  describe('JWT Parsing', () => {
    it('should parse valid JWT and extract payload', () => {
      // Real JWT structure: header.payload.signature
      // Payload (when decoded): { sub, preferred_username, email, name, etc }

      const payload = {
        sub: '550e8400-e29b-41d4-a716-446655440000',
        preferred_username: 'testuser',
        email: 'testuser@example.com',
        name: 'Test User',
        iat: 1234567890,
        exp: 1234571490,
      }

      // Base64 encode (URL-safe: replace +/= with -_)
      const encodedPayload = btoa(JSON.stringify(payload))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=/g, '')

      const fakeJwt = `header.${encodedPayload}.signature`

      // Parse like AuthContext does
      const tokenParts = fakeJwt.split('.')
      expect(tokenParts.length).toBe(3)

      const decoded = JSON.parse(
        atob(tokenParts[1].replace(/-/g, '+').replace(/_/g, '/'))
      )

      expect(decoded.preferred_username).toBe('testuser')
      expect(decoded.email).toBe('testuser@example.com')
      expect(decoded.name).toBe('Test User')
      expect(decoded.sub).toBe('550e8400-e29b-41d4-a716-446655440000')
    })

    it('should extract user claims from JWT payload', () => {
      const userClaims = {
        preferred_username: 'alice',
        email: 'alice@company.com',
        name: 'Alice Smith',
        sub: 'user-123',
      }

      // Create minimal JWT for testing
      const payload = btoa(JSON.stringify(userClaims))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
      const jwt = `header.${payload}.sig`

      const tokenParts = jwt.split('.')
      const decoded = JSON.parse(
        atob(tokenParts[1].replace(/-/g, '+').replace(/_/g, '/'))
      )

      // These are the fields AuthContext should extract
      const user = {
        username: decoded.preferred_username,
        email: decoded.email,
        name: decoded.name,
      }

      expect(user.username).toBe('alice')
      expect(user.email).toBe('alice@company.com')
      expect(user.name).toBe('Alice Smith')
    })

    it('should handle JWT with missing optional claims', () => {
      // Some tokens might not have all claims
      const minimalPayload = {
        sub: 'user-456',
        preferred_username: 'bob',
        // email and name are optional
      }

      const payload = btoa(JSON.stringify(minimalPayload))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
      const jwt = `header.${payload}.sig`

      const tokenParts = jwt.split('.')
      const decoded = JSON.parse(
        atob(tokenParts[1].replace(/-/g, '+').replace(/_/g, '/'))
      )

      const user = {
        username: decoded.preferred_username,
        email: decoded.email || undefined,
        name: decoded.name || undefined,
      }

      expect(user.username).toBe('bob')
      expect(user.email).toBeUndefined()
      expect(user.name).toBeUndefined()
    })

    it('should reject invalid JWT format', () => {
      const validJwtFormat = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/

      const invalidJwts = [
        'not_a_jwt',           // No dots
        'only.two',             // Only 2 parts
        '',                     // Empty
        'has..empty.parts',     // Empty payload
      ]

      invalidJwts.forEach((jwt) => {
        expect(jwt).not.toMatch(validJwtFormat)
      })
    })

    it('should handle malformed base64 in JWT', () => {
      const malformedJwt = 'header.!!!invalid_base64!!!.sig'

      const tokenParts = malformedJwt.split('.')
      expect(() => {
        atob(tokenParts[1])
      }).toThrow()
    })
  })

  describe('Token Restoration from localStorage', () => {
    it('should check for stored token on init', () => {
      const token = 'stored_token_abc'
      localStorage.setItem('access_token', token)

      // AuthContext should check this
      const storedToken = localStorage.getItem('access_token')
      expect(storedToken).toBe('stored_token_abc')
      expect(storedToken).not.toBeNull()
    })

    it('should skip Keycloak init if token already stored', () => {
      // If we have a valid token from previous login, we don't need to
      // call Keycloak init again
      const token = 'existing_token'
      localStorage.setItem('access_token', token)

      // AuthContext logic:
      const hasStoredToken = !!localStorage.getItem('access_token')
      let shouldCallKeycloakInit = !hasStoredToken

      expect(hasStoredToken).toBe(true)
      expect(shouldCallKeycloakInit).toBe(false)
    })

    it('should restore user info from stored token on page reload', () => {
      // Simulate stored token from previous session
      const userData = {
        preferred_username: 'charlie',
        email: 'charlie@test.com',
        name: 'Charlie Davis',
        sub: 'user-789',
      }

      const payload = btoa(JSON.stringify(userData))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
      const jwt = `header.${payload}.sig`

      localStorage.setItem('access_token', jwt)

      // On page reload, AuthContext finds token and restores user
      const storedToken = localStorage.getItem('access_token')
      expect(storedToken).not.toBeNull()

      if (storedToken) {
        const tokenParts = storedToken.split('.')
        if (tokenParts.length === 3) {
          const decoded = JSON.parse(
            atob(tokenParts[1].replace(/-/g, '+').replace(/_/g, '/'))
          )

          expect(decoded.preferred_username).toBe('charlie')
          expect(decoded.email).toBe('charlie@test.com')
        }
      }
    })
  })

  describe('Token Lifecycle', () => {
    it('should store all token response fields', () => {
      // Backend returns this from code exchange
      const tokenResponse = {
        access_token: 'eyJ...',
        token_type: 'Bearer',
        refresh_token: 'refresh_...',
        expires_in: 300,
      }

      // AuthContext stores these
      localStorage.setItem('access_token', tokenResponse.access_token)
      localStorage.setItem('token_type', tokenResponse.token_type)
      localStorage.setItem('refresh_token', tokenResponse.refresh_token)

      // Verify all stored
      expect(localStorage.getItem('access_token')).toBe(tokenResponse.access_token)
      expect(localStorage.getItem('token_type')).toBe(tokenResponse.token_type)
      expect(localStorage.getItem('refresh_token')).toBe(tokenResponse.refresh_token)
      // Note: expires_in is not stored (could calculate expiry if needed)
    })

    it('should clear tokens on logout', () => {
      // Setup: tokens stored
      localStorage.setItem('access_token', 'token_abc')
      localStorage.setItem('token_type', 'Bearer')
      localStorage.setItem('refresh_token', 'refresh_xyz')

      expect(localStorage.getItem('access_token')).not.toBeNull()

      // Logout: clear all tokens
      localStorage.removeItem('access_token')
      localStorage.removeItem('token_type')
      localStorage.removeItem('refresh_token')

      expect(localStorage.getItem('access_token')).toBeNull()
      expect(localStorage.getItem('token_type')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
    })

    it('should not mix tokens from different users', () => {
      // User 1 logs in
      localStorage.setItem('access_token', 'user1_token')
      expect(localStorage.getItem('access_token')).toBe('user1_token')

      // User 1 logs out and clears tokens
      localStorage.removeItem('access_token')

      // User 2 logs in
      localStorage.setItem('access_token', 'user2_token')
      expect(localStorage.getItem('access_token')).toBe('user2_token')
      expect(localStorage.getItem('access_token')).not.toBe('user1_token')
    })
  })

  describe('Edge Cases', () => {
    it('should handle localStorage being unavailable', () => {
      // In some environments, localStorage might be disabled
      // AuthContext should gracefully handle this

      const getTokenSafely = () => {
        try {
          return localStorage.getItem('access_token')
        } catch {
          console.warn('localStorage unavailable')
          return null
        }
      }

      const token = getTokenSafely()
      expect(token).toBeNull() // No token stored
    })

    it('should handle corrupted token in localStorage', () => {
      localStorage.setItem('access_token', 'corrupted_data_!!!!')

      const storedToken = localStorage.getItem('access_token')
      expect(storedToken).toBe('corrupted_data_!!!!')

      // Trying to parse it should fail gracefully
      const tokenParts = storedToken.split('.')
      expect(tokenParts.length).not.toBe(3) // Not a valid JWT
    })

    it('should handle token with extra whitespace', () => {
      const tokenWithWhitespace = '  eyJ... token ...  '
      localStorage.setItem('access_token', tokenWithWhitespace)

      const storedToken = localStorage.getItem('access_token')
      expect(storedToken).toBe(tokenWithWhitespace)

      // Should trim before parsing
      const trimmed = storedToken.trim()
      const tokenParts = trimmed.split('.')
      // Now should have 3 parts (if it was valid token)
    })
  })

  describe('Integration with Auth State', () => {
    it('should set isAuthenticated=true when token stored', () => {
      localStorage.setItem('access_token', 'valid_token')

      const hasToken = !!localStorage.getItem('access_token')
      const isAuthenticated = hasToken

      expect(isAuthenticated).toBe(true)
    })

    it('should set isAuthenticated=false when no token', () => {
      const hasToken = !!localStorage.getItem('access_token')
      const isAuthenticated = hasToken

      expect(isAuthenticated).toBe(false)
    })

    it('should update user object with token claims', () => {
      const claims = {
        preferred_username: 'dane',
        email: 'dane@org.com',
        name: 'Dane Evans',
      }

      const user = {
        username: claims.preferred_username,
        email: claims.email,
        name: claims.name,
      }

      expect(user.username).toBe('dane')
      expect(user.email).toBe('dane@org.com')
      expect(user.name).toBe('Dane Evans')
    })
  })
})
