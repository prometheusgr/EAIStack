import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Settings } from './Settings'
import { ToastProvider } from './ui/toast'
import { AuthProvider } from '../context/AuthContext'
import { settingsClient } from '../api/settingsClient'

vi.mock('../api/settingsClient', () => ({
  settingsClient: {
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
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

const ENV_DEFAULT_SETTINGS = {
  llm_provider: 'fake',
  llm_url: '',
  llm_model: '',
  llm_provider_is_db_override: false,
  llm_url_is_db_override: false,
  llm_model_is_db_override: false,
  embedding_provider: 'fake',
  embedding_url: '',
  embedding_model: '',
  embedding_provider_is_db_override: false,
  embedding_url_is_db_override: false,
  embedding_model_is_db_override: false,
  conversation_retention_hours: 24,
  conversation_retention_hours_is_db_override: false,
  cleanup_on_logout: true,
  cleanup_on_logout_is_db_override: false,
  knowledge_base_purge_days: 30,
  knowledge_base_purge_days_is_db_override: false,
  api_key_purge_days: 30,
  api_key_purge_days_is_db_override: false,
  available_providers: {
    llm: [
      { provider: 'fake', url: '', label: 'Fake (mocked, for testing)', requires_manual_entry: false },
    ],
    embedding: [
      { provider: 'fake', url: '', label: 'Fake (mocked, for testing)', requires_manual_entry: false },
    ],
  },
}

function renderSettings() {
  return render(
    <AuthProvider>
      <ToastProvider>
        <Settings />
      </ToastProvider>
    </AuthProvider>
  )
}

async function waitForLoaded() {
  await waitFor(() => {
    expect(settingsClient.getSettings).toHaveBeenCalled()
  })
  const input = await screen.findByLabelText(/conversation history/i)

  // The input exists as soon as get.data becomes non-null, but its value is
  // populated by a second, separate useEffect keyed on get.data (see
  // Settings.tsx) that commits in a later render. Under fast local
  // scheduling that gap is invisible; under CPU-constrained CI runners it's
  // wide enough for a test to read the input before it's populated,
  // producing an empty/null value instead of the loaded one. Waiting for
  // the value to actually land - not just for the element to exist - is
  // what every caller of this helper actually needs before it starts
  // asserting on or editing the field.
  await waitFor(() => {
    expect(input).not.toHaveValue(null)
  })
  return input
}

describe('Settings retention section', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('access_token', ADMIN_TOKEN)
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
    vi.mocked(settingsClient.updateSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
  })

  it('displays the current conversation retention window', async () => {
    renderSettings()

    const input = await waitForLoaded()

    expect(input).toHaveValue(24)
  })

  it('shows "env default" for retention fields with no DB override', async () => {
    renderSettings()
    await waitForLoaded()

    const retentionSection = screen.getByRole('region', { name: /data retention/i })

    expect(retentionSection).toHaveTextContent(/env default/i)
  })

  it('shows "overridden" for a retention field backed by a DB override', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      conversation_retention_hours: 72,
      conversation_retention_hours_is_db_override: true,
    })

    renderSettings()
    await waitForLoaded()

    const retentionSection = screen.getByRole('region', { name: /data retention/i })

    expect(retentionSection).toHaveTextContent(/overridden/i)
  })

  it('lengthening the window saves without asking for confirmation', async () => {
    const user = userEvent.setup()
    renderSettings()

    const input = await waitForLoaded()
    await user.clear(input)
    await user.type(input, '72')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })
    expect(vi.mocked(settingsClient.updateSettings).mock.calls[0][0]).toMatchObject({
      conversation_retention_hours: 72,
    })
  })

  it('shortening the window asks for confirmation before saving', async () => {
    const user = userEvent.setup()
    renderSettings()

    const input = await waitForLoaded()
    await user.clear(input)
    await user.type(input, '1')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
    expect(settingsClient.updateSettings).not.toHaveBeenCalled()
  })

  it('the confirmation states what will be deleted', async () => {
    const user = userEvent.setup()
    renderSettings()

    const input = await waitForLoaded()
    await user.clear(input)
    await user.type(input, '1')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    const dialog = await screen.findByRole('alertdialog')

    expect(dialog).toHaveTextContent(/permanently deleted/i)
    expect(dialog).toHaveTextContent(/all users/i)
    expect(dialog).toHaveTextContent(/24/)
    expect(dialog).toHaveTextContent(/1/)
  })

  it('confirming the shortened window saves it', async () => {
    const user = userEvent.setup()
    renderSettings()

    const input = await waitForLoaded()
    await user.clear(input)
    await user.type(input, '1')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: /delete/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })
    expect(vi.mocked(settingsClient.updateSettings).mock.calls[0][0]).toMatchObject({
      conversation_retention_hours: 1,
    })
  })

  it('cancelling the confirmation leaves settings unchanged', async () => {
    const user = userEvent.setup()
    renderSettings()

    const input = await waitForLoaded()
    await user.clear(input)
    await user.type(input, '1')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: /cancel/i }))

    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    })
    expect(settingsClient.updateSettings).not.toHaveBeenCalled()
  })

  it('shortening a purge window also asks for confirmation', async () => {
    const user = userEvent.setup()
    renderSettings()

    await waitForLoaded()
    const purgeInput = screen.getByLabelText(/deleted documents/i)
    await user.clear(purgeInput)
    await user.type(purgeInput, '7')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
    expect(settingsClient.updateSettings).not.toHaveBeenCalled()
  })

  it('resetting a retention field to default sends null', async () => {
    const user = userEvent.setup()
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      conversation_retention_hours: 72,
      conversation_retention_hours_is_db_override: true,
    })

    renderSettings()
    await waitForLoaded()

    const retentionSection = screen.getByRole('region', { name: /data retention/i })
    await user.click(within(retentionSection).getByRole('button', { name: /reset retention to default/i }))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })
    expect(vi.mocked(settingsClient.updateSettings).mock.calls[0][0]).toMatchObject({
      conversation_retention_hours: null,
    })
  })

  it('toggling cleanup-on-logout is saved', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForLoaded()

    await user.click(screen.getByLabelText(/purge conversations on logout/i))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })
    expect(vi.mocked(settingsClient.updateSettings).mock.calls[0][0]).toMatchObject({
      cleanup_on_logout: false,
    })
  })

  it('resetting retention to default also clears the cleanup-on-logout override', async () => {
    // Once toggled and saved, cleanup_on_logout becomes a DB override
    // (booleans have no "unset" value other than null) and the only way
    // back to the env default is the same reset control the other
    // retention fields already use.
    const user = userEvent.setup()
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      cleanup_on_logout: false,
      cleanup_on_logout_is_db_override: true,
    })

    renderSettings()
    await waitForLoaded()

    const retentionSection = screen.getByRole('region', { name: /data retention/i })
    await user.click(within(retentionSection).getByRole('button', { name: /reset retention to default/i }))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })
    expect(vi.mocked(settingsClient.updateSettings).mock.calls[0][0]).toMatchObject({
      cleanup_on_logout: null,
    })
  })
})
