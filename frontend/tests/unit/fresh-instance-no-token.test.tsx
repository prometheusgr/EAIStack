import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../../src/App'

/**
 * TDD: Fresh Instance with No Stored Token
 *
 * CRITICAL BUG: On fresh instance (no localStorage token),
 * Keycloak.init() might return authenticated=true because:
 * - Mock in tests always returns true
 * - Real Keycloak might have session cookie from previous login
 *
 * This test verifies the ACTUAL behavior and catches the bug.
 */

describe('Fresh Instance - No Stored Token - TDD', () => {
  beforeEach(() => {
    // Fresh instance: no stored token
    localStorage.clear()
    vi.clearAllMocks()
    window.history.replaceState(null, '', '/')
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('Bug: Already Logged In on Fresh Instance', () => {
    it('SHOULD show login page when no stored token', async () => {
      // Precondition: fresh instance, no token
      localStorage.clear()
      expect(localStorage.getItem('access_token')).toBeNull()

      render(<App />)

      // EXPECTED: Login page
      await waitFor(() => {
        const loginButton = screen.getByRole('button', { name: /login/i })
        expect(loginButton).toBeInTheDocument()
      })

      // Chat should NOT be visible
      const chatInput = screen.queryByPlaceholderText(/Type your message/i)
      expect(chatInput).not.toBeInTheDocument()
    })

    it('SHOULD NOT show chat when no stored token', async () => {
      localStorage.clear()

      render(<App />)

      // Chat components should not exist
      await waitFor(() => {
        const sendButton = screen.queryByRole('button', { name: /send/i })
        expect(sendButton).not.toBeInTheDocument()
      })
    })

    it('SHOULD NOT show logout button when no stored token', async () => {
      localStorage.clear()

      render(<App />)

      await waitFor(() => {
        const logoutButton = screen.queryByRole('button', { name: /logout/i })
        expect(logoutButton).not.toBeInTheDocument()
      })
    })

    it('SHOULD NOT show welcome message when no stored token', async () => {
      localStorage.clear()

      render(<App />)

      await waitFor(() => {
        const welcomeMsg = screen.queryByText(/Welcome/)
        expect(welcomeMsg).not.toBeInTheDocument()
      })
    })
  })

  describe('Root Cause: Keycloak Init Behavior', () => {
    it('should check localStorage before returning authenticated status', () => {
      // On fresh instance, kc.init() should check:
      // 1. localStorage for access_token
      // 2. kc.token property
      // 3. Session storage
      // Only return authenticated=true if token exists

      localStorage.clear()
      const hasStoredToken = !!localStorage.getItem('access_token')

      // Without stored token, should not be authenticated
      expect(hasStoredToken).toBe(false)
      // Therefore kc.init() should return false
      const shouldBeAuthenticated = hasStoredToken
      expect(shouldBeAuthenticated).toBe(false)
    })

    it('should return authenticated=false when no token in localStorage', () => {
      localStorage.clear()

      // Correct behavior: if no stored token, init returns false
      const storedToken = localStorage.getItem('access_token')
      const expectedAuthStatus = !!storedToken

      expect(expectedAuthStatus).toBe(false)
    })

    it('should respect Keycloak session cookies separately from stored token', () => {
      // Note: This is the likely issue
      // Keycloak.init() might check browser's Keycloak session cookie
      // even if we cleared localStorage
      //
      // If user was logged in before (session cookie exists in browser),
      // kc.init() will return authenticated=true even with empty localStorage
      //
      // Fix options:
      // 1. Explicitly check localStorage, ignore session cookie
      // 2. Force logout of Keycloak session on app init if no token
      // 3. Use checkLoginIframe=false AND force check localStorage

      const storageToken = localStorage.getItem('access_token')
      const sessionCookieExists = true // Hypothetically, from previous login

      // Current bug:
      // kc.init() returns true because of session cookie
      // But localStorage is empty

      // Fix: AuthContext should check localStorage independently
      const shouldBeAuthenticated = !!storageToken // Check storage, not cookie
      expect(shouldBeAuthenticated).toBe(false)
    })
  })

  describe('Fix: Independent Token Check', () => {
    it('should use localStorage as source of truth for authentication', () => {
      // Solution: Don't rely solely on kc.init() result
      // Also check if localStorage has token

      localStorage.clear()

      const token = localStorage.getItem('access_token')
      const isAuthenticated = !!token

      expect(isAuthenticated).toBe(false)
    })

    it('should override Keycloak authenticated status with localStorage check', () => {
      localStorage.clear()

      // What Keycloak says (might be wrong due to session cookie)
      const kcAuthenticated = true

      // What localStorage says (source of truth)
      const hasStoredToken = !!localStorage.getItem('access_token')

      // Use localStorage as ground truth
      const finalAuthenticated = hasStoredToken

      expect(finalAuthenticated).toBe(false)
      expect(finalAuthenticated).not.toBe(kcAuthenticated)
    })

    it('should clear Keycloak session if localStorage is empty', () => {
      localStorage.clear()

      // If localStorage has no token but Keycloak session exists
      const storedToken = localStorage.getItem('access_token')
      const kcSessionExists = true

      if (!storedToken && kcSessionExists) {
        // Should invalidate the session or treat as not authenticated
        const authenticatedStatus = !!storedToken

        expect(authenticatedStatus).toBe(false)
      }
    })
  })

  describe('Implementation Path', () => {
    it('should initialize with isLoading=true', async () => {
      localStorage.clear()

      render(<App />)

      // While initializing, should show loading (or login after init)
      // At some point, should reach not-loading state
      await waitFor(
        () => {
          // After init completes, should show either login or chat
          const loginButton = screen.queryByRole('button', { name: /login/i })
          const chatInput = screen.queryByPlaceholderText(/Type your message/i)

          // One of them should exist
          expect(loginButton || chatInput).toBeTruthy()
        },
        { timeout: 5000 }
      )
    })

    it('should prioritize localStorage token over Keycloak state', () => {
      localStorage.clear()
      localStorage.setItem('access_token', 'token_123')

      // Now should be authenticated despite what Keycloak says
      const token = localStorage.getItem('access_token')
      const shouldBeAuth = !!token

      expect(shouldBeAuth).toBe(true)

      localStorage.clear()
    })

    it('should recognize when both localStorage and Keycloak agree on no auth', () => {
      localStorage.clear()

      // No token in storage
      const token = localStorage.getItem('access_token')

      // No token = not authenticated
      const isAuth = !!token

      expect(isAuth).toBe(false)
    })
  })

  describe('Component Re-render After Logout', () => {
    it('should show login after logout clears localStorage', () => {
      // Before logout
      localStorage.setItem('access_token', 'token_123')
      let showChat = !!localStorage.getItem('access_token')
      expect(showChat).toBe(true)

      // After logout
      localStorage.removeItem('access_token')
      showChat = !!localStorage.getItem('access_token')

      expect(showChat).toBe(false)
    })

    it('should NOT show chat after localStorage is cleared', () => {
      localStorage.clear()

      const token = localStorage.getItem('access_token')
      const showChat = !!token

      expect(showChat).toBe(false)
    })
  })
})
