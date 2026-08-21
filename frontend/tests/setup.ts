import '@testing-library/jest-dom'

// jsdom doesn't implement these pointer-capture / scroll APIs, but Radix UI's
// Select (and other popover-based primitives) call them during pointer
// interactions. Without these no-op polyfills, clicking a Radix Select in
// tests throws "target.hasPointerCapture is not a function".
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {}
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {}
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

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
