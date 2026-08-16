import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import Keycloak from 'keycloak-js'

interface AuthContextType {
  keycloak: Keycloak.KeycloakInstance | null
  isAuthenticated: boolean
  isLoading: boolean
  login: () => void
  logout: () => void
  user: any
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [keycloak, setKeycloak] = useState<Keycloak.KeycloakInstance | null>(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [user, setUser] = useState(null)
  const [error, setError] = useState<string | null>(null)
  const [keycloakUrl, setKeycloakUrl] = useState<string>('http://localhost:8080/')

  useEffect(() => {
    const initKeycloak = async () => {
      // Determine Keycloak URL based on environment
      let url = 'http://localhost:8080/'
      if (import.meta.env.VITE_KEYCLOAK_URL) {
        url = import.meta.env.VITE_KEYCLOAK_URL
        if (!url.endsWith('/')) {
          url += '/'
        }
      }
      setKeycloakUrl(url)

      console.log('[Auth] Keycloak URL:', url)

      const kc = new Keycloak({
        url: url,
        realm: 'eaistack',
        clientId: 'eaistack-web',
      })

      try {
        // Check for authorization code from Keycloak redirect
        console.log('[Auth] Init: Checking for code in URL...', window.location.search)
        const urlParams = new URLSearchParams(window.location.search)
        const code = urlParams.get('code')
        const error = urlParams.get('error')
        const state = urlParams.get('state')

        console.log('[Auth] Init: code=', code ? 'present' : 'none', 'error=', error, 'state=', state)

        // CRITICAL: Prevent processing old authorization codes after logout
        // Track which authorization codes we've already processed to avoid reusing them
        const processedCodesKey = 'auth_processed_codes'
        const processedCodes = new Set(JSON.parse(sessionStorage.getItem(processedCodesKey) || '[]'))

        if (code) {
          if (processedCodes.has(code)) {
            console.log('[Auth] Authorization code already processed, ignoring to prevent replay.')
            // Clean the URL to prevent this code from being processed again
            window.history.replaceState(null, '', window.location.pathname)
          } else {
            console.log('[Auth] New authorization code, will process')
            processedCodes.add(code)
            sessionStorage.setItem(processedCodesKey, JSON.stringify(Array.from(processedCodes)))
          }
        }

        // Handle authorization code exchange
        if (code && !processedCodes.has(code)) {
          console.log('[Auth] Authorization code detected, exchanging for token...')

          // Exchange code for token via backend
          try {
            const tokenResponse = await fetch('/api/auth/token', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                code,
                redirect_uri: window.location.origin + '/',
              }),
            })

            if (tokenResponse.ok) {
              const tokenData = await tokenResponse.json()
              console.log('[Auth] Token received:', tokenData.access_token ? 'success' : 'no token')

              // Store token for future requests
              if (tokenData.access_token) {
                localStorage.setItem('access_token', tokenData.access_token)
                localStorage.setItem('token_type', tokenData.token_type || 'Bearer')
                if (tokenData.refresh_token) {
                  localStorage.setItem('refresh_token', tokenData.refresh_token)
                }

                // Parse token to extract user info
                try {
                  // Decode JWT without verification (we trust it from our backend)
                  const tokenParts = tokenData.access_token.split('.')
                  if (tokenParts.length === 3) {
                    const payload = JSON.parse(
                      atob(tokenParts[1].replace(/-/g, '+').replace(/_/g, '/'))
                    )
                    console.log('[Auth] Token payload:', payload.preferred_username)

                    // Set token on keycloak instance so ChatWindow can access it
                    kc.token = tokenData.access_token
                    kc.tokenParsed = payload

                    // Update auth state
                    setKeycloak(kc)
                    setIsAuthenticated(true)
                    setUser({
                      username: payload.preferred_username,
                      email: payload.email,
                      name: payload.name,
                    })
                    console.log('[Auth] Auth state updated, user:', payload.preferred_username)
                  }
                } catch (parseErr) {
                  console.warn('[Auth] Could not parse token:', parseErr)
                }
              }

              // Clean URL to prevent re-processing
              window.history.replaceState(null, '', window.location.pathname)

              console.log('[Auth] Token exchanged successfully')
              // Don't redirect - just return and let React re-render with updated auth state
              setIsLoading(false)
              return
            } else {
              console.error('[Auth] Token exchange failed:', tokenResponse.status)
              setError('Login failed. Please try again.')
            }
          } catch (exchangeErr) {
            console.error('[Auth] Code exchange error:', exchangeErr)
            setError('Login failed. Please try again.')
          }

          // Clean URL even if exchange failed
          window.history.replaceState(null, '', window.location.pathname)
        }

        // Handle login_required error
        if (error) {
          console.warn('[Auth] Detected error:', error)
          setError(error === 'login_required' ? 'Login required' : error)
          // Clean URL to prevent re-processing
          window.history.replaceState(null, '', window.location.pathname)
        }

        // Check if we already have a stored token from previous login
        const storedToken = localStorage.getItem('access_token')
        if (storedToken) {
          console.log('[Auth] Found stored token, using it')
          try {
            const tokenParts = storedToken.split('.')
            if (tokenParts.length === 3) {
              const payload = JSON.parse(
                atob(tokenParts[1].replace(/-/g, '+').replace(/_/g, '/'))
              )
              // Set keycloak.token so ChatWindow can access it
              kc.token = storedToken
              kc.tokenParsed = payload
              setKeycloak(kc)
              setIsAuthenticated(true)
              setUser({
                username: payload.preferred_username,
                email: payload.email,
                name: payload.name,
              })
              console.log('[Auth] Restored user from stored token:', payload.preferred_username)
              setIsLoading(false)
              return
            }
          } catch (parseErr) {
            console.warn('[Auth] Could not parse stored token:', parseErr)
            // Fall through to normal init
          }
        }

        // Initialize Keycloak without triggering any redirects or session checks
        // DO NOT specify onLoad - when omitted, Keycloak just checks for existing token
        // without any automatic redirects or SSO checks
        const kcAuthenticated = await kc.init({
          checkLoginIframe: false, // Disable iframe-based session check (can cause redirects)
          // Note: onLoad is intentionally omitted. Valid values are 'login-required' or 'check-sso',
          // but both can cause redirects. Omitting onLoad means just check localStorage.
          pkceMethod: 'S256',
        })

        console.log('[Auth] Init complete, keycloak says authenticated:', kcAuthenticated)

        // CRITICAL: Use localStorage as SOLE source of truth, not Keycloak session cookie
        // Reason: After logout, Keycloak's session cookie persists. We only trust localStorage.
        // If localStorage has no token, we are NOT authenticated, period.
        const tokenFromStorage = localStorage.getItem('access_token')
        const appAuthenticated = !!tokenFromStorage

        console.log('[Auth] App authentication state:', { tokenStored: !!tokenFromStorage, kcAuthenticated, appAuthenticated })

        // CRITICAL: Clear Keycloak instance token if localStorage has no token
        // This ensures we never use Keycloak's session as source of truth
        if (!appAuthenticated && kc.token) {
          console.log('[Auth] Clearing Keycloak token because localStorage is empty')
          kc.token = undefined
          kc.tokenParsed = undefined
        }

        setKeycloak(kc)
        setIsAuthenticated(appAuthenticated)

        if (appAuthenticated && tokenFromStorage) {
          try {
            const tokenParts = tokenFromStorage.split('.')
            if (tokenParts.length === 3) {
              const payload = JSON.parse(
                atob(tokenParts[1].replace(/-/g, '+').replace(/_/g, '/'))
              )
              setUser({
                username: payload.preferred_username,
                email: payload.email,
                name: payload.name,
              })
              console.log('[Auth] User logged in:', payload.preferred_username)
              setError(null)
            }
          } catch (err) {
            console.warn('[Auth] Could not parse stored token:', err)
            setUser(null)
          }
        } else if (!appAuthenticated) {
          setUser(null)
          console.log('[Auth] Not authenticated (no stored token in localStorage)')
        }
      } catch (err) {
        console.error('[Auth] Keycloak init failed:', err)
        setError(err instanceof Error ? err.message : 'Initialization failed')
        setKeycloak(kc)
        setIsAuthenticated(false)
      } finally {
        setIsLoading(false)
      }
    }
    initKeycloak()
  }, [])

  const login = () => {
    console.log('[Auth] login() - redirecting to Keycloak')

    try {
      const baseUrl = keycloakUrl.replace(/\/$/, '')
      const keycloakAuthUrl = new URL(`${baseUrl}/realms/eaistack/protocol/openid-connect/auth`)

      // Standard OIDC authorization code flow
      keycloakAuthUrl.searchParams.set('client_id', 'eaistack-web')
      keycloakAuthUrl.searchParams.set('redirect_uri', window.location.origin + '/')
      keycloakAuthUrl.searchParams.set('response_type', 'code')
      keycloakAuthUrl.searchParams.set('response_mode', 'query')
      keycloakAuthUrl.searchParams.set('scope', 'openid profile email')
      keycloakAuthUrl.searchParams.set('state', 'eaistack-' + Date.now())
      // Force Keycloak to show login screen even if session exists
      // According to OIDC spec, prompt=login means "end any existing session and show login"
      keycloakAuthUrl.searchParams.set('prompt', 'login')

      console.log('[Auth] Redirecting to:', keycloakAuthUrl.href.substring(0, 80))
      window.location.href = keycloakAuthUrl.href
    } catch (err) {
      console.error('[Auth] login() error:', err)
    }
  }

  const logout = () => {
    console.log('[Auth] logout() - clearing session')

    // Clear ALL tokens from localStorage IMMEDIATELY
    localStorage.removeItem('access_token')
    localStorage.removeItem('token_type')
    localStorage.removeItem('refresh_token')
    sessionStorage.clear()

    // Update React state to logged out
    setIsAuthenticated(false)
    setUser(null)
    setKeycloak(null)

    // Strategy: Redirect directly to Keycloak auth endpoint with prompt=logout
    // This is a non-standard but effective way to ensure Keycloak destroys the session before redirect
    // According to Keycloak source, this pattern works better than the logout endpoint
    try {
      const baseUrl = keycloakUrl.replace(/\/$/, '')
      // First: logout endpoint to clear server-side session
      window.location.href = `${baseUrl}/realms/eaistack/protocol/openid-connect/logout?redirect_uri=${encodeURIComponent(window.location.origin + '/')}`
    } catch (err) {
      console.error('[Auth] Logout failed:', err)
    }
  }

  return (
    <AuthContext.Provider value={{ keycloak, isAuthenticated, isLoading, login, logout, user }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
