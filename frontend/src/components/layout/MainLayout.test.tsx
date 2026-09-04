import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { MainLayout } from './MainLayout'
import { AuthProvider } from '../../context/AuthContext'

function buildToken(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.invalid_sig`
}

const ADMIN_TOKEN = buildToken({
  sub: 'admin-1',
  preferred_username: 'admin',
  exp: 9999999999,
  realm_access: { roles: ['admin'] },
})

const NON_ADMIN_TOKEN = buildToken({
  sub: 'user-1',
  preferred_username: 'regular',
  exp: 9999999999,
  realm_access: { roles: [] },
})

const CONSOLE_URL = 'http://localhost:8080/admin/master/console/#/eaistack/users'

function renderLayout(props: Partial<ComponentProps<typeof MainLayout>> = {}) {
  return render(
    <AuthProvider>
      <MainLayout currentView="chat" onViewChange={() => {}} {...props}>
        <div>content</div>
      </MainLayout>
    </AuthProvider>
  )
}

describe('MainLayout User Management link (issue #40)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders a User Management deep link to the Keycloak admin console for an admin', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)

    renderLayout({ keycloakUsersConsoleUrl: CONSOLE_URL })

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /user management/i })).toBeInTheDocument()
    })
    const link = screen.getByRole('link', { name: /user management/i })
    expect(link).toHaveAttribute('href', CONSOLE_URL)
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer')
  })

  it('does not render the link for a non-admin user', async () => {
    localStorage.setItem('access_token', NON_ADMIN_TOKEN)

    renderLayout({ keycloakUsersConsoleUrl: CONSOLE_URL })

    await waitFor(() => {
      expect(screen.getByText('content')).toBeInTheDocument()
    })
    expect(screen.queryByRole('link', { name: /user management/i })).not.toBeInTheDocument()
  })

  it('does not render the link before the console URL has loaded', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)

    renderLayout({ keycloakUsersConsoleUrl: undefined })

    await waitFor(() => {
      expect(screen.getByText('content')).toBeInTheDocument()
    })
    expect(screen.queryByRole('link', { name: /user management/i })).not.toBeInTheDocument()
  })

  it('does not render the link when the backend reports no console URL configured', async () => {
    localStorage.setItem('access_token', ADMIN_TOKEN)

    renderLayout({ keycloakUsersConsoleUrl: null })

    await waitFor(() => {
      expect(screen.getByText('content')).toBeInTheDocument()
    })
    expect(screen.queryByRole('link', { name: /user management/i })).not.toBeInTheDocument()
  })
})
