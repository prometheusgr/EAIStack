import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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
  available_providers: {
    llm: [
      { provider: 'fake', url: '', label: 'Fake (mocked, for testing)' },
      {
        provider: 'llama-cpp',
        url: 'http://llama-server:8000/v1',
        label: 'llama-cpp (llama-server, detected)',
      },
      { provider: 'openai-compatible', url: '', label: 'OpenAI-compatible (custom)' },
    ],
    embedding: [
      { provider: 'fake', url: '', label: 'Fake (mocked, for testing)' },
      {
        provider: 'llama-cpp',
        url: 'http://embedding-server:8000/v1',
        label: 'llama-cpp (embedding-server, detected)',
      },
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

describe('Settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('access_token', ADMIN_TOKEN)
  })

  it('loads and displays the current effective LLM and embedding providers', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)

    renderSettings()

    await waitFor(() => {
      expect(settingsClient.getSettings).toHaveBeenCalled()
    })

    expect(await screen.findAllByText(/fake/i)).not.toHaveLength(0)
  })

  it('shows "env default" for fields with no DB override', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)

    renderSettings()

    await waitFor(() => {
      expect(screen.getAllByText(/env default/i).length).toBeGreaterThan(0)
    })
  })

  it('shows "overridden" for fields with a DB override', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      llm_provider: 'llama-cpp',
      llm_url: 'http://llama-server:8000/v1',
      llm_model: 'llama-3',
      llm_provider_is_db_override: true,
      llm_url_is_db_override: true,
      llm_model_is_db_override: true,
    })

    renderSettings()

    await waitFor(() => {
      expect(screen.getAllByText(/overridden/i).length).toBeGreaterThan(0)
    })
  })

  it('save button calls updateSettings and shows a success toast', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
    vi.mocked(settingsClient.updateSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      llm_provider: 'fake',
    })

    const user = userEvent.setup()
    renderSettings()

    const saveButton = await screen.findByRole('button', { name: /save/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })
    expect(await screen.findByText(/saved/i)).toBeInTheDocument()
  })

  it('shows an error toast when updateSettings fails validation', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
    vi.mocked(settingsClient.updateSettings).mockRejectedValue(
      new Error('Unknown llm_provider: bogus')
    )

    const user = userEvent.setup()
    renderSettings()

    const saveButton = await screen.findByRole('button', { name: /save/i })
    await user.click(saveButton)

    expect(await screen.findByText(/unknown llm_provider/i)).toBeInTheDocument()
  })

  it('never renders llm_api_key anywhere on the page', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)

    const { container } = renderSettings()

    await waitFor(() => {
      expect(settingsClient.getSettings).toHaveBeenCalled()
    })

    expect(container.innerHTML).not.toContain('llm_api_key')
  })
})
