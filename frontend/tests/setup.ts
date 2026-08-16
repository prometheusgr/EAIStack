import '@testing-library/jest-dom'

declare global {
  var Keycloak: any
}

// Mock Keycloak for tests
globalThis.Keycloak = function() {
  return {
    init: () => Promise.resolve(true),
    login: () => {},
    logout: () => {},
    token: 'fake-token',
    subject: 'fake-user-id',
  }
} as any
