import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthProvider, useAuth } from '../../src/context/AuthContext'

function buildToken(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.invalid_sig`
}

function IsAdminProbe() {
  const { isAdmin, isLoading } = useAuth()
  if (isLoading) return <div>loading</div>
  return <div data-testid="is-admin">{String(isAdmin)}</div>
}

function RefreshProbe() {
  const { isAdmin, isAuthenticated, isLoading, authError, refreshAccessToken } = useAuth()
  if (isLoading) return <div>loading</div>
  return (
    <div>
      <div data-testid="is-admin">{String(isAdmin)}</div>
      <div data-testid="is-authenticated">{String(isAuthenticated)}</div>
      <div data-testid="auth-error">{authError?.message ?? ''}</div>
      <div data-testid="auth-error-retry-after">{authError?.retryAfterSeconds ?? ''}</div>
      <button onClick={() => refreshAccessToken()}>refresh</button>
    </div>
  )
}

function AuthErrorProbe() {
  const { isLoading, authError } = useAuth()
  if (isLoading) return <div>loading</div>
  return (
    <div>
      <div data-testid="auth-error">{authError?.message ?? ''}</div>
      <div data-testid="auth-error-retry-after">{authError?.retryAfterSeconds ?? ''}</div>
    </div>
  )
}

describe('AuthContext isAdmin', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('is true when the stored token carries the admin realm role', async () => {
    const token = buildToken({
      sub: 'user-123',
      preferred_username: 'testuser',
      exp: 9999999999,
      realm_access: { roles: ['admin', 'offline_access'] },
    })
    localStorage.setItem('access_token', token)

    render(
      <AuthProvider>
        <IsAdminProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('is-admin')).toHaveTextContent('true')
    })
  })

  it('is false when the stored token has no admin realm role', async () => {
    const token = buildToken({
      sub: 'user-456',
      preferred_username: 'regularuser',
      exp: 9999999999,
      realm_access: { roles: ['offline_access'] },
    })
    localStorage.setItem('access_token', token)

    render(
      <AuthProvider>
        <IsAdminProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('is-admin')).toHaveTextContent('false')
    })
  })

  it('is false when the stored token has no realm_access claim at all', async () => {
    const token = buildToken({
      sub: 'user-789',
      preferred_username: 'norolesuser',
      exp: 9999999999,
    })
    localStorage.setItem('access_token', token)

    render(
      <AuthProvider>
        <IsAdminProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('is-admin')).toHaveTextContent('false')
    })
  })

  it('is false when there is no stored token', async () => {
    render(
      <AuthProvider>
        <IsAdminProbe />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('is-admin')).toHaveTextContent('false')
    })
  })

  describe('after a failed token refresh', () => {
    beforeEach(() => {
      vi.stubGlobal('fetch', vi.fn())
    })

    afterEach(() => {
      vi.unstubAllGlobals()
    })

    it('clears isAdmin for a previously-admin session when the refresh token is rejected (401)', async () => {
      const token = buildToken({
        sub: 'user-123',
        preferred_username: 'testuser',
        exp: 9999999999,
        realm_access: { roles: ['admin', 'offline_access'] },
      })
      localStorage.setItem('access_token', token)
      localStorage.setItem('refresh_token', 'stale-refresh-token')

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'invalid_grant' }),
      } as Response)

      const user = userEvent.setup()
      render(
        <AuthProvider>
          <RefreshProbe />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('is-admin')).toHaveTextContent('true')
      })

      await user.click(screen.getByText('refresh'))

      await waitFor(() => {
        expect(screen.getByTestId('is-admin')).toHaveTextContent('false')
        expect(screen.getByTestId('is-authenticated')).toHaveTextContent('false')
      })
    })

    it('does NOT log out a valid session when the refresh is rate-limited (429)', async () => {
      // A 429 means "the refresh token is still good, just try again shortly"
      // -- treating it the same as an invalid/expired refresh token (401)
      // would force a real, working session to log out and re-authenticate
      // purely because of request volume, defeating the point of a refresh
      // token existing at all.
      const token = buildToken({
        sub: 'user-123',
        preferred_username: 'testuser',
        exp: 9999999999,
        realm_access: { roles: ['admin', 'offline_access'] },
      })
      localStorage.setItem('access_token', token)
      localStorage.setItem('refresh_token', 'still-valid-refresh-token')

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 429,
        headers: new Headers({ 'Retry-After': '30' }),
        json: async () => ({
          detail: 'rate_limit_exceeded',
          message: 'Too many requests. Please wait before trying again.',
        }),
      } as Response)

      const user = userEvent.setup()
      render(
        <AuthProvider>
          <RefreshProbe />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('is-admin')).toHaveTextContent('true')
      })

      await user.click(screen.getByText('refresh'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-error')).toHaveTextContent(
          'Too many requests. Please wait before trying again.'
        )
      })

      // The session itself must survive: still authenticated, still admin,
      // tokens still in localStorage.
      expect(screen.getByTestId('is-authenticated')).toHaveTextContent('true')
      expect(screen.getByTestId('is-admin')).toHaveTextContent('true')
      expect(localStorage.getItem('access_token')).toBe(token)
      expect(localStorage.getItem('refresh_token')).toBe('still-valid-refresh-token')
    })

    it('refreshAccessToken returns false on a 429 without clearing the session', async () => {
      const token = buildToken({
        sub: 'user-123',
        preferred_username: 'testuser',
        exp: 9999999999,
      })
      localStorage.setItem('access_token', token)
      localStorage.setItem('refresh_token', 'still-valid-refresh-token')

      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 429,
        headers: new Headers({ 'Retry-After': '30' }),
        json: async () => ({ detail: 'rate_limit_exceeded', message: 'Slow down.' }),
      } as Response)

      let refreshResult: boolean | undefined
      function ReturnValueProbe() {
        const { isLoading, refreshAccessToken } = useAuth()
        if (isLoading) return <div>loading</div>
        return (
          <button
            onClick={async () => {
              refreshResult = await refreshAccessToken()
            }}
          >
            refresh
          </button>
        )
      }

      const user = userEvent.setup()
      render(
        <AuthProvider>
          <ReturnValueProbe />
        </AuthProvider>
      )

      await waitFor(() => screen.getByText('refresh'))
      await user.click(screen.getByText('refresh'))

      await waitFor(() => {
        expect(refreshResult).toBe(false)
      })
    })

    it('clears isAdmin for a previously-admin session when the refresh request throws', async () => {
      const token = buildToken({
        sub: 'user-123',
        preferred_username: 'testuser',
        exp: 9999999999,
        realm_access: { roles: ['admin', 'offline_access'] },
      })
      localStorage.setItem('access_token', token)
      localStorage.setItem('refresh_token', 'stale-refresh-token')

      vi.mocked(fetch).mockRejectedValueOnce(new Error('network down'))

      const user = userEvent.setup()
      render(
        <AuthProvider>
          <RefreshProbe />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('is-admin')).toHaveTextContent('true')
      })

      await user.click(screen.getByText('refresh'))

      await waitFor(() => {
        expect(screen.getByTestId('is-admin')).toHaveTextContent('false')
      })
    })
  })

  describe('initial login (authorization code exchange)', () => {
    afterEach(() => {
      vi.unstubAllGlobals()
      window.history.replaceState(null, '', '/')
    })

    it('surfaces the backend message when the code exchange is rate-limited (429)', async () => {
      window.history.pushState({}, '', '/?code=some-auth-code')
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValueOnce({
          ok: false,
          status: 429,
          headers: new Headers({ 'Retry-After': '30' }),
          json: async () => ({
            detail: 'rate_limit_exceeded',
            message: 'Too many requests. Please wait before trying again.',
          }),
        } as Response)
      )

      render(
        <AuthProvider>
          <AuthErrorProbe />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('auth-error')).toHaveTextContent(
          'Too many requests. Please wait before trying again.'
        )
      })
      expect(screen.getByTestId('auth-error-retry-after')).toHaveTextContent('30')
    })

    it('clears the code from the URL even after a failed exchange, so a reload does not repeat it', async () => {
      window.history.pushState({}, '', '/?code=some-auth-code')
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValueOnce({
          ok: false,
          status: 429,
          headers: new Headers({ 'Retry-After': '30' }),
          json: async () => ({ detail: 'rate_limit_exceeded', message: 'Slow down.' }),
        } as Response)
      )

      render(
        <AuthProvider>
          <AuthErrorProbe />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('auth-error')).toHaveTextContent('Slow down.')
      })
      expect(window.location.search).toBe('')
    })

    it('does not set an error message after a successful code exchange', async () => {
      window.history.pushState({}, '', '/?code=some-auth-code')
      const token = buildToken({ sub: 'user-1', preferred_username: 'alice', exp: 9999999999 })
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ access_token: token, token_type: 'Bearer' }),
        } as Response)
      )

      render(
        <AuthProvider>
          <AuthErrorProbe />
        </AuthProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('auth-error')).toHaveTextContent('')
      })
    })
  })
})
