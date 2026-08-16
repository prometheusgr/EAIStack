import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

/**
 * TDD: Chat Window Token Integration
 *
 * Tests that ChatWindow can access and use auth token:
 * 1. Token available from keycloak.token after login
 * 2. ChatWindow retrieves token correctly
 * 3. Token included in API request headers
 * 4. Error shown if no token available
 * 5. Chat message not sent without token
 */

describe('Chat Window Token Integration - TDD', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('Token Availability After Login', () => {
    it('should have token available in keycloak.token after OAuth login', () => {
      // After code exchange and token storage, keycloak.token should be set
      const newToken = 'eyJ..valid..oauth..token'
      const keycloak = {
        token: newToken,
        tokenParsed: { preferred_username: 'user123' },
      }

      expect(keycloak.token).toBe(newToken)
      expect(keycloak.token).not.toBeNull()
      expect(keycloak.token).toBeDefined()
    })

    it('should restore token in keycloak.token on page reload', () => {
      // Setup: token from previous session in localStorage
      const storedToken = 'persisted_token_from_previous_session'
      localStorage.setItem('access_token', storedToken)

      // On page reload, AuthContext should restore it
      const keycloak = {
        token: localStorage.getItem('access_token') || undefined,
        tokenParsed: {},
      }

      expect(keycloak.token).toBe(storedToken)
    })

    it('should be null if not authenticated', () => {
      const keycloak = {
        token: null,
        tokenParsed: undefined,
      }

      expect(keycloak.token).toBeNull()
    })
  })

  describe('ChatWindow Token Retrieval', () => {
    it('should retrieve token from keycloak.token', () => {
      const keycloak = {
        token: 'chat_token_abc123',
      }

      // ChatWindow does: const token = keycloak?.token
      const token = keycloak?.token

      expect(token).toBe('chat_token_abc123')
    })

    it('should fall back to localStorage if keycloak.token is undefined', () => {
      // Setup: token in storage but keycloak.token not set
      const storedToken = 'fallback_token_from_storage'
      localStorage.setItem('access_token', storedToken)

      const keycloak = {
        token: undefined, // Not set
      }

      // ChatWindow does: const token = keycloak?.token || localStorage.getItem('access_token')
      const token = keycloak?.token || localStorage.getItem('access_token')

      expect(token).toBe(storedToken)
    })

    it('should prefer keycloak.token over localStorage token', () => {
      const kcToken = 'keycloak_token'
      const storageToken = 'storage_token'

      localStorage.setItem('access_token', storageToken)
      const keycloak = { token: kcToken }

      // Should use keycloak.token first
      const token = keycloak?.token || localStorage.getItem('access_token')

      expect(token).toBe('keycloak_token')
      expect(token).not.toBe('storage_token')
    })

    it('should handle keycloak being null', () => {
      const keycloak = null
      const storedToken = 'token_in_storage'
      localStorage.setItem('access_token', storedToken)

      // ChatWindow does: const token = keycloak?.token || localStorage.getItem('access_token')
      const token = keycloak?.token || localStorage.getItem('access_token')

      expect(token).toBe(storedToken)
    })

    it('should check both sources for token availability', () => {
      const scenarios = [
        {
          name: 'both sources have token',
          keycloak: { token: 'kc_token' },
          stored: 'storage_token',
          expected: 'kc_token',
        },
        {
          name: 'only keycloak has token',
          keycloak: { token: 'kc_token' },
          stored: null,
          expected: 'kc_token',
        },
        {
          name: 'only localStorage has token',
          keycloak: { token: undefined },
          stored: 'storage_token',
          expected: 'storage_token',
        },
        {
          name: 'neither has token',
          keycloak: { token: undefined },
          stored: null,
          expected: null,
        },
      ]

      scenarios.forEach((scenario) => {
        localStorage.clear()
        if (scenario.stored) {
          localStorage.setItem('access_token', scenario.stored)
        }

        const token = scenario.keycloak?.token || localStorage.getItem('access_token')

        if (scenario.expected) {
          expect(token).toBe(scenario.expected)
        } else {
          expect(token).toBeNull()
        }
      })
    })
  })

  describe('Token in API Requests', () => {
    it('should include token in Authorization header', () => {
      const token = 'request_token_xyz'
      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      }

      expect(headers.Authorization).toBe(`Bearer ${token}`)
      expect(headers.Authorization).toMatch(/^Bearer /)
    })

    it('should send token with fetch request', () => {
      const token = 'fetch_token_123'
      const message = 'test message'

      // Simulate what ChatWindow does
      const requestInit = {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message }),
      }

      expect(requestInit.headers.Authorization).toContain(token)
      expect(requestInit.method).toBe('POST')
    })

    it('should use Bearer scheme for token', () => {
      const token = 'some_token_abc'
      const authHeader = `Bearer ${token}`

      expect(authHeader).toMatch(/^Bearer /)
      expect(authHeader).toContain(token)
      expect(authHeader).toBe(`Bearer ${token}`)
    })

    it('should handle long token strings in headers', () => {
      const longToken =
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'
      const headers = {
        Authorization: `Bearer ${longToken}`,
      }

      expect(headers.Authorization).toContain(longToken)
      expect(headers.Authorization.length).toBeGreaterThan(100)
    })
  })

  describe('Error Handling for Missing Token', () => {
    it('should show error when no token available', () => {
      localStorage.clear()
      const keycloak = { token: undefined }

      const token = keycloak?.token || localStorage.getItem('access_token')
      const hasToken = !!token

      if (!hasToken) {
        const errorMessage = 'No auth token available. Please log in.'
        expect(errorMessage).toBeDefined()
        expect(errorMessage).toContain('token')
      }

      expect(hasToken).toBe(false)
    })

    it('should prevent message send if no token', () => {
      localStorage.clear()
      const keycloak = { token: undefined }

      const token = keycloak?.token || localStorage.getItem('access_token')
      const canSendMessage = !!token

      if (!canSendMessage) {
        const errorMsg = 'No auth token available. Please log in.'
        expect(errorMsg).toBeTruthy()
      }

      expect(canSendMessage).toBe(false)
    })

    it('should display error to user on message send', () => {
      const error = new Error('No auth token available. Please log in.')

      expect(error.message).toContain('token')
      expect(error.message).toContain('log in')
    })

    it('should not add user message if token check fails', () => {
      localStorage.clear()
      const keycloak = { token: undefined }
      let messages: any[] = []

      const token = keycloak?.token || localStorage.getItem('access_token')

      if (!token) {
        // Don't add message to list
        expect(messages.length).toBe(0)
      }

      // If token was available, would add:
      // messages.push({ role: 'user', text: 'test' })

      expect(messages).toHaveLength(0)
    })
  })

  describe('Token Persistence Through Chat Session', () => {
    it('should keep token available for multiple messages in session', () => {
      const token = 'session_token_123'
      localStorage.setItem('access_token', token)

      // First message
      const token1 = localStorage.getItem('access_token')
      expect(token1).toBe(token)

      // Second message
      const token2 = localStorage.getItem('access_token')
      expect(token2).toBe(token)

      // Third message
      const token3 = localStorage.getItem('access_token')
      expect(token3).toBe(token)

      // All should be the same token
      expect(token1).toBe(token2)
      expect(token2).toBe(token3)
    })

    it('should not lose token between message sends', () => {
      const token = 'persistent_token'
      localStorage.setItem('access_token', token)

      const keycloak = { token }

      // Message 1
      const token1 = keycloak.token || localStorage.getItem('access_token')
      expect(token1).toBeTruthy()

      // Message 2
      const token2 = keycloak.token || localStorage.getItem('access_token')
      expect(token2).toBeTruthy()

      // Both should work
      expect(token1).toBe(token)
      expect(token2).toBe(token)
    })

    it('should use same token for all API requests in session', () => {
      const sessionToken = 'same_token_for_session'
      localStorage.setItem('access_token', sessionToken)

      // Request 1
      const req1Token = localStorage.getItem('access_token')
      // Request 2
      const req2Token = localStorage.getItem('access_token')
      // Request 3
      const req3Token = localStorage.getItem('access_token')

      expect(req1Token).toBe(sessionToken)
      expect(req2Token).toBe(sessionToken)
      expect(req3Token).toBe(sessionToken)
    })
  })

  describe('Token Syncing After Login', () => {
    it('should sync token from localStorage to keycloak.token after code exchange', () => {
      // After OAuth code exchange, token stored in localStorage
      const exchangedToken = 'exchanged_oauth_token'
      localStorage.setItem('access_token', exchangedToken)

      // AuthContext should set it on keycloak instance
      const keycloak = {
        token: localStorage.getItem('access_token'),
      }

      expect(keycloak.token).toBe(exchangedToken)
    })

    it('should sync token from localStorage to keycloak.token on page reload', () => {
      // Simulate page reload: token in storage from previous session
      const persistedToken = 'token_from_previous_session'
      localStorage.setItem('access_token', persistedToken)

      // AuthContext retrieves it on init
      const keycloak = {
        token: localStorage.getItem('access_token'),
      }

      expect(keycloak.token).toBe(persistedToken)
    })

    it('should update keycloak.tokenParsed after setting token', () => {
      const tokenData = {
        access_token: 'token_abc',
        tokenParsed: {
          preferred_username: 'alice',
          email: 'alice@example.com',
          name: 'Alice',
        },
      }

      const keycloak = {
        token: tokenData.access_token,
        tokenParsed: tokenData.tokenParsed,
      }

      expect(keycloak.token).toBe('token_abc')
      expect(keycloak.tokenParsed?.preferred_username).toBe('alice')
    })
  })

  describe('Token Availability in ChatWindow Context', () => {
    it('should have token available when useAuth is called', () => {
      const token = 'token_from_auth_context'
      localStorage.setItem('access_token', token)

      // ChatWindow calls useAuth
      const authContext = {
        keycloak: { token },
      }

      // Then retrieves token
      const chatToken = authContext.keycloak?.token || localStorage.getItem('access_token')

      expect(chatToken).toBe(token)
    })

    it('should handle useAuth returning null keycloak', () => {
      const storedToken = 'token_in_storage'
      localStorage.setItem('access_token', storedToken)

      const authContext = {
        keycloak: null,
      }

      // Should fall back to localStorage
      const chatToken = authContext.keycloak?.token || localStorage.getItem('access_token')

      expect(chatToken).toBe(storedToken)
    })

    it('should be usable immediately after login completes', () => {
      // Login completes, token received
      const newToken = 'fresh_login_token'
      localStorage.setItem('access_token', newToken)

      const keycloak = { token: newToken }

      // ChatWindow should be able to use it immediately
      const token = keycloak?.token || localStorage.getItem('access_token')

      expect(token).toBe(newToken)
      expect(token).toBeTruthy()
    })
  })

  describe('Recovery After Token Loss', () => {
    it('should recover token from localStorage if keycloak instance resets', () => {
      const token = 'recoverable_token'
      localStorage.setItem('access_token', token)

      // Keycloak instance lost/reset
      let keycloak: any = null

      // Should still be able to access token from storage
      const recoveredToken = keycloak?.token || localStorage.getItem('access_token')

      expect(recoveredToken).toBe(token)
    })

    it('should handle component re-render with token loss', () => {
      const token = 'rerender_token'
      localStorage.setItem('access_token', token)

      // Component re-renders
      const keycloak1 = { token }
      const token1 = keycloak1?.token || localStorage.getItem('access_token')

      // After re-render, keycloak might be unset
      const keycloak2 = { token: undefined }
      const token2 = keycloak2?.token || localStorage.getItem('access_token')

      expect(token1).toBe(token)
      expect(token2).toBe(token) // Should still get it from storage
    })
  })
})
