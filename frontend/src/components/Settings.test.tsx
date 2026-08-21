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
      {
        provider: 'llama-cpp',
        url: 'http://llama-server:8000/v1',
        label: 'llama-cpp (llama-server, detected)',
        requires_manual_entry: true,
      },
      {
        provider: 'openai-compatible',
        url: '',
        label: 'OpenAI-compatible (custom)',
        requires_manual_entry: true,
      },
    ],
    embedding: [
      { provider: 'fake', url: '', label: 'Fake (mocked, for testing)', requires_manual_entry: false },
      {
        provider: 'llama-cpp',
        url: 'http://embedding-server:8000/v1',
        label: 'llama-cpp (embedding-server, detected)',
        requires_manual_entry: true,
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

  it('clears the model field when the LLM provider selection changes', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      llm_provider: 'openai-compatible',
      llm_url: 'http://custom:8000/v1',
      llm_model: 'llama-3',
      llm_provider_is_db_override: true,
      llm_url_is_db_override: true,
      llm_model_is_db_override: true,
    })

    const user = userEvent.setup()
    renderSettings()

    await waitFor(() => {
      expect(document.getElementById('llm-model')).not.toBeNull()
    })
    const modelInput = document.getElementById('llm-model') as HTMLInputElement
    expect(modelInput.value).toBe('llama-3')

    // Switch to another manual-entry provider (not "fake", whose advanced
    // fields are hidden entirely) so the model input stays visible and its
    // cleared value can be asserted directly.
    const providerSelect = screen.getByLabelText(/llm provider/i)
    await user.click(providerSelect)
    const llamaCppOption = await screen.findByRole('option', {
      name: /llama-cpp \(llama-server, detected\)/i,
    })
    await user.click(llamaCppOption)

    await waitFor(() => {
      expect((document.getElementById('llm-model') as HTMLInputElement).value).toBe('')
    })
  })

  it('clears the model field when the embedding provider selection changes', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      embedding_provider: 'llama-cpp',
      embedding_url: 'http://embedding-server:8000/v1',
      embedding_model: 'embed-model',
      embedding_provider_is_db_override: true,
      embedding_url_is_db_override: true,
      embedding_model_is_db_override: true,
    })

    const user = userEvent.setup()
    renderSettings()

    await waitFor(() => {
      expect(document.getElementById('embedding-model')).not.toBeNull()
    })
    const modelInput = document.getElementById('embedding-model') as HTMLInputElement
    expect(modelInput.value).toBe('embed-model')

    // Switch away to "fake" (whose advanced fields are hidden) and back to
    // llama-cpp: the model field must come back empty, not carrying over
    // the stale "embed-model" value from before the round trip.
    const providerSelect = screen.getByLabelText(/embedding provider/i)
    await user.click(providerSelect)
    const fakeOption = await screen.findByRole('option', { name: /fake \(mocked, for testing\)/i })
    await user.click(fakeOption)

    await user.click(screen.getByLabelText(/embedding provider/i))
    const llamaCppOption = await screen.findByRole('option', {
      name: /llama-cpp \(embedding-server, detected\)/i,
    })
    await user.click(llamaCppOption)

    await waitFor(() => {
      expect((document.getElementById('embedding-model') as HTMLInputElement).value).toBe('')
    })
  })

  it('sends null for the LLM URL and model when "Reset to default" is clicked', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      llm_provider: 'openai-compatible',
      llm_url: 'http://custom:8000/v1',
      llm_model: 'llama-3',
      llm_provider_is_db_override: true,
      llm_url_is_db_override: true,
      llm_model_is_db_override: true,
    })
    vi.mocked(settingsClient.updateSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)

    const user = userEvent.setup()
    renderSettings()

    const resetButtons = await screen.findAllByRole('button', { name: /reset to default/i })
    const llmResetButton = resetButtons[0]
    await user.click(llmResetButton)

    const saveButton = screen.getByRole('button', { name: /^save$/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })

    const payload = vi.mocked(settingsClient.updateSettings).mock.calls[0][0]
    expect(payload.llm_url).toBeNull()
    expect(payload.llm_model).toBeNull()
  })

  it('shows and pre-fills the custom URL/model fields for llama-cpp with a stored override', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      llm_provider: 'llama-cpp',
      llm_url: 'http://custom-llama-host:9000/v1',
      llm_model: 'custom-model-name',
      llm_provider_is_db_override: true,
      llm_url_is_db_override: true,
      llm_model_is_db_override: true,
    })

    renderSettings()

    await waitFor(() => {
      expect(screen.getByLabelText('Custom URL')).toBeInTheDocument()
    })

    expect(screen.getByLabelText('Custom URL')).toHaveValue('http://custom-llama-host:9000/v1')
    expect(screen.getByLabelText('Custom Model')).toHaveValue('custom-model-name')
  })
})
