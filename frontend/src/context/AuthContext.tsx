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
  const [isLoading, setIsLoading] = useState(false)
  const [user, setUser] = useState(null)

  useEffect(() => {
    const initKeycloak = async () => {
      const kc = new Keycloak({
        url: 'http://localhost:8080',
        realm: 'eaistack',
        clientId: 'eaistack-web',
      })
      try {
        const authenticated = await kc.init({ checkLoginIframe: false })
        setKeycloak(kc)
        setIsAuthenticated(authenticated)
        if (authenticated) {
          setUser({
            username: kc.tokenParsed?.preferred_username,
            email: kc.tokenParsed?.email,
            name: kc.tokenParsed?.name,
          })
          console.log('[Auth] Initialized with user:', kc.tokenParsed?.preferred_username)
        }
      } catch (err) {
        console.error('[Auth] Keycloak init failed:', err)
        setKeycloak(kc)
      }
      setIsLoading(false)
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
