import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RetentionNotice } from './RetentionNotice'
import { AuthProvider } from '../context/AuthContext'
import { settingsClient } from '../api/settingsClient'

vi.mock('../api/settingsClient', () => ({
  settingsClient: {
    getRetentionNotice: vi.fn(),
  },
}))

function buildToken(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.invalid_sig`
}

const USER_TOKEN = buildToken({
  sub: 'user-1',
  preferred_username: 'regular',
  exp: 9999999999,
  realm_access: { roles: ['offline_access'] },
})

function renderWithAuth() {
  localStorage.setItem('access_token', USER_TOKEN)
  return render(
    <AuthProvider>
      <RetentionNotice />
    </AuthProvider>
  )
}

describe('RetentionNotice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('shows the effective conversation-retention window in plain language', async () => {
    vi.mocked(settingsClient.getRetentionNotice).mockResolvedValueOnce({
      conversation_retention_hours: 5,
      cleanup_on_logout: false,
      notice_enabled: true,
    })

    renderWithAuth()

    expect(await screen.findByText(/5 hours/i)).toBeInTheDocument()
  })

  it('describes a whole-day window in days rather than hours', async () => {
    vi.mocked(settingsClient.getRetentionNotice).mockResolvedValueOnce({
      conversation_retention_hours: 48,
      cleanup_on_logout: false,
      notice_enabled: true,
    })

    renderWithAuth()

    expect(await screen.findByText(/2 days/i)).toBeInTheDocument()
  })

  it('states conversations are kept indefinitely when the window is null', async () => {
    vi.mocked(settingsClient.getRetentionNotice).mockResolvedValueOnce({
      conversation_retention_hours: null,
      cleanup_on_logout: false,
      notice_enabled: true,
    })

    renderWithAuth()

    expect(await screen.findByText(/kept indefinitely/i)).toBeInTheDocument()
  })

  it('renders nothing when notice_enabled is false', async () => {
    vi.mocked(settingsClient.getRetentionNotice).mockResolvedValueOnce({
      conversation_retention_hours: 24,
      cleanup_on_logout: false,
      notice_enabled: false,
    })

    renderWithAuth()

    await waitFor(() => expect(settingsClient.getRetentionNotice).toHaveBeenCalled())
    expect(screen.queryByText(/retained|kept/i)).not.toBeInTheDocument()
  })

  it('renders nothing while the request is in flight or has not resolved', () => {
    vi.mocked(settingsClient.getRetentionNotice).mockReturnValue(new Promise(() => {}))

    renderWithAuth()

    expect(screen.queryByText(/retained|kept/i)).not.toBeInTheDocument()
  })

  it('renders nothing if the request fails', async () => {
    vi.mocked(settingsClient.getRetentionNotice).mockRejectedValueOnce(new Error('network error'))

    renderWithAuth()

    await waitFor(() => expect(settingsClient.getRetentionNotice).toHaveBeenCalled())
    expect(screen.queryByText(/retained|kept/i)).not.toBeInTheDocument()
  })

  it('can be dismissed for the rest of the session', async () => {
    vi.mocked(settingsClient.getRetentionNotice).mockResolvedValueOnce({
      conversation_retention_hours: 5,
      cleanup_on_logout: false,
      notice_enabled: true,
    })

    renderWithAuth()

    await screen.findByText(/5 hours/i)
    await userEvent.click(screen.getByRole('button', { name: /dismiss/i }))

    expect(screen.queryByText(/5 hours/i)).not.toBeInTheDocument()
  })

  it('mentions logout cleanup when enabled', async () => {
    vi.mocked(settingsClient.getRetentionNotice).mockResolvedValueOnce({
      conversation_retention_hours: 5,
      cleanup_on_logout: true,
      notice_enabled: true,
    })

    renderWithAuth()

    expect(await screen.findByText(/log out/i)).toBeInTheDocument()
  })
})
