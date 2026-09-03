import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuditLog } from './AuditLog'
import { AuthProvider } from '../context/AuthContext'
import { settingsClient } from '../api/settingsClient'
import type { AuditLogResponse } from '../types/settings'

vi.mock('../api/settingsClient', () => ({
  settingsClient: {
    getAuditLog: vi.fn(),
  },
}))

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

const AUDIT_LOG_RESPONSE: AuditLogResponse = {
  entries: [
    {
      id: 'entry-2',
      actor_user_id: 'admin-1',
      action: 'guardrail.config_update',
      field_name: 'guardrails_input_enabled',
      old_value: 'True',
      new_value: 'False',
      created_at: '2026-09-02T12:00:00Z',
    },
    {
      id: 'entry-1',
      actor_user_id: 'admin-1',
      action: 'retention.update',
      field_name: 'conversation_retention_hours',
      old_value: '72',
      new_value: '24',
      created_at: '2026-09-01T08:00:00Z',
    },
  ],
}

function renderAuditLog() {
  return render(
    <AuthProvider>
      <AuditLog />
    </AuthProvider>
  )
}

describe('AuditLog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('access_token', ADMIN_TOKEN)
  })

  it('shows a loading state while fetching', async () => {
    vi.mocked(settingsClient.getAuditLog).mockReturnValue(new Promise(() => {}))

    renderAuditLog()

    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders each audit entry with timestamp, actor, action, field, and old/new value', async () => {
    vi.mocked(settingsClient.getAuditLog).mockResolvedValueOnce(AUDIT_LOG_RESPONSE)

    renderAuditLog()

    await waitFor(() => {
      expect(screen.getByText('retention.update')).toBeInTheDocument()
    })

    expect(screen.getByText('guardrail.config_update')).toBeInTheDocument()
    expect(screen.getAllByText('admin-1').length).toBeGreaterThan(0)
    expect(screen.getByText('conversation_retention_hours')).toBeInTheDocument()
    expect(screen.getByText('72')).toBeInTheDocument()
    expect(screen.getByText('24')).toBeInTheDocument()
  })

  it('renders newest-first order as returned by the backend', async () => {
    vi.mocked(settingsClient.getAuditLog).mockResolvedValueOnce(AUDIT_LOG_RESPONSE)

    renderAuditLog()

    await waitFor(() => {
      expect(screen.getByText('retention.update')).toBeInTheDocument()
    })

    const rows = screen.getAllByRole('row')
    // rows[0] is the header row.
    expect(rows[1]).toHaveTextContent('guardrail.config_update')
    expect(rows[2]).toHaveTextContent('retention.update')
  })

  it('shows an empty state when there are no audit entries yet', async () => {
    vi.mocked(settingsClient.getAuditLog).mockResolvedValueOnce({ entries: [] })

    renderAuditLog()

    await waitFor(() => {
      expect(screen.getByText(/no audit entries/i)).toBeInTheDocument()
    })
  })

  it('shows an error state with a retry action on failure', async () => {
    vi.mocked(settingsClient.getAuditLog).mockRejectedValueOnce(new Error('Failed to load'))

    renderAuditLog()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    vi.mocked(settingsClient.getAuditLog).mockResolvedValueOnce(AUDIT_LOG_RESPONSE)
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))

    await waitFor(() => {
      expect(screen.getByText('retention.update')).toBeInTheDocument()
    })
  })
})
