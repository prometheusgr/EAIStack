import { describe, it, expect } from 'vitest'
import {
  decodeJwt,
  buildKeycloakLoginUrl,
  buildKeycloakLogoutUrl,
  AuthTokenPayload,
} from '../../src/auth/authHelpers'

describe('authHelpers', () => {
  describe('decodeJwt', () => {
    it('decodes valid JWT successfully', () => {
      const token = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLTEyMyIsInByZWZlcnJlZF91c2VybmFtZSI6InRlc3R1c2VyIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwibmFtZSI6IlRlc3QgVXNlciIsImV4cCI6OTk5OTk5OTk5OX0.invalid_sig'

      const payload = decodeJwt(token)

      expect(payload.sub).toBe('user-123')
      expect(payload.preferred_username).toBe('testuser')
      expect(payload.email).toBe('test@example.com')
      expect(payload.name).toBe('Test User')
      expect(payload.exp).toBe(9999999999)
    })

    it('handles missing optional claims', () => {
      const token = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLTEyMyIsInByZWZlcnJlZF91c2VybmFtZSI6InRlc3R1c2VyIiwiZXhwIjo5OTk5OTk5OTk5fQ.invalid_sig'

      const payload = decodeJwt(token)

      expect(payload.sub).toBe('user-123')
      expect(payload.email).toBeUndefined()
      expect(payload.name).toBeUndefined()
    })

    it('throws on malformed input', () => {
      expect(() => decodeJwt('not.a.token')).toThrow()
      expect(() => decodeJwt('invalid')).toThrow()
      expect(() => decodeJwt('')).toThrow()
    })
  })

  describe('buildKeycloakLoginUrl', () => {
    it('builds login URL with all required parameters', () => {
      const url = buildKeycloakLoginUrl('http://localhost:8080/', 'http://localhost:3000/')

      expect(url).toContain('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      expect(url).toContain('client_id=eaistack-web')
      expect(url).toContain('redirect_uri=http%3A%2F%2Flocalhost%3A3000%2F')
      expect(url).toContain('response_type=code')
      expect(url).toContain('response_mode=query')
      expect(url).toContain('scope=openid+profile+email')
      expect(url).toContain('prompt=login')
    })

    it('includes prompt=login for bug fix', () => {
      const url = buildKeycloakLoginUrl('http://localhost:8080/', 'http://localhost:3000/')
      expect(url).toContain('prompt=login')
    })

    it('handles Keycloak URL with trailing slash', () => {
      const url = buildKeycloakLoginUrl('http://localhost:8080/', 'http://localhost:3000/')
      expect(url).toContain('http://localhost:8080/realms/eaistack')
    })

    it('handles Keycloak URL without trailing slash', () => {
      const url = buildKeycloakLoginUrl('http://localhost:8080', 'http://localhost:3000/')
      expect(url).toContain('http://localhost:8080/realms/eaistack')
    })
  })

  describe('buildKeycloakLogoutUrl', () => {
    it('builds logout URL with redirect_uri', () => {
      const url = buildKeycloakLogoutUrl('http://localhost:8080/', 'http://localhost:3000/')

      expect(url).toContain('http://localhost:8080/realms/eaistack/protocol/openid-connect/logout')
      expect(url).toContain('redirect_uri=http%3A%2F%2Flocalhost%3A3000%2F')
    })

    it('does not include prompt parameter', () => {
      const url = buildKeycloakLogoutUrl('http://localhost:8080/', 'http://localhost:3000/')
      expect(url).not.toContain('prompt')
    })

    it('handles Keycloak URL with trailing slash', () => {
      const url = buildKeycloakLogoutUrl('http://localhost:8080/', 'http://localhost:3000/')
      expect(url).toContain('http://localhost:8080/realms/eaistack')
    })

    it('handles Keycloak URL without trailing slash', () => {
      const url = buildKeycloakLogoutUrl('http://localhost:8080', 'http://localhost:3000/')
      expect(url).toContain('http://localhost:8080/realms/eaistack')
    })
  })
})
