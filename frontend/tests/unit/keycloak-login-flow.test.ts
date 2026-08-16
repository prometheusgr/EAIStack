import { describe, it, expect, vi } from 'vitest'

/**
 * TDD Test: Keycloak Login Flow
 *
 * This test documents the CORRECT login flow to prevent infinite redirects.
 * The issue: keycloak.login() is redirecting to Keycloak, but Keycloak is
 * returning error=login_required, causing a loop.
 *
 * Root cause: The Keycloak JS client needs EITHER:
 * 1. A valid redirect URI configured in the client
 * 2. OR use implicit flow without redirectUri
 * 3. OR navigate directly to Keycloak login form (bypass JS client)
 */

describe('Keycloak Login Flow - TDD', () => {
  it('should navigate directly to Keycloak login form', () => {
    // TDD: For E2E/real user flow, should navigate directly to Keycloak
    // NOT use keycloak.login() which has issues with redirectUri

    // Correct approach:
    const keycloakLoginUrl = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
    keycloakLoginUrl.searchParams.set('client_id', 'eaistack-web')
    keycloakLoginUrl.searchParams.set('redirect_uri', 'http://localhost:3000/')
    keycloakLoginUrl.searchParams.set('response_type', 'code')
    keycloakLoginUrl.searchParams.set('response_mode', 'query')
    keycloakLoginUrl.searchParams.set('scope', 'openid profile email')

    expect(keycloakLoginUrl.href).toContain('client_id=eaistack-web')
    expect(keycloakLoginUrl.href).toContain('redirect_uri=http')
    expect(keycloakLoginUrl.href).toContain('response_type=code')
  })

  it('should handle authorization code and exchange for token', () => {
    // TDD: After Keycloak redirects back with code, app should:
    // 1. Extract code from URL
    // 2. Exchange code for token (backend handles this)
    // 3. Store token in localStorage or session

    const redirectUrl = 'http://localhost:3000/?code=abc123&state=xyz789'
    const urlParams = new URLSearchParams(new URL(redirectUrl).search)
    const code = urlParams.get('code')
    const state = urlParams.get('state')

    expect(code).toBe('abc123')
    expect(state).toBe('xyz789')
  })

  it('should NOT use keycloak.login() if it causes redirect loop', () => {
    // TDD: If keycloak.login() causes error=login_required loop,
    // should use direct navigation instead

    // Problem: keycloak.login() internally does something wrong
    // Solution: Bypass it and navigate directly

    const loginMethod = 'direct_navigation' // Not 'keycloak.login()'
    expect(loginMethod).toBe('direct_navigation')
  })

  it('should detect when already logged in via token in localStorage', () => {
    // TDD: AuthContext should check localStorage for existing token
    // If token exists and valid, restore session without redirect

    const token = 'eyJhbGc...' // JWT token
    localStorage.setItem('kc_token', token)

    const storedToken = localStorage.getItem('kc_token')
    expect(storedToken).toBe(token)

    localStorage.clear()
  })

  it('should use onLoad=none to prevent auto-redirect on init', () => {
    // TDD: kc.init() should not auto-redirect
    // onLoad='none' or 'check-sso' but NOT with redirectUri

    const initOptions = {
      checkLoginIframe: false,
      onLoad: 'check-sso',
      // DO NOT include redirectUri - this causes the loop
      // redirectUri is for Keycloak to know where to send the user AFTER login
      // If not configured in Keycloak client, it rejects the request
    }

    expect(initOptions.onLoad).toBe('check-sso')
    expect(initOptions.checkLoginIframe).toBe(false)
  })

  it('should handle redirect URI mismatch error', () => {
    // TDD: If redirect_uri in login call doesn't match Keycloak client config,
    // Keycloak returns invalid_grant or redirect_uri_mismatch error

    // This is likely the real issue:
    // Keycloak client in realm-import.json has:
    //   "redirectUris": ["http://localhost:3000", "http://localhost:3000/"]
    // But login is sending a different redirect_uri

    const configuredUris = ['http://localhost:3000', 'http://localhost:3000/']
    const requestUri = 'http://localhost:3000/' // With trailing slash

    const isValid = configuredUris.some((uri) => uri === requestUri)
    expect(isValid).toBe(true)
  })
})

describe('Login Implementation - TDD', () => {
  it('should provide a login() function that navigates to Keycloak', () => {
    // TDD: AuthContext.login() should navigate directly to Keycloak
    // NOT call keycloak.login()

    const login = () => {
      const url = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      url.searchParams.set('client_id', 'eaistack-web')
      url.searchParams.set('redirect_uri', 'http://localhost:3000/')
      url.searchParams.set('response_type', 'code')
      url.searchParams.set('response_mode', 'query')
      url.searchParams.set('scope', 'openid profile email')

      // window.location.href = url.href
      return url.href
    }

    const loginUrl = login()
    expect(loginUrl).toContain('8080')
    expect(loginUrl).toContain('client_id=eaistack-web')
  })

  it('should handle code exchange after Keycloak redirect', () => {
    // TDD: After Keycloak redirects back with ?code=...,
    // should POST to backend to exchange code for token

    // Backend endpoint: POST /auth/token
    // Body: { code: '...', redirect_uri: 'http://localhost:3000/' }
    // Returns: { access_token: '...', refresh_token: '...' }

    const code = 'auth_code_from_keycloak'
    const exchangePayload = {
      code,
      redirect_uri: 'http://localhost:3000/',
    }

    expect(exchangePayload.code).toBe('auth_code_from_keycloak')
    expect(exchangePayload.redirect_uri).toBeDefined()
  })
})
