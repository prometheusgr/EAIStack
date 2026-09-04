import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Dashboard } from './Dashboard'
import { AuthProvider } from '../context/AuthContext'
import { settingsClient } from '../api/settingsClient'
import type { DashboardResponse, AuditLogResponse } from '../types/settings'

vi.mock('../api/settingsClient', () => ({
  settingsClient: {
    getDashboard: vi.fn(),
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

const DASHBOARD_RESPONSE: DashboardResponse = {
  rate_limit: { enabled: true, active_bucket_count: 4 },
  guardrails: {
    input_rejected_counts_by_pattern: { sql_injection: 3, instruction_override: 1 },
    output_redacted_count: 2,
  },
  tracing: {
    db_desired_enabled: true,
    process_actually_configured: false,
    phoenix_ui_url: 'http://localhost:6006',
  },
}

const AUDIT_LOG_RESPONSE: AuditLogResponse = {
  entries: [
    {
      id: 'entry-1',
      actor_user_id: 'admin-1',
      action: 'guardrail.config_update',
      field_name: 'guardrails_input_enabled',
      old_value: 'True',
      new_value: 'False',
      created_at: '2026-09-02T12:00:00Z',
    },
  ],
}

function renderDashboard(onViewAuditLog: () => void = () => {}) {
  return render(
    <AuthProvider>
      <Dashboard onViewAuditLog={onViewAuditLog} />
    </AuthProvider>
  )
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('access_token', ADMIN_TOKEN)
    vi.mocked(settingsClient.getAuditLog).mockResolvedValue(AUDIT_LOG_RESPONSE)
  })

  it('shows a loading state while fetching', async () => {
    vi.mocked(settingsClient.getDashboard).mockReturnValue(new Promise(() => {}))

    renderDashboard()

    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('renders the rate limiting tile with live bucket count', async () => {
    vi.mocked(settingsClient.getDashboard).mockResolvedValueOnce(DASHBOARD_RESPONSE)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText(/rate limiting/i)).toBeInTheDocument()
    })
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('renders the guardrails tile with per-pattern trip counts', async () => {
    vi.mocked(settingsClient.getDashboard).mockResolvedValueOnce(DASHBOARD_RESPONSE)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText(/guardrails/i)).toBeInTheDocument()
    })
    expect(screen.getByText('sql_injection')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('instruction_override')).toBeInTheDocument()
  })

  it('renders the tracing tile with a link to the Phoenix UI', async () => {
    vi.mocked(settingsClient.getDashboard).mockResolvedValueOnce(DASHBOARD_RESPONSE)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText(/tracing/i)).toBeInTheDocument()
    })
    const phoenixLink = screen.getByRole('link', { name: /phoenix/i })
    expect(phoenixLink).toHaveAttribute('href', 'http://localhost:6006')
  })

  it('flags a divergence between the DB-desired and process-actual tracing state', async () => {
    vi.mocked(settingsClient.getDashboard).mockResolvedValueOnce(DASHBOARD_RESPONSE)

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByText(/restart/i)).toBeInTheDocument()
    })
  })

  it('renders the recent activity tile from the audit log and links to the full view', async () => {
    vi.mocked(settingsClient.getDashboard).mockResolvedValueOnce(DASHBOARD_RESPONSE)
    const onViewAuditLog = vi.fn()

    renderDashboard(onViewAuditLog)

    await waitFor(() => {
      expect(screen.getByText('guardrail.config_update')).toBeInTheDocument()
    })

    await userEvent.click(screen.getByRole('button', { name: /view full audit log/i }))
    expect(onViewAuditLog).toHaveBeenCalled()
  })

  it('shows an error state with a retry action on failure', async () => {
    vi.mocked(settingsClient.getDashboard).mockRejectedValueOnce(new Error('Failed to load'))

    renderDashboard()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    vi.mocked(settingsClient.getDashboard).mockResolvedValueOnce(DASHBOARD_RESPONSE)
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))

    await waitFor(() => {
      expect(screen.getByText(/rate limiting/i)).toBeInTheDocument()
    })
  })
})
