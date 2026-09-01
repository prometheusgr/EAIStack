import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Settings } from './Settings'
import { ToastProvider } from './ui/toast'
import { TooltipProvider } from './ui/tooltip'
import { AuthProvider } from '../context/AuthContext'
import { settingsClient } from '../api/settingsClient'
import type { SystemSettingsResponse } from '../types/settings'

vi.mock('../api/settingsClient', () => ({
  settingsClient: {
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
    createGuardrailPattern: vi.fn(),
    setGuardrailPatternEnabled: vi.fn(),
    deleteGuardrailPattern: vi.fn(),
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

const ENV_DEFAULT_SETTINGS: SystemSettingsResponse = {
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
  max_input_length: 4000,
  max_input_length_is_db_override: false,
  guardrails_input_enabled: true,
  guardrails_input_enabled_is_db_override: false,
  guardrails_output_enabled: true,
  guardrails_output_enabled_is_db_override: false,
  tracing_enabled: false,
  tracing_enabled_is_db_override: false,
  rate_limit_enabled: true,
  rate_limit_enabled_is_db_override: false,
  rate_limit_chat_capacity: 10,
  rate_limit_chat_capacity_is_db_override: false,
  rate_limit_chat_refill_per_minute: 10,
  rate_limit_chat_refill_per_minute_is_db_override: false,
  rate_limit_auth_capacity: 10,
  rate_limit_auth_capacity_is_db_override: false,
  rate_limit_auth_refill_per_minute: 10,
  rate_limit_auth_refill_per_minute_is_db_override: false,
  guardrail_patterns: [
    {
      id: 'built-in-1',
      source: 'built_in',
      label: 'SQL injection',
      pattern_text: null,
      enabled: true,
    },
    {
      id: 'custom-1',
      source: 'custom',
      label: 'Block foo',
      pattern_text: 'foo bar',
      enabled: true,
    },
  ],
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
        <TooltipProvider>
          <Settings />
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  )
}

describe('Settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('access_token', ADMIN_TOKEN)
    vi.mocked(settingsClient.createGuardrailPattern).mockResolvedValue({
      id: 'new-pattern',
      source: 'custom',
      label: 'New pattern',
      pattern_text: 'new phrase',
      enabled: true,
    })
    vi.mocked(settingsClient.setGuardrailPatternEnabled).mockResolvedValue({
      id: 'built-in-1',
      source: 'built_in',
      label: 'SQL injection',
      pattern_text: null,
      enabled: false,
    })
    vi.mocked(settingsClient.deleteGuardrailPattern).mockResolvedValue(undefined)
  })

  it('shows a common-setups reference panel naming at least two named configurations', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)

    renderSettings()

    const guide = await screen.findByRole('region', { name: /common setups/i })
    expect(within(guide).getByText(/privacy-sensitive/i)).toBeInTheDocument()
    expect(within(guide).getByText(/general-purpose/i)).toBeInTheDocument()
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

    // Scoped to the LLM Provider section specifically: "Reset to default" is
    // no longer a unique button label on this page now that the Guardrails
    // section (see below) has its own max_input_length reset button with
    // the same text.
    const llmSection = await screen.findByRole('region', { name: 'LLM configuration' })
    const llmResetButton = await within(llmSection).findByRole('button', {
      name: /reset to default/i,
    })
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

describe('Settings guardrails section', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('access_token', ADMIN_TOKEN)
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
    vi.mocked(settingsClient.updateSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
    vi.mocked(settingsClient.createGuardrailPattern).mockResolvedValue({
      id: 'new-pattern',
      source: 'custom',
      label: 'New pattern',
      pattern_text: 'new phrase',
      enabled: true,
    })
    vi.mocked(settingsClient.setGuardrailPatternEnabled).mockResolvedValue({
      id: 'built-in-1',
      source: 'built_in',
      label: 'SQL injection',
      pattern_text: null,
      enabled: false,
    })
    vi.mocked(settingsClient.deleteGuardrailPattern).mockResolvedValue(undefined)
  })

  async function waitForGuardrailsLoaded() {
    await waitFor(() => {
      expect(settingsClient.getSettings).toHaveBeenCalled()
    })
    const input = await screen.findByLabelText(/maximum input length/i)
    await waitFor(() => {
      expect(input).not.toHaveValue(null)
    })
    return input
  }

  it('renders the guardrails section with fetched values', async () => {
    renderSettings()

    const maxInputLength = await waitForGuardrailsLoaded()

    expect(maxInputLength).toHaveValue(4000)
    expect(screen.getByLabelText(/reject unsafe input/i)).toBeChecked()
    expect(screen.getByLabelText(/filter unsafe output/i)).toBeChecked()

    const guardrailsSection = screen.getByRole('region', { name: /guardrails/i })
    expect(guardrailsSection).toHaveTextContent(/env default/i)
  })

  it('shows "overridden" for guardrail fields with a DB override', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      max_input_length: 2000,
      max_input_length_is_db_override: true,
    })

    renderSettings()
    await waitForGuardrailsLoaded()

    const guardrailsSection = screen.getByRole('region', { name: /guardrails/i })
    expect(guardrailsSection).toHaveTextContent(/overridden/i)
  })

  it('shows an inline warning when turning off "reject unsafe input", and hides it when re-enabled', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    const inputToggle = screen.getByLabelText(/reject unsafe input/i)
    await user.click(inputToggle)

    expect(
      screen.getByText(/removes protection against unsafe input/i)
    ).toBeInTheDocument()

    await user.click(inputToggle)

    expect(
      screen.queryByText(/removes protection against unsafe input/i)
    ).not.toBeInTheDocument()
  })

  it('shows an inline warning when turning off "filter unsafe output"', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    const outputToggle = screen.getByLabelText(/filter unsafe output/i)
    await user.click(outputToggle)

    expect(
      screen.getByText(/removes protection against unsafe output/i)
    ).toBeInTheDocument()
  })

  it('does not show a warning when a toggle is already off and stays off', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      guardrails_input_enabled: false,
    })

    renderSettings()
    await waitForGuardrailsLoaded()

    expect(
      screen.queryByText(/removes protection against unsafe input/i)
    ).not.toBeInTheDocument()
  })

  it('editing max_input_length and saving sends the right payload without clobbering retention fields', async () => {
    const user = userEvent.setup()
    renderSettings()

    const maxInputLength = await waitForGuardrailsLoaded()
    await user.clear(maxInputLength)
    await user.type(maxInputLength, '2000')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })

    const payload = vi.mocked(settingsClient.updateSettings).mock.calls[0][0]
    expect(payload).toMatchObject({
      max_input_length: 2000,
      conversation_retention_hours: 24,
      knowledge_base_purge_days: 30,
      api_key_purge_days: 30,
    })
  })

  it('sends null for max_input_length when its "Reset to default" is clicked', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      max_input_length: 2000,
      max_input_length_is_db_override: true,
    })

    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    const maxInputLengthResetButton = screen.getByRole('button', {
      name: /reset to default/i,
    })
    await user.click(maxInputLengthResetButton)
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })

    const payload = vi.mocked(settingsClient.updateSettings).mock.calls[0][0]
    expect(payload.max_input_length).toBeNull()
  })

  it('turning off a guardrail toggle and saving sends false in the payload', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    await user.click(screen.getByLabelText(/reject unsafe input/i))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })

    const payload = vi.mocked(settingsClient.updateSettings).mock.calls[0][0]
    expect(payload).toMatchObject({ guardrails_input_enabled: false })
  })

  it('renders the tracing toggle reflecting its env-default state', async () => {
    renderSettings()
    await waitForGuardrailsLoaded()

    const tracingToggle = screen.getByLabelText(/enable llm tracing/i) as HTMLInputElement
    expect(tracingToggle.checked).toBe(false)
    expect(screen.getByText(/enable llm tracing \(env default\)/i)).toBeInTheDocument()
  })

  it('reflects tracing_enabled_is_db_override as "Overridden"', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      tracing_enabled: true,
      tracing_enabled_is_db_override: true,
    })

    renderSettings()
    await waitForGuardrailsLoaded()

    const tracingToggle = screen.getByLabelText(/enable llm tracing/i) as HTMLInputElement
    expect(tracingToggle.checked).toBe(true)
    expect(screen.getByText(/enable llm tracing \(overridden\)/i)).toBeInTheDocument()
  })

  it('turning on tracing and saving sends true in the payload', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    await user.click(screen.getByLabelText(/enable llm tracing/i))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })

    const payload = vi.mocked(settingsClient.updateSettings).mock.calls[0][0]
    expect(payload).toMatchObject({ tracing_enabled: true })
  })

  it('renders built-in pattern rows without a delete button', async () => {
    renderSettings()
    await waitForGuardrailsLoaded()

    const builtInRow = screen.getByText('SQL injection').closest('li') as HTMLElement
    expect(within(builtInRow).queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
  })

  it('renders custom pattern rows with a delete button and the pattern text', async () => {
    renderSettings()
    await waitForGuardrailsLoaded()

    const customRow = screen.getByText('Block foo').closest('li') as HTMLElement
    expect(within(customRow).getByText('foo bar')).toBeInTheDocument()
    expect(within(customRow).getByRole('button', { name: /delete/i })).toBeInTheDocument()
  })

  it('toggling a pattern checkbox calls the enable mutation with the right id and value', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    const builtInRow = screen.getByText('SQL injection').closest('li') as HTMLElement
    await user.click(within(builtInRow).getByRole('checkbox'))

    await waitFor(() => {
      expect(settingsClient.setGuardrailPatternEnabled).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Function),
        'built-in-1',
        false
      )
    })
  })

  it('shows a toast after successfully toggling a pattern', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    const builtInRow = screen.getByText('SQL injection').closest('li') as HTMLElement
    await user.click(within(builtInRow).getByRole('checkbox'))

    expect(await screen.findByText(/pattern updated/i)).toBeInTheDocument()
  })

  it('submitting the add-custom-pattern form calls the create mutation and clears the form', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    const labelInput = screen.getByLabelText(/pattern label/i)
    const phraseInput = screen.getByLabelText(/pattern phrase/i)
    await user.type(labelInput, 'Block bar')
    await user.type(phraseInput, 'bar baz')
    await user.click(screen.getByRole('button', { name: /add pattern/i }))

    await waitFor(() => {
      expect(settingsClient.createGuardrailPattern).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Function),
        'Block bar',
        'bar baz'
      )
    })

    await waitFor(() => {
      expect(labelInput).toHaveValue('')
      expect(phraseInput).toHaveValue('')
    })
  })

  it('the add-pattern submit button is disabled until both fields are non-empty', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    const submitButton = screen.getByRole('button', { name: /add pattern/i })
    expect(submitButton).toBeDisabled()

    await user.type(screen.getByLabelText(/pattern label/i), 'Block bar')
    expect(submitButton).toBeDisabled()

    await user.type(screen.getByLabelText(/pattern phrase/i), 'bar baz')
    expect(submitButton).not.toBeDisabled()
  })

  it('clicking delete on a custom pattern calls the delete mutation with the right id', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForGuardrailsLoaded()

    const customRow = screen.getByText('Block foo').closest('li') as HTMLElement
    await user.click(within(customRow).getByRole('button', { name: /delete/i }))

    await waitFor(() => {
      expect(settingsClient.deleteGuardrailPattern).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Function),
        'custom-1'
      )
    })
  })
})

describe('Settings rate limiting section', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('access_token', ADMIN_TOKEN)
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
    vi.mocked(settingsClient.updateSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
  })

  async function waitForRateLimitLoaded() {
    await waitFor(() => {
      expect(settingsClient.getSettings).toHaveBeenCalled()
    })
    const input = await screen.findByLabelText(/chat burst capacity/i)
    await waitFor(() => {
      expect(input).not.toHaveValue(null)
    })
    return input
  }

  it('renders the rate limiting section with fetched values', async () => {
    renderSettings()
    await waitForRateLimitLoaded()

    expect(screen.getByLabelText(/enable rate limiting/i)).toBeChecked()
    expect(screen.getByLabelText(/chat burst capacity/i)).toHaveValue(10)
    expect(screen.getByLabelText(/chat refill rate/i)).toHaveValue(10)
    expect(screen.getByLabelText(/login burst capacity/i)).toHaveValue(10)
    expect(screen.getByLabelText(/login refill rate/i)).toHaveValue(10)

    const section = screen.getByRole('region', { name: /rate limiting/i })
    expect(section).toHaveTextContent(/env default/i)
  })

  it('shows "overridden" for rate limit fields with a DB override', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue({
      ...ENV_DEFAULT_SETTINGS,
      rate_limit_chat_capacity: 5,
      rate_limit_chat_capacity_is_db_override: true,
    })

    renderSettings()
    await waitForRateLimitLoaded()

    const section = screen.getByRole('region', { name: /rate limiting/i })
    expect(section).toHaveTextContent(/overridden/i)
  })

  it('editing the chat refill rate and saving sends the right payload', async () => {
    const user = userEvent.setup()
    renderSettings()
    const chatRefill = await waitForRateLimitLoaded()
    void chatRefill

    const refillInput = screen.getByLabelText(/chat refill rate/i)
    await user.clear(refillInput)
    await user.type(refillInput, '20')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })

    const payload = vi.mocked(settingsClient.updateSettings).mock.calls[0][0]
    expect(payload).toMatchObject({ rate_limit_chat_refill_per_minute: 20 })
  })

  it('turning off rate limiting and saving sends false in the payload', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitForRateLimitLoaded()

    await user.click(screen.getByLabelText(/enable rate limiting/i))
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      expect(settingsClient.updateSettings).toHaveBeenCalled()
    })

    const payload = vi.mocked(settingsClient.updateSettings).mock.calls[0][0]
    expect(payload).toMatchObject({ rate_limit_enabled: false })
  })
})

describe('Settings field help tooltips', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('access_token', ADMIN_TOKEN)
    vi.mocked(settingsClient.getSettings).mockResolvedValue(ENV_DEFAULT_SETTINGS)
  })

  it('shows help text for the LLM provider field on hover', async () => {
    const user = userEvent.setup()
    renderSettings()

    const providerLabel = (await screen.findByText('Provider', {
      selector: 'label[for="llm-provider-select"]',
    })) as HTMLElement
    const trigger = within(providerLabel.parentElement as HTMLElement).getByRole('button', {
      name: 'Show help',
    })
    await user.hover(trigger)

    expect(
      await screen.findByText(/which service generates chat responses/i)
    ).toBeInTheDocument()
  })

  it('shows help text for the conversation retention field on hover', async () => {
    const user = userEvent.setup()
    renderSettings()

    const retentionLabel = (await screen.findByText(/conversation history \(hours\)/i, {
      selector: 'label[for="conversation-retention-hours"]',
    })) as HTMLElement
    const trigger = within(retentionLabel.parentElement as HTMLElement).getByRole('button', {
      name: 'Show help',
    })
    await user.hover(trigger)

    expect(await screen.findByText(/leave empty to keep conversations forever/i)).toBeInTheDocument()
  })

  it('shows help text for the rate limit chat capacity field on hover', async () => {
    const user = userEvent.setup()
    renderSettings()

    const capacityLabel = (await screen.findByText(/chat burst capacity/i, {
      selector: 'label[for="rate-limit-chat-capacity"]',
    })) as HTMLElement
    const trigger = within(capacityLabel.parentElement as HTMLElement).getByRole('button', {
      name: 'Show help',
    })
    await user.hover(trigger)

    expect(await screen.findByText(/maximum number of chat requests/i)).toBeInTheDocument()
  })
})
