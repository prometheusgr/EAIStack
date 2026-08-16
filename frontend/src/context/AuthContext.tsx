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
        const urlParams = new URLSearchParams(window.location.search)
        const code = urlParams.get('code')
        const error = urlParams.get('error')
        const state = urlParams.get('state')

        // Handle authorization code exchange
        if (code) {
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

                    // Update auth state
                    setKeycloak(kc)
                    setIsAuthenticated(true)
                    setUser({
                      username: payload.preferred_username,
                      email: payload.email,
                      name: payload.name,
                    })
                  }
                } catch (parseErr) {
                  console.warn('[Auth] Could not parse token:', parseErr)
                }
              }

              // Clean URL to prevent re-processing
              window.history.replaceState(null, '', window.location.pathname)

              // Redirect to chat page
              console.log('[Auth] Token exchanged successfully, redirecting to chat...')
              window.location.href = '/chat'
              return // Exit here, let the redirect happen
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

        // Initialize Keycloak without triggering any redirects or session checks
        // DO NOT specify onLoad - when omitted, Keycloak just checks for existing token
        // without any automatic redirects or SSO checks
        const authenticated = await kc.init({
          checkLoginIframe: false, // Disable iframe-based session check (can cause redirects)
          // Note: onLoad is intentionally omitted. Valid values are 'login-required' or 'check-sso',
          // but both can cause redirects. Omitting onLoad means just check localStorage.
          pkceMethod: 'S256',
        })

        console.log('[Auth] Init complete, authenticated:', authenticated)

        setKeycloak(kc)
        setIsAuthenticated(authenticated)

        if (authenticated && kc.tokenParsed) {
          setUser({
            username: kc.tokenParsed.preferred_username,
            email: kc.tokenParsed.email,
            name: kc.tokenParsed.name,
          })
          console.log('[Auth] User logged in:', kc.tokenParsed.preferred_username)
          setError(null)
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
    // Navigate directly to Keycloak instead of using keycloak.login()
    // Use the configured Keycloak URL (not hardcoded localhost:8080)
    const baseUrl = keycloakUrl.replace(/\/$/, '') // Remove trailing slash for URL construction
    const keycloakLoginUrl = new URL(`${baseUrl}/realms/eaistack/protocol/openid-connect/auth`)
    keycloakLoginUrl.searchParams.set('client_id', 'eaistack-web')
    keycloakLoginUrl.searchParams.set('redirect_uri', window.location.origin + '/')
    keycloakLoginUrl.searchParams.set('response_type', 'code')
    keycloakLoginUrl.searchParams.set('response_mode', 'query')
    keycloakLoginUrl.searchParams.set('scope', 'openid profile email')
    keycloakLoginUrl.searchParams.set('state', 'eaistack-' + Date.now())

    console.log('[Auth] Redirecting to Keycloak login:', keycloakLoginUrl.href)
    window.location.href = keycloakLoginUrl.href
  }

  const logout = () => {
    if (keycloak) {
      keycloak.logout({ redirectUri: `${window.location.origin}/` })
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
