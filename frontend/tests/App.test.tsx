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
        available_providers: { llm: [], embedding: [] },
      },
      error: null,
      isLoading: false,
      execute: vi.fn(),
    },
    update: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, error: null, data: null },
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
