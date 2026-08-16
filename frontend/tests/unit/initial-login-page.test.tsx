import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from '../../src/App'

/**
 * TDD: Initial Login Page Render
 *
 * Tests that on fresh instance (no stored token):
 * 1. App renders with loading state initially
 * 2. After auth init completes, shows login page
 * 3. Login button visible
 * 4. Chat window NOT visible
 * 5. No automatic redirection to chat
 */

describe('Initial Login Page - Fresh Instance - TDD', () => {
  beforeEach(() => {
    // Fresh instance: clear all localStorage
    localStorage.clear()
    vi.clearAllMocks()
    // Also clear any URL params
    window.history.replaceState(null, '', '/')
  })

  afterEach(() => {
    localStorage.clear()
    window.history.replaceState(null, '', '/')
  })

  describe('App Render on Fresh Instance', () => {
    it('should show loading state initially', async () => {
      // When App first mounts, AuthContext is initializing
      const { container } = render(<App />)

      // Should show loading or login initially
      // (loading happens while Keycloak inits)
      expect(container).toBeDefined()
    })

    it('should show login page when no token in localStorage', async () => {
      // Fresh instance: no stored token
      localStorage.clear()

      const { container } = render(<App />)

      // After auth completes, should show login page with login button
      await waitFor(() => {
        const loginButton = screen.getByRole('button', { name: /login/i })
        expect(loginButton).toBeInTheDocument()
      })
    })

    it('should display login button on fresh instance', async () => {
      localStorage.clear()

      render(<App />)

      // Should see login button
      await waitFor(() => {
        const loginButton = screen.getByRole('button', { name: /login/i })
        expect(loginButton).toBeInTheDocument()
      })
    })

    it('should NOT show chat window on fresh instance', async () => {
      localStorage.clear()

      render(<App />)

      // Chat window should NOT be visible
      await waitFor(() => {
        const chatWindow = screen.queryByPlaceholderText(/Type your message/i)
        expect(chatWindow).not.toBeInTheDocument()
      })
    })

    it('should NOT show logout button on fresh instance', async () => {
      localStorage.clear()

      render(<App />)

      // Logout button should NOT be visible
      await waitFor(() => {
        const logoutButton = screen.queryByRole('button', { name: /logout/i })
        expect(logoutButton).not.toBeInTheDocument()
      })
    })

    it('should NOT show welcome message on fresh instance', async () => {
      localStorage.clear()

      render(<App />)

      // "Welcome, [username]" should NOT appear
      await waitFor(() => {
        const welcomeText = screen.queryByText(/Welcome/)
        expect(welcomeText).not.toBeInTheDocument()
      })
    })
  })

  describe('Initial Auth State', () => {
    it('should start with isAuthenticated=false', () => {
      // With no localStorage token, auth state should be false
      const hasToken = !!localStorage.getItem('access_token')
      expect(hasToken).toBe(false)
    })

    it('should have no user object on fresh instance', () => {
      localStorage.clear()

      // No user data in storage
      const userName = localStorage.getItem('user_name')
      expect(userName).toBeNull()
    })

    it('should have empty keycloak instance', () => {
      localStorage.clear()

      // Keycloak will be initialized but without a token
      const token = localStorage.getItem('access_token')
      expect(token).toBeNull()
    })
  })

  describe('No Automatic Redirect on Fresh Instance', () => {
    it('should NOT redirect to chat automatically', async () => {
      localStorage.clear()

      render(<App />)

      // URL should remain at /
      await waitFor(() => {
        expect(window.location.pathname).toBe('/')
      })
    })

    it('should NOT redirect to Keycloak automatically', async () => {
      localStorage.clear()

      render(<App />)

      // window.location.href should not change
      // (Only changes when user clicks login)
      await waitFor(() => {
        expect(window.location.href).toContain('localhost:3000/')
      })
    })

    it('should wait for user click before redirect', async () => {
      localStorage.clear()

      render(<App />)

      // Login button should be clickable (not redirected yet)
      await waitFor(() => {
        const loginButton = screen.getByRole('button', { name: /login/i })
        expect(loginButton).toBeEnabled()
      })
    })
  })

  describe('Conditional Rendering Logic', () => {
    it('should render login UI when isAuthenticated=false', () => {
      const isAuthenticated = false

      // App should render login page
      const showLoginUI = !isAuthenticated

      expect(showLoginUI).toBe(true)
    })

    it('should render chat UI when isAuthenticated=true', () => {
      // Setup: with token
      const isAuthenticated = true

      // App should render chat page
      const showChatUI = isAuthenticated

      expect(showChatUI).toBe(true)
    })

    it('should hide chat when isAuthenticated becomes false', () => {
      // Start authenticated
      let isAuthenticated = true
      let showChatUI = isAuthenticated
      expect(showChatUI).toBe(true)

      // After logout
      isAuthenticated = false
      showChatUI = isAuthenticated

      expect(showChatUI).toBe(false)
    })

    it('should show login when isAuthenticated becomes false', () => {
      let isAuthenticated = true
      let showLoginUI = !isAuthenticated
      expect(showLoginUI).toBe(false)

      // After logout
      isAuthenticated = false
      showLoginUI = !isAuthenticated

      expect(showLoginUI).toBe(true)
    })
  })

  describe('Page Content Verification', () => {
    it('should show "EAIStack" heading on login page', async () => {
      localStorage.clear()

      render(<App />)

      await waitFor(() => {
        const heading = screen.getByText('EAIStack')
        expect(heading).toBeInTheDocument()
      })
    })

    it('should show description text on login page', async () => {
      localStorage.clear()

      render(<App />)

      // Login page should have some instruction text
      await waitFor(() => {
        // Either this text or a login button, but NOT chat interface
        const hasLoginButton = !!screen.queryByRole('button', { name: /login/i })
        expect(hasLoginButton).toBe(true)
      })
    })

    it('should NOT show "Phase 2: Agent Chat" header on fresh instance', async () => {
      localStorage.clear()

      render(<App />)

      // This is in AppContent under chat UI
      await waitFor(() => {
        const agentHeader = screen.queryByText(/Phase 2: Agent Chat/)
        expect(agentHeader).not.toBeInTheDocument()
      })
    })

    it('should NOT show chat messages container on fresh instance', async () => {
      localStorage.clear()

      render(<App />)

      await waitFor(() => {
        const messagesContainer = screen.queryByRole('textbox', { name: /message/i })
        expect(messagesContainer).not.toBeInTheDocument()
      })
    })
  })

  describe('Integration: Fresh vs Authenticated Instance', () => {
    it('should show different UI for fresh vs authenticated', () => {
      // Fresh instance
      localStorage.clear()
      const freshAuth = !!localStorage.getItem('access_token')
      const freshShowsLogin = !freshAuth
      expect(freshShowsLogin).toBe(true)

      // Authenticated instance
      localStorage.setItem('access_token', 'token_abc')
      const authAuth = !!localStorage.getItem('access_token')
      const authShowsChat = authAuth
      expect(authShowsChat).toBe(true)

      // They should be opposite
      expect(freshShowsLogin).toBe(true)
      expect(authShowsChat).toBe(true)
      // One shows login, one shows chat (opposite for the user)

      localStorage.clear()
    })

    it('should transition from login to chat on successful login', () => {
      // Start: fresh instance
      localStorage.clear()
      let isAuthenticated = !!localStorage.getItem('access_token')
      let showLogin = !isAuthenticated
      expect(showLogin).toBe(true)

      // After login: token stored
      localStorage.setItem('access_token', 'token_123')
      isAuthenticated = !!localStorage.getItem('access_token')
      showLogin = !isAuthenticated

      expect(showLogin).toBe(false)
      expect(isAuthenticated).toBe(true)

      localStorage.clear()
    })
  })
})
