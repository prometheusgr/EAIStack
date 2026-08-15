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

  useEffect(() => {
    const kc = new Keycloak({
      url: 'http://localhost:8080',
      realm: 'eaistack',
      clientId: 'eaistack-web',
    })

    kc.init({ onLoad: 'check-sso', redirectUri: 'http://localhost:3000' })
      .then((authenticated) => {
        setKeycloak(kc)
        setIsAuthenticated(authenticated)
        if (authenticated) {
          setUser({
            username: kc.tokenParsed?.preferred_username,
            email: kc.tokenParsed?.email,
            name: kc.tokenParsed?.name,
          })
        }
      })
      .catch(() => {
        setKeycloak(kc)
      })
      .finally(() => {
        setIsLoading(false)
      })
  }, [])

  const login = () => {
    if (keycloak) {
      keycloak.login()
    }
  }

  const logout = () => {
    if (keycloak) {
      keycloak.logout()
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
