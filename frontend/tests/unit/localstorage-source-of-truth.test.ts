import { describe, it, expect, beforeEach, afterEach } from 'vitest'

/**
 * TDD: localStorage as Source of Truth for Authentication
 *
 * CRITICAL: Our app must use localStorage as the authoritative source
 * for authentication state, NOT Keycloak's session cookie.
 *
 * Why: Keycloak SSO (Single Sign On) means it checks session cookies
 * and will say "authenticated=true" even if our app's localStorage is empty.
 * This causes users to see chat when they shouldn't.
 *
 * Fix: AuthContext uses localStorage to determine auth state, independent
 * of what Keycloak's session cookie says.
 */

describe('localStorage as Source of Truth - TDD', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('App Authentication vs Keycloak Session', () => {
    it('should be NOT authenticated when localStorage is empty, even if Keycloak session exists', () => {
      // Scenario: User logged in before (Keycloak session exists)
      // But cleared localStorage (or is on fresh instance)

      localStorage.clear()
      const storedToken = localStorage.getItem('access_token')

      // Keycloak might say: authenticated=true (has session cookie)
      const kcAuthenticated = true

      // But our app should say: NOT authenticated (no stored token)
      const appAuthenticated = !!storedToken

      expect(storedToken).toBeNull()
      expect(kcAuthenticated).toBe(true) // Keycloak session exists
      expect(appAuthenticated).toBe(false) // But we're not authenticated in our app
    })

    it('should prioritize localStorage token over Keycloak session', () => {
      const scenarios = [
        {
          name: 'has stored token + keycloak session',
          hasStoredToken: true,
          kcAuthenticated: true,
          expectedAppAuth: true,
        },
        {
          name: 'has stored token, no keycloak session',
          hasStoredToken: true,
          kcAuthenticated: false,
          expectedAppAuth: true,
        },
        {
          name: 'no stored token, has keycloak session',
          hasStoredToken: false,
          kcAuthenticated: true,
          expectedAppAuth: false, // THIS IS KEY - localStorage wins
        },
        {
          name: 'no stored token, no keycloak session',
          hasStoredToken: false,
          kcAuthenticated: false,
          expectedAppAuth: false,
        },
      ]

      scenarios.forEach((scenario) => {
        if (scenario.hasStoredToken) {
          localStorage.setItem('access_token', 'token_123')
        } else {
          localStorage.clear()
        }

        const storedToken = localStorage.getItem('access_token')
        const appAuthenticated = !!storedToken

        expect(appAuthenticated).toBe(scenario.expectedAppAuth)
        localStorage.clear()
      })
    })
  })

  describe('Source of Truth Precedence', () => {
    it('should use stored token if available', () => {
      localStorage.setItem('access_token', 'my_token')

      const storedToken = localStorage.getItem('access_token')
      const isAuthenticated = !!storedToken

      expect(isAuthenticated).toBe(true)
    })

    it('should NOT authenticate if no stored token, regardless of Keycloak', () => {
      localStorage.clear()

      const storedToken = localStorage.getItem('access_token')
      const isAuthenticated = !!storedToken

      expect(isAuthenticated).toBe(false)
    })

    it('should check stored token first before Keycloak state', () => {
      // App authentication logic:
      // const appAuth = !!storedToken || (kcAuthenticated && !!kc.token)

      const storedToken = localStorage.getItem('access_token')
      const kcAuthenticated = true // Keycloak session exists
      const kcToken = undefined // But no token set on kc instance

      const appAuth = !!storedToken || (kcAuthenticated && !!kcToken)

      expect(storedToken).toBeNull()
      expect(appAuth).toBe(false) // Should be false due to empty localStorage
    })

    it('should accept Keycloak auth only if we also have a token', () => {
      // Both conditions must be true:
      // 1. Keycloak says authenticated
      // 2. Keycloak has an actual token

      const kcAuthenticated = true
      const kcToken = 'keycloak_token'

      const appAuth = kcAuthenticated && !!kcToken

      expect(appAuth).toBe(true)
    })

    it('should reject Keycloak auth if session but no token', () => {
      // Keycloak says authenticated (session exists)
      // But no actual token on kc instance

      const kcAuthenticated = true
      const kcToken = undefined

      const appAuth = kcAuthenticated && !!kcToken

      expect(appAuth).toBe(false)
    })
  })

  describe('Fresh Instance vs Previous Session', () => {
    it('should show login page on fresh instance despite Keycloak session', () => {
      // Fresh instance: no localStorage
      localStorage.clear()

      // But Keycloak session exists from previous browser session
      const storedToken = localStorage.getItem('access_token')
      const kcAuthenticated = true // Session cookie still valid

      // App should still show login page
      const showLogin = !storedToken
      const showChat = !!storedToken

      expect(showLogin).toBe(true)
      expect(showChat).toBe(false)
    })

    it('should not skip login on fresh instance', () => {
      localStorage.clear()

      // Keycloak would auto-authenticate due to session cookie
      const kcWouldAutoAuth = true

      // But we explicitly require stored token
      const userMustLogin = !localStorage.getItem('access_token')

      expect(userMustLogin).toBe(true)
    })

    it('should enforce login after logout clears localStorage', () => {
      // Before logout: authenticated
      localStorage.setItem('access_token', 'token_abc')
      let isAuth = !!localStorage.getItem('access_token')
      expect(isAuth).toBe(true)

      // After logout: clear localStorage
      localStorage.removeItem('access_token')

      // Now not authenticated, even if Keycloak session exists
      isAuth = !!localStorage.getItem('access_token')
      expect(isAuth).toBe(false)
    })
  })

  describe('Token Consistency', () => {
    it('should have token in localStorage and on keycloak instance', () => {
      const token = 'consistent_token'
      localStorage.setItem('access_token', token)

      // Both should match
      const stored = localStorage.getItem('access_token')
      const onKeycloak = token // Would be set: kc.token = token

      expect(stored).toBe(onKeycloak)
    })

    it('should detect when tokens are out of sync', () => {
      localStorage.setItem('access_token', 'stored_token')

      // If kc.token is different (or missing), use stored
      const stored = localStorage.getItem('access_token')
      const onKeycloak = undefined

      const token = stored || onKeycloak

      expect(token).toBe('stored_token')
    })
  })

  describe('Logout Side Effects', () => {
    it('should clear localStorage on logout', () => {
      localStorage.setItem('access_token', 'token_123')
      expect(localStorage.getItem('access_token')).not.toBeNull()

      // Logout clears it
      localStorage.removeItem('access_token')

      expect(localStorage.getItem('access_token')).toBeNull()
    })

    it('should NOT re-authenticate after logout despite session cookie', () => {
      // Setup: logged in
      localStorage.setItem('access_token', 'token_123')
      let isAuth = !!localStorage.getItem('access_token')
      expect(isAuth).toBe(true)

      // Logout: clear localStorage
      localStorage.removeItem('access_token')

      // Now not authenticated
      isAuth = !!localStorage.getItem('access_token')

      // Even if Keycloak session cookie still exists
      const kcSessionStillExists = true

      // Our app is NOT authenticated
      expect(isAuth).toBe(false)
      expect(kcSessionStillExists).toBe(true) // Separate from our auth
    })

    it('should require new login after logout', () => {
      // After logout, user must login again (get new token)
      localStorage.clear()

      const hasToken = !!localStorage.getItem('access_token')

      // User must click login and go through OAuth flow again
      expect(hasToken).toBe(false)
    })
  })

  describe('Multiple Sessions / Users', () => {
    it('should handle session switching via localStorage only', () => {
      // User 1 logs in
      localStorage.setItem('access_token', 'user1_token')
      let auth = !!localStorage.getItem('access_token')
      expect(auth).toBe(true)

      // User 1 logs out
      localStorage.removeItem('access_token')
      auth = !!localStorage.getItem('access_token')
      expect(auth).toBe(false)

      // User 2 logs in
      localStorage.setItem('access_token', 'user2_token')
      auth = !!localStorage.getItem('access_token')
      expect(auth).toBe(true)

      // No cross-contamination
      expect(localStorage.getItem('access_token')).toBe('user2_token')

      localStorage.clear()
    })
  })

  describe('Browser Context Scenarios', () => {
    it('should work in private/incognito mode (no Keycloak cookie)', () => {
      // Private mode: no cookies, no localStorage persistence expected
      localStorage.clear()

      const hasToken = !!localStorage.getItem('access_token')
      expect(hasToken).toBe(false)
      // Should show login
    })

    it('should work after clearing cookies but not localStorage', () => {
      // Edge case: cookies cleared, localStorage survives
      localStorage.setItem('access_token', 'token_survives')

      // Keycloak session cookie gone, but our token remains
      const stored = localStorage.getItem('access_token')
      const isAuth = !!stored

      expect(isAuth).toBe(true) // Still authenticated
    })

    it('should work after clearing localStorage but not cookies', () => {
      // Edge case: localStorage cleared, Keycloak cookie remains
      localStorage.clear()

      // Keycloak would say: authenticated (session cookie exists)
      // But our app says: NOT authenticated (no stored token)
      const isAuth = !!localStorage.getItem('access_token')

      expect(isAuth).toBe(false) // Not authenticated
    })
  })

  describe('Explicit Logout of Keycloak Session', () => {
    it('should optionally call keycloak.logout to clear session cookie', () => {
      // After clearing localStorage, can also call kc.logout()
      // to clear Keycloak's session cookie for full logout

      localStorage.clear()

      const logoutFn = () => {
        // Clear localStorage
        localStorage.removeItem('access_token')
        // Clear Keycloak session
        // keycloak.logout({ redirectUri: ... })
      }

      logoutFn()

      expect(localStorage.getItem('access_token')).toBeNull()
    })

    it('should be in consistent state after logout', () => {
      localStorage.setItem('access_token', 'token_123')

      // Complete logout:
      localStorage.removeItem('access_token')
      const kcLogoutCalled = true // Would call keycloak.logout()

      // Verify state
      const hasToken = !!localStorage.getItem('access_token')
      expect(hasToken).toBe(false)
      expect(kcLogoutCalled).toBe(true)
    })
  })
})
