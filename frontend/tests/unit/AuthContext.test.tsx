import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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
})
