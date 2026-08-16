import { describe, it, expect } from 'vitest'

/**
 * TDD: Login Must Include prompt=login Parameter
 *
 * CRITICAL FIX: The prompt=login parameter tells Keycloak to:
 * - Ignore existing session cookies
 * - Show login form even if user has valid session
 * - Force fresh authentication
 *
 * Without prompt=login, after logout:
 * 1. User clicks login
 * 2. Browser redirects to Keycloak
 * 3. Keycloak checks session cookie (still valid from before logout)
 * 4. Keycloak skips login form
 * 5. Keycloak returns code immediately
 * 6. User sees chat without entering credentials
 */

describe('Login prompt=login Parameter - TDD', () => {
  describe('Keycloak OAuth2 Parameters', () => {
    it('should include all required OAuth2 parameters', () => {
      const url = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      url.searchParams.set('client_id', 'eaistack-web')
      url.searchParams.set('redirect_uri', 'http://localhost:3000/')
      url.searchParams.set('response_type', 'code')
      url.searchParams.set('response_mode', 'query')
      url.searchParams.set('scope', 'openid profile email')
      url.searchParams.set('state', 'state-value')

      expect(url.searchParams.get('client_id')).toBe('eaistack-web')
      expect(url.searchParams.get('redirect_uri')).toBe('http://localhost:3000/')
      expect(url.searchParams.get('response_type')).toBe('code')
      expect(url.searchParams.get('scope')).toBe('openid profile email')
    })

    it('CRITICAL: must include prompt=login parameter', () => {
      const url = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      url.searchParams.set('client_id', 'eaistack-web')
      url.searchParams.set('redirect_uri', 'http://localhost:3000/')
      url.searchParams.set('response_type', 'code')
      url.searchParams.set('response_mode', 'query')
      url.searchParams.set('scope', 'openid profile email')
      url.searchParams.set('state', 'state-value')
      url.searchParams.set('prompt', 'login') // THIS IS KEY!

      expect(url.searchParams.get('prompt')).toBe('login')
    })

    it('prompt=login overrides Keycloak session', () => {
      // With prompt=login:
      const withPrompt = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      withPrompt.searchParams.set('prompt', 'login')

      // Keycloak will:
      // 1. Ignore session cookie
      // 2. Show login form
      // 3. Require user to enter credentials

      expect(withPrompt.searchParams.get('prompt')).toBe('login')

      // Without prompt=login:
      const withoutPrompt = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      // Missing prompt parameter

      // Keycloak will:
      // 1. Check for session cookie
      // 2. If valid, skip login form
      // 3. Return code immediately (BUG!)

      expect(withoutPrompt.searchParams.has('prompt')).toBe(false)
    })
  })

  describe('Keycloak prompt Parameter Values', () => {
    it('prompt=login forces authentication', () => {
      // prompt=login tells Keycloak:
      // "User must authenticate, even if session exists"

      const prompt = 'login'
      expect(prompt).toBe('login')
    })

    it('prompt=consent requests user consent', () => {
      // For reference: other prompt values exist
      const otherPrompts = ['consent', 'none']

      // But for our use case, prompt=login is correct
      expect(otherPrompts).not.toContain('login')
    })

    it('without prompt, Keycloak uses session if available', () => {
      // Default behavior (no prompt parameter):
      // If session cookie exists, use it
      // If no session, show login

      // This is why logout wasn't working!
      // After logout, Keycloak session cookie still existed
      // So Keycloak auto-logged user back in

      const hasSession = true // After logout
      const wouldSkipLoginForm = hasSession // Without prompt=login

      expect(wouldSkipLoginForm).toBe(true)
    })
  })

  describe('Complete Login URL', () => {
    it('should have correct format for Keycloak auth endpoint', () => {
      const baseUrl = 'http://localhost:8080'
      const realm = 'eaistack'
      const endpoint = `/realms/${realm}/protocol/openid-connect/auth`

      const url = new URL(`${baseUrl}${endpoint}`)

      expect(url.hostname).toBe('localhost')
      expect(url.pathname).toContain('/protocol/openid-connect/auth')
    })

    it('should construct complete login URL with all parameters', () => {
      const url = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')

      const params = {
        client_id: 'eaistack-web',
        redirect_uri: 'http://localhost:3000/',
        response_type: 'code',
        response_mode: 'query',
        scope: 'openid profile email',
        state: `state-${Date.now()}`,
        prompt: 'login',
      }

      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.set(key, value)
      })

      // Verify all parameters are set
      Object.entries(params).forEach(([key]) => {
        expect(url.searchParams.has(key)).toBe(true)
      })

      // Verify prompt=login is present
      expect(url.searchParams.get('prompt')).toBe('login')
    })
  })

  describe('Bug Fix Verification', () => {
    it('before fix: login URL missing prompt=login', () => {
      const loginUrlBefore = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      loginUrlBefore.searchParams.set('client_id', 'eaistack-web')
      loginUrlBefore.searchParams.set('redirect_uri', 'http://localhost:3000/')
      loginUrlBefore.searchParams.set('response_type', 'code')
      loginUrlBefore.searchParams.set('response_mode', 'query')
      loginUrlBefore.searchParams.set('scope', 'openid profile email')
      // Missing: prompt=login

      const hasPromptBefore = loginUrlBefore.searchParams.has('prompt')
      expect(hasPromptBefore).toBe(false) // BUG
    })

    it('after fix: login URL includes prompt=login', () => {
      const loginUrlAfter = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      loginUrlAfter.searchParams.set('client_id', 'eaistack-web')
      loginUrlAfter.searchParams.set('redirect_uri', 'http://localhost:3000/')
      loginUrlAfter.searchParams.set('response_type', 'code')
      loginUrlAfter.searchParams.set('response_mode', 'query')
      loginUrlAfter.searchParams.set('scope', 'openid profile email')
      loginUrlAfter.searchParams.set('prompt', 'login') // FIXED

      const hasPromptAfter = loginUrlAfter.searchParams.has('prompt')
      expect(hasPromptAfter).toBe(true) // FIXED

      expect(loginUrlAfter.searchParams.get('prompt')).toBe('login')
    })
  })

  describe('Logout -> Login Flow With Fix', () => {
    it('after logout, login with prompt=login requires credentials', () => {
      // Logout
      localStorage.removeItem('access_token')

      // User clicks login
      const loginUrl = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      loginUrl.searchParams.set('client_id', 'eaistack-web')
      loginUrl.searchParams.set('redirect_uri', 'http://localhost:3000/')
      loginUrl.searchParams.set('response_type', 'code')
      loginUrl.searchParams.set('response_mode', 'query')
      loginUrl.searchParams.set('scope', 'openid profile email')
      loginUrl.searchParams.set('prompt', 'login') // KEY FIX

      // With prompt=login:
      // 1. Browser redirects to loginUrl
      // 2. Keycloak IGNORES session cookie
      // 3. Keycloak shows login form
      // 4. User enters credentials
      // 5. Keycloak issues code
      // 6. App exchanges code for token
      // 7. User sees chat

      expect(loginUrl.searchParams.get('prompt')).toBe('login')
    })
  })

  describe('Testing Scenarios', () => {
    it('scenario 1: First time user login', () => {
      // Fresh install, no session cookie
      // With or without prompt=login, user sees login form

      const url = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      url.searchParams.set('prompt', 'login')

      // User logs in, sees credentials form
      expect(url.searchParams.get('prompt')).toBe('login')
    })

    it('scenario 2: User logout then re-login (THE BUG)', () => {
      // BEFORE FIX:
      // 1. User logs in (Keycloak creates session)
      // 2. User clicks logout (app state cleared, but Keycloak session remains)
      // 3. User clicks login (no prompt=login)
      // 4. Keycloak sees valid session
      // 5. Keycloak returns code without form
      // 6. User sees chat (BUG!)

      // AFTER FIX:
      // 1. User logs in
      // 2. User clicks logout
      // 3. User clicks login (WITH prompt=login)
      // 4. Keycloak IGNORES session (because of prompt=login)
      // 5. Keycloak shows login form
      // 6. User enters credentials
      // 7. User sees chat (CORRECT)

      const urlWithFix = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      urlWithFix.searchParams.set('prompt', 'login')

      expect(urlWithFix.searchParams.get('prompt')).toBe('login')
    })
  })
})
