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

  useEffect(() => {
    const initKeycloak = async () => {
      // Determine Keycloak URL based on environment
      // In Docker: Browser sees http://localhost:8080 (published port)
      // In local dev: http://localhost:8080
      let keycloakUrl = 'http://localhost:8080/'
      if (import.meta.env.VITE_KEYCLOAK_URL) {
        keycloakUrl = import.meta.env.VITE_KEYCLOAK_URL
        // Ensure trailing slash for Keycloak client
        if (!keycloakUrl.endsWith('/')) {
          keycloakUrl += '/'
        }
      }

      console.log('[Auth] Configured Keycloak URL:', keycloakUrl)

      const kc = new Keycloak({
        url: keycloakUrl,
        realm: 'eaistack',
        clientId: 'eaistack-web',
      })

      console.log('[Auth] Keycloak instance URL:', kc.authServerUrl)

      console.log('[Auth] Keycloak config:', {
        url: kc.authServerUrl,
        realm: kc.realm,
        clientId: kc.clientId,
      })
      try {
        // Check for redirect loop (error=login_required in hash)
        if (window.location.hash.includes('error=login_required')) {
          console.warn('[Auth] Detected login_required error - possible session issue')
          setError('Login failed. Please try again.')
          setKeycloak(kc)
          setIsAuthenticated(false)
          setIsLoading(false)
          return
        }

        const authenticated = await kc.init({
          checkLoginIframe: false,
          onLoad: 'check-sso',
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

  const login = async () => {
    if (keycloak) {
      try {
        keycloak.login()
      } catch (err) {
        console.error('Login failed:', err)
      }
    }
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
