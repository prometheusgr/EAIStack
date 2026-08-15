import '@testing-library/jest-dom'

// Mock Keycloak for tests
global.Keycloak = function() {
  return {
    init: () => Promise.resolve(true),
    login: () => {},
    logout: () => {},
    token: 'fake-token',
    subject: 'fake-user-id',
  }
} as any
