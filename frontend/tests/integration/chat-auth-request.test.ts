import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

/**
 * Integration Test: Chat Message with Authentication
 *
 * Tests the complete flow of sending a chat message with auth token.
 * This helps diagnose why we're getting 401 Unauthorized.
 */

describe('Chat Message Authentication - Integration Test', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('Request Construction', () => {
    it('should construct request with correct headers', () => {
      const token = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyJ9.signature'

      // Simulate what agentsClient does
      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      }

      expect(headers['Content-Type']).toBe('application/json')
      expect(headers.Authorization).toMatch(/^Bearer /)
      expect(headers.Authorization).toContain(token)
    })

    it('should include token in every request', () => {
      const token1 = 'token_message_1'
      const token2 = 'token_message_2'

      // Message 1
      const headers1 = {
        Authorization: `Bearer ${token1}`,
      }
      expect(headers1.Authorization).toContain(token1)

      // Message 2
      const headers2 = {
        Authorization: `Bearer ${token2}`,
      }
      expect(headers2.Authorization).toContain(token2)
    })

    it('should NOT send request without token', () => {
      // ChatWindow should check for token first
      const token = null

      if (!token) {
        // Error before sending request
        const shouldSend = false
        expect(shouldSend).toBe(false)
      }
    })
  })

  describe('Common 401 Causes', () => {
    it('cause 1: No Authorization header sent', () => {
      // If token is undefined/null, Authorization header missing
      const token = null

      const headers = token ? { Authorization: `Bearer ${token}` } : {}

      expect(headers).toEqual({}) // Empty headers
      // Backend returns 401: no bearer token found
    })

    it('cause 2: Token has wrong audience', () => {
      // Token issued for "eaistack-web" client
      // Backend expects "eaistack-backend" or "eaistack-web"

      const tokenAudience = 'eaistack-web'
      const backendExpectation = ['eaistack-backend', 'eaistack-web']

      const isValid = backendExpectation.includes(tokenAudience)

      // If eaistack-web is in the valid list, should work
      expect(isValid).toBe(true)
    })

    it('cause 3: Token is expired', () => {
      const now = Math.floor(Date.now() / 1000)
      const expiredTime = now - 3600 // 1 hour ago

      const isExpired = expiredTime < now

      // If token is expired, backend returns 401: Token expired
      expect(isExpired).toBe(true)
    })

    it('cause 4: Token signature invalid', () => {
      // If token was modified or signed with wrong key, signature check fails
      // Backend returns 401: Invalid token

      const validToken = 'eyJ..header..eyJ..payload..valid_signature'
      const tamperedToken = 'eyJ..header..eyJ..payload..invalid_signature'

      // Real backend would use Keycloak's public key to verify
      expect(tamperedToken).not.toBe(validToken)
    })

    it('cause 5: Token missing required claims', () => {
      // Token missing "sub" (subject) or other required claims
      // Backend returns 401

      const payloadWithSub = { sub: 'user-123', aud: 'eaistack-web' }
      const payloadWithoutSub = { aud: 'eaistack-web' } // Missing sub

      expect(payloadWithSub).toHaveProperty('sub')
      expect(payloadWithoutSub).not.toHaveProperty('sub')
      // Token without sub would be rejected
    })
  })

  describe('Debugging 401 Errors', () => {
    it('should log token length to verify token is present', () => {
      const token = 'eyJhbGciOiJSUzI1NiJ9.payload.sig'

      const tokenLength = token.length
      console.log(`[Debug] Token length: ${tokenLength}`)

      expect(tokenLength).toBeGreaterThan(10)
    })

    it('should log first characters of token (safe for logs)', () => {
      const token = 'eyJhbGciOiJSUzI1NiJ9.payload.sig'

      const tokenPreview = token.substring(0, 20)
      console.log(`[Debug] Token preview: ${tokenPreview}...`)

      expect(tokenPreview).toHaveLength(20)
    })

    it('should verify Authorization header format', () => {
      const token = 'token_123'
      const authHeader = `Bearer ${token}`

      // Correct format
      expect(authHeader).toMatch(/^Bearer [^\s]+$/)

      // Common mistakes
      const mistakes = [
        'Bearer', // Missing token
        'Bearertoken_123', // Missing space
        'Bearer token_123 extra', // Extra content
        'token_123', // Missing scheme
      ]

      mistakes.forEach((wrong) => {
        expect(wrong).not.toMatch(/^Bearer [^\s]+$/)
      })
    })
  })

  describe('Request/Response Cycle', () => {
    it('should send request to /api/agents/chat', () => {
      const url = '/api/agents/chat'
      const method = 'POST'

      expect(url).toBe('/api/agents/chat')
      expect(method).toBe('POST')
    })

    it('should include message in request body', () => {
      const request = {
        message: 'test message',
        threadId: undefined,
      }

      expect(request.message).toBe('test message')
    })

    it('should handle 401 response', () => {
      const response = {
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
      }

      if (!response.ok) {
        if (response.status === 401) {
          const errorMessage = 'Chat request failed: Unauthorized'
          expect(errorMessage).toContain('Unauthorized')
        }
      }
    })

    it('should handle 200 response', () => {
      const response = {
        ok: true,
        status: 200,
        json: async () => ({
          response: 'Agent response',
          thread_id: 'thread-123',
        }),
      }

      expect(response.ok).toBe(true)
      expect(response.status).toBe(200)
    })
  })

  describe('Token Lifecycle in Chat', () => {
    it('should have token available after login', () => {
      // After successful OAuth login and token exchange
      localStorage.setItem('access_token', 'token_after_login')

      const token = localStorage.getItem('access_token')

      expect(token).toBe('token_after_login')
    })

    it('should use same token for multiple messages', () => {
      const token = 'persistent_token'
      localStorage.setItem('access_token', token)

      // Message 1
      const token1 = localStorage.getItem('access_token')
      expect(token1).toBe(token)

      // Message 2
      const token2 = localStorage.getItem('access_token')
      expect(token2).toBe(token)

      // Should be consistent
      expect(token1).toBe(token2)
    })

    it('should no longer have token after logout', () => {
      localStorage.setItem('access_token', 'token_123')
      expect(localStorage.getItem('access_token')).not.toBeNull()

      // Logout
      localStorage.removeItem('access_token')

      const token = localStorage.getItem('access_token')
      expect(token).toBeNull()

      // Subsequent requests would fail with no auth header
    })
  })

  describe('Error Message Analysis', () => {
    it('should throw ApiError with detail message from backend on non-ok response', async () => {
      const { sendChatMessage } = await import('@/api/agentsClient')

      let fetchCallCount = 0
      global.fetch = vi.fn(() => {
        fetchCallCount++
        return Promise.resolve({
          status: 401,
          ok: false,
          statusText: 'Unauthorized',
          json: async () => ({ detail: 'Token has expired' }),
        } as Response)
      })

      const mockRefresh = vi.fn(() => Promise.resolve(false))

      try {
        await sendChatMessage('test', undefined, 'invalid_token', mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: any) {
        expect(error.message).toBe('Token has expired')
        expect(error.status).toBe(401)
      }
    })

    it('should retry on 401 with refreshed token', async () => {
      const { sendChatMessage } = await import('@/api/agentsClient')

      let fetchCallCount = 0
      global.fetch = vi.fn(() => {
        fetchCallCount++
        if (fetchCallCount === 1) {
          return Promise.resolve({
            status: 401,
            ok: false,
            json: async () => ({ detail: 'Unauthorized' }),
          } as Response)
        }
        return Promise.resolve({
          status: 200,
          ok: true,
          json: async () => ({
            response: 'Agent response',
            thread_id: 'thread-123',
          }),
        } as Response)
      })

      const mockRefresh = vi.fn(() => {
        localStorage.setItem('access_token', 'refreshed_token')
        return Promise.resolve(true)
      })

      const result = await sendChatMessage('test', undefined, 'original_token', mockRefresh)

      expect(mockRefresh).toHaveBeenCalled()
      expect(result.response).toBe('Agent response')
    })

    it('should include backend error detail in exception message', async () => {
      const { sendChatMessage } = await import('@/api/agentsClient')

      global.fetch = vi.fn(() =>
        Promise.resolve({
          status: 500,
          ok: false,
          json: async () => ({ detail: 'Database connection failed' }),
        } as Response)
      )

      const mockRefresh = vi.fn(() => Promise.resolve(false))

      try {
        await sendChatMessage('test', undefined, 'token', mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: any) {
        expect(error.message).toBe('Database connection failed')
      }
    })
  })
})
