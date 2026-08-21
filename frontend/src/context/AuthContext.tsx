import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import {
  decodeJwt,
  buildKeycloakLoginUrl,
  buildKeycloakLogoutUrl,
  AuthUser,
} from '../auth/authHelpers'

interface AuthContextType {
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: () => void
  logout: () => void
  refreshAccessToken: () => Promise<boolean>
  user: AuthUser | null
  roles: string[]
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [roles, setRoles] = useState<string[]>([])
  const [keycloakUrl, setKeycloakUrl] = useState<string>('http://localhost:8080/')

  useEffect(() => {
    const initAuth = async () => {
      let url = 'http://localhost:8080/'
      if (import.meta.env.VITE_KEYCLOAK_URL) {
        url = import.meta.env.VITE_KEYCLOAK_URL
        if (!url.endsWith('/')) {
          url += '/'
        }
      }
      setKeycloakUrl(url)

      try {
        const urlParams = new URLSearchParams(window.location.search)
        const code = urlParams.get('code')
        const authError = urlParams.get('error')

        // Handle authorization code from Keycloak redirect
        if (code) {
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
              if (tokenData.access_token) {
                localStorage.setItem('access_token', tokenData.access_token)
                localStorage.setItem('token_type', tokenData.token_type || 'Bearer')
                if (tokenData.refresh_token) {
                  localStorage.setItem('refresh_token', tokenData.refresh_token)
                }
                if (tokenData.id_token) {
                  localStorage.setItem('id_token', tokenData.id_token)
                }

                try {
                  const payload = decodeJwt(tokenData.access_token)
                  setToken(tokenData.access_token)
                  setIsAuthenticated(true)
                  setUser({
                    username: payload.preferred_username,
                    email: payload.email,
                    name: payload.name,
                  })
                  setRoles(payload.realm_access?.roles || [])
                } catch {
                  localStorage.removeItem('access_token')
                  localStorage.removeItem('refresh_token')
                  localStorage.removeItem('token_type')
                  localStorage.removeItem('id_token')
                }
              }
              window.history.replaceState(null, '', window.location.pathname)
              setIsLoading(false)
              return
            }
          } catch {
            // Error handled below
          }
          window.history.replaceState(null, '', window.location.pathname)
        }

        if (authError) {
          window.history.replaceState(null, '', window.location.pathname)
        }

        // Check for stored token from previous session
        const storedToken = localStorage.getItem('access_token')
        if (storedToken) {
          try {
            const payload = decodeJwt(storedToken)
            setToken(storedToken)
            setIsAuthenticated(true)
            setUser({
              username: payload.preferred_username,
              email: payload.email,
              name: payload.name,
            })
            setRoles(payload.realm_access?.roles || [])
            setIsLoading(false)
            return
          } catch {
            localStorage.removeItem('access_token')
            localStorage.removeItem('refresh_token')
            localStorage.removeItem('token_type')
            localStorage.removeItem('id_token')
          }
        }

        // No token found
        setIsAuthenticated(false)
        setUser(null)
        setToken(null)
      } finally {
        setIsLoading(false)
      }
    }
    initAuth()
  }, [])

  const login = () => {
    if (!keycloakUrl || keycloakUrl.length === 0) {
      return
    }

    try {
      const loginUrl = buildKeycloakLoginUrl(keycloakUrl, window.location.origin + '/')
      window.location.href = loginUrl
    } catch {
      // Error handling
    }
  }

  const refreshAccessToken = async (): Promise<boolean> => {
    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      return false
    }

    try {
      const response = await fetch('/api/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grant_type: 'refresh_token',
          refresh_token: refreshToken,
        }),
      })

      if (!response.ok) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('token_type')
        localStorage.removeItem('id_token')
        setIsAuthenticated(false)
        setUser(null)
        setToken(null)
        setRoles([])
        return false
      }

      const tokenData = await response.json()
      if (tokenData.access_token) {
        localStorage.setItem('access_token', tokenData.access_token)
        localStorage.setItem('token_type', tokenData.token_type || 'Bearer')
        if (tokenData.refresh_token) {
          localStorage.setItem('refresh_token', tokenData.refresh_token)
        }
        if (tokenData.id_token) {
          localStorage.setItem('id_token', tokenData.id_token)
        }

        try {
          const payload = decodeJwt(tokenData.access_token)
          setToken(tokenData.access_token)
          setUser({
            username: payload.preferred_username,
            email: payload.email,
            name: payload.name,
          })
          setRoles(payload.realm_access?.roles || [])
          return true
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          localStorage.removeItem('token_type')
          localStorage.removeItem('id_token')
          setIsAuthenticated(false)
          setUser(null)
          setToken(null)
          setRoles([])
          return false
        }
      }
      return false
    } catch {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('token_type')
      localStorage.removeItem('id_token')
      setIsAuthenticated(false)
      setUser(null)
      setToken(null)
      setRoles([])
      return false
    }
  }

  const logout = () => {
    const idToken = localStorage.getItem('id_token')
    localStorage.removeItem('access_token')
    localStorage.removeItem('token_type')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('id_token')

    setIsAuthenticated(false)
    setUser(null)
    setToken(null)
    setRoles([])

    try {
      const logoutUrl = buildKeycloakLogoutUrl(keycloakUrl, window.location.origin + '/', idToken || undefined)
      window.location.replace(logoutUrl)
    } catch {
      // Fallback: stay on page with cleared auth
    }
  }

  const isAdmin = roles.includes('admin')

  return (
    <AuthContext.Provider
      value={{ token, isAuthenticated, isLoading, login, logout, refreshAccessToken, user, roles, isAdmin }}
    >
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
