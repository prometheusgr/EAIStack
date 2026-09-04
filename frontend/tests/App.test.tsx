import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../src/App'

const mockUseAuth = vi.fn()

vi.mock('../src/context/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

vi.mock('../src/hooks/useSettingsService', () => ({
  useSettingsService: () => ({
    get: {
      data: {
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
        conversation_retention_hours: null,
        conversation_retention_hours_is_db_override: false,
        cleanup_on_logout: true,
        cleanup_on_logout_is_db_override: false,
        knowledge_base_purge_days: null,
        knowledge_base_purge_days_is_db_override: false,
        api_key_purge_days: null,
        api_key_purge_days_is_db_override: false,
        max_input_length: 4000,
        max_input_length_is_db_override: false,
        guardrails_input_enabled: true,
        guardrails_input_enabled_is_db_override: false,
        guardrails_output_enabled: true,
        guardrails_output_enabled_is_db_override: false,
        guardrail_patterns: [],
        available_providers: { llm: [], embedding: [] },
      },
      error: null,
      isLoading: false,
      execute: vi.fn(),
    },
    getDashboard: {
      data: undefined,
      error: null,
      isLoading: false,
      execute: vi.fn(),
    },
    getNavConfig: {
      data: undefined,
      error: null,
      isLoading: false,
      execute: vi.fn(),
    },
    getRetentionNotice: {
      data: undefined,
      error: null,
      isLoading: false,
      execute: vi.fn(),
    },
    update: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, error: null, data: null },
    createGuardrailPattern: {
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
      data: null,
    },
    setGuardrailPatternEnabled: {
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
      data: null,
    },
    deleteGuardrailPattern: {
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
      data: null,
    },
  }),
}))

function baseAuth(overrides: Partial<ReturnType<typeof mockUseAuth>> = {}) {
  return {
    token: 'fake-token-123',
    isAuthenticated: true,
    isLoading: false,
    login: () => {},
    logout: () => {},
    refreshAccessToken: async () => false,
    user: { name: 'Test User', username: 'testuser' },
    roles: [],
    isAdmin: false,
    ...overrides,
  }
}

describe('App login screen auth error (issue #47)', () => {
  it('shows the backend message when authError is set with no retryAfterSeconds', () => {
    mockUseAuth.mockReturnValue(
      baseAuth({
        isAuthenticated: false,
        authError: { message: "That message couldn't be sent. Please rephrase your question." },
      })
    )

    render(<App />)

    expect(
      screen.getByText("That message couldn't be sent. Please rephrase your question.")
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /login/i })).toBeEnabled()
  })

  it('shows a live countdown and disables Login while a rate-limit retryAfterSeconds is counting down', async () => {
    vi.useFakeTimers()
    mockUseAuth.mockReturnValue(
      baseAuth({
        isAuthenticated: false,
        authError: {
          message: 'Too many requests. Please wait before trying again.',
          retryAfterSeconds: 3,
        },
      })
    )

    render(<App />)

    expect(screen.getByText(/too many requests/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry in 3s/i })).toBeDisabled()

    for (let i = 0; i < 3; i++) {
      await vi.advanceTimersByTimeAsync(1000)
    }

    expect(screen.getByRole('button', { name: /^login$/i })).toBeEnabled()
    vi.useRealTimers()
  })
})

describe('App admin gating for the Settings view', () => {
  it('does not show the Settings nav item for a non-admin user', () => {
    mockUseAuth.mockReturnValue(baseAuth({ isAdmin: false }))

    render(<App />)

    expect(screen.queryByRole('button', { name: /Settings/i })).not.toBeInTheDocument()
  })

  it('shows the Settings nav item for an admin user and navigates to it on click', async () => {
    mockUseAuth.mockReturnValue(baseAuth({ isAdmin: true }))
    const user = userEvent.setup()

    render(<App />)

    const settingsButton = screen.getByRole('button', { name: /Settings/i })
    await user.click(settingsButton)

    expect(screen.getByText(/Runtime LLM and embedding provider configuration/i)).toBeInTheDocument()
  })
})
