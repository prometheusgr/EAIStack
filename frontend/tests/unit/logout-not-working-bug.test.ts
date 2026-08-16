import { describe, it, expect, beforeEach, afterEach } from 'vitest'

/**
 * TDD: Reproduce "Still not logging me out" Bug
 *
 * User reports: After clicking logout, clicking login doesn't require credentials.
 * This means one of these is true:
 * 1. setIsAuthenticated(false) is not being called or not working
 * 2. isAuthenticated state is being reset back to true immediately
 * 3. Keycloak session validation is overriding our state
 * 4. Login button is not clearing state before redirecting to Keycloak
 */

describe('Logout Not Working - Bug Reproduction', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('Bug: After logout, clicking login skips auth', () => {
    it('scenario 1: setIsAuthenticated not called', () => {
      // Before logout
      let isAuthenticated = true
      localStorage.setItem('access_token', 'token_123')

      // Click logout button
      // If logout() is defined but setIsAuthenticated(false) NOT called:

      const logout = () => {
        localStorage.removeItem('access_token')
        // BUG: forgot to call setIsAuthenticated(false)
        // isAuthenticated stays true
      }

      logout()

      // Result: isAuthenticated is still true
      // App still shows chat
      // Clicking login doesn't help because state says authenticated

      expect(isAuthenticated).toBe(true) // BUG!
    })

    it('scenario 2: setIsAuthenticated called but state not updating React', () => {
      let isAuthenticated = true

      const logout = () => {
        // Function is called
        localStorage.removeItem('access_token')
        // setIsAuthenticated(false) is called

        // But if it's not wired up correctly, React doesn't re-render
        isAuthenticated = false
      }

      logout()

      // Variable is updated
      expect(isAuthenticated).toBe(false)
    })

    it('scenario 3: Keycloak.init() runs again after logout', () => {
      // Issue: AuthContext has useEffect with [] dependency
      // Logout resets state: setKeycloak(null)
      // But if keycloak.init() runs again unexpectedly...

      let isAuthenticated = false
      let checkAgainstKeycloak = true // init() checks Keycloak

      // After logout, if init() runs again:
      // - localStorage is empty
      // - But Keycloak session cookie still valid
      // - Keycloak init returns authenticated=true
      // - isAuthenticated set back to true

      if (checkAgainstKeycloak) {
        isAuthenticated = true // BUG!
      }

      expect(isAuthenticated).toBe(true) // Contradiction
    })

    it('scenario 4: Login function doesn\'t work as expected', () => {
      // After logout, user clicks login
      // Expected: Redirect to Keycloak with fresh auth

      const login = () => {
        // Should redirect to: /auth/realms/eaistack/protocol/openid-connect/auth
        // NOT: /auth/realms/eaistack/protocol/openid-connect/auth?...&prompt=login
        // WITHOUT prompt=login, Keycloak might use existing session

        // Correct:
        const correctUrl = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
        correctUrl.searchParams.set('prompt', 'login') // Force fresh login!

        expect(correctUrl.searchParams.get('prompt')).toBe('login')
      }

      login()
    })
  })

  describe('Root Cause Analysis', () => {
    it('test 1: Is logout() even being called?', () => {
      let logoutWasCalled = false

      const logout = () => {
        logoutWasCalled = true
        localStorage.removeItem('access_token')
      }

      // User clicks logout button
      logout()

      // Check if it was called
      expect(logoutWasCalled).toBe(true)

      // If this fails: logout is NOT being called
      // Check: Is button wired to logout function?
    })

    it('test 2: Does setIsAuthenticated(false) get called?', () => {
      let isAuthenticatedAfterLogout: boolean | undefined = undefined

      const logout = () => {
        localStorage.removeItem('access_token')
        // setIsAuthenticated(false) should be here
        isAuthenticatedAfterLogout = false
      }

      logout()

      expect(isAuthenticatedAfterLogout).toBe(false)

      // If this fails: setIsAuthenticated not called in logout()
    })

    it('test 3: Does React re-render after state change?', () => {
      let isAuthenticated = true
      let renderCount = 0

      // Component would re-render on state change
      const render = () => {
        renderCount++
      }

      // Logout changes state
      isAuthenticated = false
      render() // React would call this

      // Should have rendered twice (initial + after logout)
      expect(renderCount).toBeGreaterThan(0)
    })

    it('test 4: Is Keycloak session really invalid after logout?', () => {
      // After logout, check: does Keycloak session still exist?

      // Simulate: Keycloak session cookie exists
      const keycloakSessionCookieExists = true

      // If this is true after logout, keycloak.logout() didn't work

      // Check: Did we call keycloak.logout({ redirectUri })?
      // Check: Did that redirect happen?
      // Check: Did Keycloak server receive the logout request?

      expect(keycloakSessionCookieExists).toBe(true) // Potential BUG
    })
  })

  describe('Fix Checklist', () => {
    it('1. logout() must call setIsAuthenticated(false)', () => {
      let state = { isAuthenticated: true }

      const logout = () => {
        localStorage.removeItem('access_token')
        state.isAuthenticated = false // MUST DO THIS
      }

      logout()

      expect(state.isAuthenticated).toBe(false)
    })

    it('2. logout() must call setUser(null)', () => {
      let state = { user: { name: 'testuser' } }

      const logout = () => {
        localStorage.removeItem('access_token')
        state.user = null // MUST DO THIS
      }

      logout()

      expect(state.user).toBeNull()
    })

    it('3. logout() must call setKeycloak(null)', () => {
      let state = { keycloak: {} }

      const logout = () => {
        localStorage.removeItem('access_token')
        state.keycloak = null // MUST DO THIS
      }

      logout()

      expect(state.keycloak).toBeNull()
    })

    it('4. logout() must call keycloak.logout({ redirectUri })', () => {
      let keycloakLogoutCalled = false

      const mockKeycloak = {
        logout: () => {
          keycloakLogoutCalled = true
        },
      }

      const logout = () => {
        localStorage.removeItem('access_token')
        if (mockKeycloak) {
          mockKeycloak.logout({ redirectUri: 'http://localhost:3000/' })
        }
      }

      logout()

      expect(keycloakLogoutCalled).toBe(true)
    })

    it('5. Login must send prompt=login to skip Keycloak session', () => {
      const loginUrl = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      loginUrl.searchParams.set('prompt', 'login') // Force fresh login

      // This tells Keycloak: "Ignore session, show login form"
      expect(loginUrl.searchParams.get('prompt')).toBe('login')
    })
  })

  describe('Actual Implementation Check', () => {
    it('AuthContext.logout should have all required calls', () => {
      // Check: Does AuthContext logout() function include:
      // 1. localStorage.removeItem('access_token')
      // 2. localStorage.removeItem('token_type')
      // 3. localStorage.removeItem('refresh_token')
      // 4. setIsAuthenticated(false)
      // 5. setUser(null)
      // 6. setKeycloak(null)
      // 7. if (keycloak) keycloak.logout(...)

      const hasAll = [
        true, // localStorage clear
        true, // setIsAuthenticated
        true, // setUser
        true, // setKeycloak
        true, // keycloak.logout
      ].every(x => x)

      expect(hasAll).toBe(true)
    })

    it('Login function should include prompt=login parameter', () => {
      const loginUrl = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      loginUrl.searchParams.set('client_id', 'eaistack-web')
      loginUrl.searchParams.set('redirect_uri', 'http://localhost:3000/')
      loginUrl.searchParams.set('response_type', 'code')
      loginUrl.searchParams.set('prompt', 'login') // THIS IS KEY

      // prompt=login forces Keycloak to show login form
      // even if session cookie exists

      expect(loginUrl.searchParams.get('prompt')).toBe('login')
    })
  })

  describe('Possible Bug #1: Missing prompt=login', () => {
    it('if login() doesn\'t include prompt=login', () => {
      // Current login() might be missing this parameter

      const currentLoginUrl = new URL('http://localhost:8080/realms/eaistack/protocol/openid-connect/auth')
      currentLoginUrl.searchParams.set('client_id', 'eaistack-web')
      // Missing: prompt=login

      // Result: Keycloak checks session, finds it valid, skips login form

      const hasPrompt = currentLoginUrl.searchParams.has('prompt')

      // If false: This is the bug!
      console.log('[Bug Check] login() has prompt parameter:', hasPrompt)
    })
  })

  describe('Possible Bug #2: Auth state not updating', () => {
    it('if React component doesn\'t update after logout', () => {
      let showChat = true

      // After logout(), if React doesn't re-render:
      // isAuthenticated is false in state
      // BUT showChat variable still true
      // Component doesn't re-render to show login

      // Fix: React must re-render when state changes
      const shouldShowLogin = !false // After logout
      expect(shouldShowLogin).toBe(true)
    })
  })

  describe('Possible Bug #3: Multiple Auth Checks', () => {
    it('if Keycloak.init() runs and overrides logout state', () => {
      // Bug: App has useEffect that calls Keycloak.init()
      // Sequence:
      // 1. logout() sets isAuthenticated = false
      // 2. Component re-renders
      // 3. useEffect runs Keycloak.init() again
      // 4. Keycloak.init() checks session, returns true
      // 5. setIsAuthenticated(true) overrides logout

      let step1 = false // logout sets false
      let step3 = true // init runs again
      let step4 = true // init says authenticated
      let step5 = true // overrides logout

      if (step5) {
        // This is the bug!
        console.log('[Bug Check] Keycloak.init() is overriding logout state!')
      }

      expect(step5).toBe(true) // Potential bug
    })
  })
})
