import '@testing-library/jest-dom'

interface MockKeycloakInstance {
  init: () => Promise<boolean>
  login: () => void
  logout: () => void
  token: string
  subject: string
}

declare global {
  // eslint-disable-next-line no-var -- ambient global declarations require `var`
  var Keycloak: new () => MockKeycloakInstance
}

// Mock Keycloak for tests
globalThis.Keycloak = function (this: MockKeycloakInstance) {
  this.init = () => Promise.resolve(true)
  this.login = () => {}
  this.logout = () => {}
  this.token = 'fake-token'
  this.subject = 'fake-user-id'
} as unknown as new () => MockKeycloakInstance
