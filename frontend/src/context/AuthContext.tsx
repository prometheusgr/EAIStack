import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import {
  decodeJwt,
  buildKeycloakLoginUrl,
  buildKeycloakLogoutUrl,
  AuthUser,
} from '../auth/authHelpers'
import { AuthService } from '@/services/authService'
import { useIsMounted } from '../hooks/useIsMounted'
import { parseErrorBody } from '../api/authorizedFetch'

interface AuthContextType {
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: () => void
  logout: () => Promise<void>
  refreshAccessToken: () => Promise<boolean>
  user: AuthUser | null
  roles: string[]
  isAdmin: boolean
  // Details of the most recent failed /api/auth/token call (initial code
  // exchange or a background refresh) -- e.g. a rate limit trip's "Too many
  // requests..." text plus the Retry-After countdown, when the backend
  // supplied one. null when there is nothing to show, or the endpoint gave
  // no message (see parseErrorBody).
  authError: { message: string; retryAfterSeconds?: number } | null
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [roles, setRoles] = useState<string[]>([])
  const [keycloakUrl, setKeycloakUrl] = useState<string>('http://localhost:8080/')
  const [authError, setAuthError] = useState<{ message: string; retryAfterSeconds?: number } | null>(
    null
  )
  const isMounted = useIsMounted()

  useEffect(() => {
    const initAuth = async () => {
      let url = 'http://localhost:8080/'
      if (import.meta.env.VITE_KEYCLOAK_URL) {
        url = import.meta.env.VITE_KEYCLOAK_URL
        if (!url.endsWith('/')) {
          url += '/'
        }
      }
      if (isMounted()) setKeycloakUrl(url)

      try {
        const urlParams = new URLSearchParams(window.location.search)
        const code = urlParams.get('code')
        // Keycloak's own ?error= redirect param (e.g. user denied consent)
        // -- distinct from the authError *state* below, which is this
        // context's own /api/auth/token failure message.
        const keycloakErrorParam = urlParams.get('error')

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

            if (!isMounted()) {
              return
            }

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
                  if (isMounted()) {
                    setToken(tokenData.access_token)
                    setIsAuthenticated(true)
                    setUser({
                      username: payload.preferred_username,
                      email: payload.email,
                      name: payload.name,
                    })
                    setRoles(payload.realm_access?.roles || [])
                  }
                } catch {
                  localStorage.removeItem('access_token')
                  localStorage.removeItem('refresh_token')
                  localStorage.removeItem('token_type')
                  localStorage.removeItem('id_token')
                }
              }
              window.history.replaceState(null, '', window.location.pathname)
              if (isMounted()) setIsLoading(false)
              return
            }

            // Non-ok response (e.g. a rate-limit trip, an expired/invalid
            // code): surface the backend's human-readable message so the
            // pre-login screen can show *why* login didn't complete,
            // instead of silently dropping the user back to the login
            // button with no explanation.
            const body = await parseErrorBody(tokenResponse)
            if (isMounted()) {
              setAuthError(
                body.message
                  ? { message: body.message, retryAfterSeconds: body.retryAfterSeconds }
                  : null
              )
            }
          } catch {
            // Error handled below
          }
          window.history.replaceState(null, '', window.location.pathname)
        }

        if (keycloakErrorParam) {
          window.history.replaceState(null, '', window.location.pathname)
        }

        // Check for stored token from previous session
        const storedToken = localStorage.getItem('access_token')
        if (storedToken) {
          try {
            const payload = decodeJwt(storedToken)
            if (isMounted()) {
              setToken(storedToken)
              setIsAuthenticated(true)
              setUser({
                username: payload.preferred_username,
                email: payload.email,
                name: payload.name,
              })
              setRoles(payload.realm_access?.roles || [])
              setIsLoading(false)
            }
            return
          } catch {
            localStorage.removeItem('access_token')
            localStorage.removeItem('refresh_token')
            localStorage.removeItem('token_type')
            localStorage.removeItem('id_token')
          }
        }

        // No token found
        if (isMounted()) {
          setIsAuthenticated(false)
          setUser(null)
          setToken(null)
          setIsLoading(false)
        }
      } finally {
        if (isMounted()) {
          setIsLoading(false)
        }
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
        // A 429 means the refresh token itself is still good -- the caller
        // is just being throttled. Treating it the same as an invalid/
        // expired refresh token (any other non-ok status) would force a
        // perfectly valid session to log out and re-authenticate purely
        // because of request volume, which defeats the point of having a
        // refresh token at all. Leave the session and stored tokens
        // untouched; the caller can retry after Retry-After.
        const body = await parseErrorBody(response)
        if (response.status === 429) {
          if (isMounted()) {
            setAuthError(
              body.message
                ? { message: body.message, retryAfterSeconds: body.retryAfterSeconds }
                : null
            )
          }
          return false
        }

        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('token_type')
        localStorage.removeItem('id_token')
        if (isMounted()) {
          setIsAuthenticated(false)
          setUser(null)
          setToken(null)
          setRoles([])
        }
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
          if (isMounted()) {
            setToken(tokenData.access_token)
            setUser({
              username: payload.preferred_username,
              email: payload.email,
              name: payload.name,
            })
            setRoles(payload.realm_access?.roles || [])
          }
          return true
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          localStorage.removeItem('token_type')
          localStorage.removeItem('id_token')
          if (isMounted()) {
            setIsAuthenticated(false)
            setUser(null)
            setToken(null)
            setRoles([])
          }
          return false
        }
      }
      return false
    } catch {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('token_type')
      localStorage.removeItem('id_token')
      if (isMounted()) {
        setIsAuthenticated(false)
        setUser(null)
        setToken(null)
        setRoles([])
      }
      return false
    }
  }

  const logout = async () => {
    const idToken = localStorage.getItem('id_token')
    const accessToken = localStorage.getItem('access_token')

    // Ask the backend to purge this user's conversation state before the
    // token is discarded — afterwards there is no credential left to
    // authenticate the request. Whether anything is actually deleted is the
    // backend's decision (cleanup_on_logout); the frontend only triggers it.
    // A failure here must not strand the user in a half-logged-out state, so
    // the local sign-out proceeds regardless.
    if (accessToken) {
      try {
        await new AuthService(accessToken).logout()
      } catch {
        // Server-side cleanup failed; the TTL sweep will collect the data.
      }
    }

    localStorage.removeItem('access_token')
    localStorage.removeItem('token_type')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('id_token')

    if (isMounted()) {
      setIsAuthenticated(false)
      setUser(null)
      setToken(null)
      setRoles([])
    }

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
      value={{
        token,
        isAuthenticated,
        isLoading,
        login,
        logout,
        refreshAccessToken,
        user,
        roles,
        isAdmin,
        authError,
      }}
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
