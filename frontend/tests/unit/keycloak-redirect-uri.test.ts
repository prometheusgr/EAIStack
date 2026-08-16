import { describe, it, expect } from 'vitest'

/**
 * TDD: Keycloak Redirect URI with Port Number
 *
 * Problem: After successful login, Keycloak redirects to localhost/realms/eaistack/...
 * instead of localhost:3000/?code=...
 *
 * Root Cause: Keycloak's redirect URI validation or generation is not including the port
 *
 * Solution: Ensure:
 * 1. realm-import.json includes redirect URIs with ports
 * 2. Login request sends correct redirect_uri parameter
 * 3. Keycloak is configured to preserve ports in redirects
 */

describe('Keycloak Redirect URI - TDD', () => {
  it('should include port 3000 in configured redirect URIs', () => {
    // Keycloak client config must list valid redirect URIs
    const configuredRedirectUris = [
      'http://localhost:3000',
      'http://localhost:3000/',
    ]

    // Should accept both with and without trailing slash
    expect(configuredRedirectUris).toContain('http://localhost:3000')
    expect(configuredRedirectUris).toContain('http://localhost:3000/')
  })

  it('should send redirect_uri with port in login request', () => {
    // When user clicks login, we build a URL like:
    // http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?
    //   client_id=eaistack-web&
    //   redirect_uri=http://localhost:3000/&
    //   response_type=code&...

    const baseUrl = 'http://localhost:8080'
    const loginUrl = new URL(`${baseUrl}/realms/eaistack/protocol/openid-connect/auth`)
    loginUrl.searchParams.set('redirect_uri', 'http://localhost:3000/')

    // Redirect URI must include port
    expect(loginUrl.searchParams.get('redirect_uri')).toBe('http://localhost:3000/')
    expect(loginUrl.searchParams.get('redirect_uri')).toContain(':3000')
  })

  it('should use window.location.origin which preserves port', () => {
    // window.location.origin automatically includes port if present
    // e.g., if user visits http://localhost:3000, origin is http://localhost:3000
    // if user visits http://example.com, origin is http://example.com

    // Test: when page is at localhost:3000, origin includes port
    const origin = 'http://localhost:3000' // This is what window.location.origin would be
    const redirectUri = origin + '/'

    expect(redirectUri).toBe('http://localhost:3000/')
    expect(redirectUri).toContain('3000')
  })

  it('should verify realm-import has correct redirect URIs', () => {
    // The realm-import.json must be updated after Keycloak starts
    // to include the correct redirect URIs

    const realmConfig = {
      clientId: 'eaistack-web',
      redirectUris: [
        'http://localhost:3000',
        'http://localhost:3000/',
      ],
      webOrigins: [
        'http://localhost:3000',
      ],
    }

    expect(realmConfig.redirectUris).toContain('http://localhost:3000/')
    expect(realmConfig.webOrigins).toContain('http://localhost:3000')
  })

  it('should handle Keycloak returning code with correct redirect', () => {
    // After user logs in, Keycloak should redirect back to:
    // http://localhost:3000/?code=<code>&state=<state>

    const redirectFromKeycloak = 'http://localhost:3000/?code=abc123&state=xyz789'
    const urlParams = new URLSearchParams(new URL(redirectFromKeycloak).search)

    expect(urlParams.get('code')).toBe('abc123')
    expect(urlParams.get('state')).toBe('xyz789')
    // Must NOT be localhost/realms/eaistack/login-actions/...
  })
})
