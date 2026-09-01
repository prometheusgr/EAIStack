import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import type { ReactNode } from 'react'
import { AuthProvider, useAuth } from '../../src/context/AuthContext'
import { useSettingsService } from '../../src/hooks/useSettingsService'
import { settingsClient } from '../../src/api/settingsClient'

vi.mock('../../src/api/settingsClient', () => ({
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

const MOCK_TOKEN = buildToken({
  sub: 'admin-1',
  preferred_username: 'admin',
  exp: 9999999999,
  realm_access: { roles: ['admin'] },
})

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

/** Renders useSettingsService alongside useAuth so tests can wait for the
 * AuthProvider's async init to finish before exercising the hook — token
 * is null until initAuth() resolves.
 */
function useSettingsServiceHarness() {
  const auth = useAuth()
  const service = useSettingsService()
  return { ...service, isAuthLoading: auth.isLoading }
}

const SETTINGS_RESPONSE = {
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
  guardrail_patterns: [],
  available_providers: { llm: [], embedding: [] },
}

describe('useSettingsService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('access_token', MOCK_TOKEN)
  })

  it('get.execute() loads settings and reflects success state', async () => {
    vi.mocked(settingsClient.getSettings).mockResolvedValue(SETTINGS_RESPONSE)

    const { result } = renderHook(() => useSettingsServiceHarness(), { wrapper })
    await waitFor(() => expect(result.current.isAuthLoading).toBe(false))

    await act(async () => {
      await result.current.get.execute()
    })

    await waitFor(() => {
      expect(result.current.get.data).toEqual(SETTINGS_RESPONSE)
      expect(result.current.get.error).toBeNull()
      expect(result.current.get.isLoading).toBe(false)
    })
  })

  it('get.execute() reflects error state when the client rejects', async () => {
    vi.mocked(settingsClient.getSettings).mockRejectedValue(new Error('Admin access required'))

    const { result } = renderHook(() => useSettingsServiceHarness(), { wrapper })
    await waitFor(() => expect(result.current.isAuthLoading).toBe(false))

    await act(async () => {
      await result.current.get.execute()
    })

    await waitFor(() => {
      expect(result.current.get.error).not.toBeNull()
      expect(result.current.get.error?.message).toBe('Admin access required')
    })
  })

  it('update.mutateAsync() calls settingsClient.updateSettings with the payload', async () => {
    vi.mocked(settingsClient.updateSettings).mockResolvedValue({
      ...SETTINGS_RESPONSE,
      llm_provider: 'llama-cpp',
      llm_provider_is_db_override: true,
    })

    const { result } = renderHook(() => useSettingsServiceHarness(), { wrapper })
    await waitFor(() => expect(result.current.isAuthLoading).toBe(false))

    await act(async () => {
      await result.current.update.mutateAsync({ llm_provider: 'llama-cpp' })
    })

    expect(settingsClient.updateSettings).toHaveBeenCalledWith(
      { llm_provider: 'llama-cpp' },
      MOCK_TOKEN,
      expect.any(Function)
    )
    expect(result.current.update.data?.llm_provider).toBe('llama-cpp')
  })

  it('update.mutateAsync() reflects error state when the client rejects', async () => {
    vi.mocked(settingsClient.updateSettings).mockRejectedValue(
      new Error('Unknown llm_provider: bogus')
    )

    const { result } = renderHook(() => useSettingsServiceHarness(), { wrapper })
    await waitFor(() => expect(result.current.isAuthLoading).toBe(false))

    await act(async () => {
      try {
        await result.current.update.mutateAsync({ llm_provider: 'bogus' })
      } catch {
        // Error is captured in hook state below; rethrow is expected from mutateAsync.
      }
    })

    await waitFor(() => {
      expect(result.current.update.error?.message).toBe('Unknown llm_provider: bogus')
    })
  })

  it('createGuardrailPattern.mutateAsync() calls settingsClient.createGuardrailPattern with the constructor token', async () => {
    vi.mocked(settingsClient.createGuardrailPattern).mockResolvedValue({
      id: 'pattern-1',
      source: 'custom',
      label: 'Block foo',
      pattern_text: 'foo bar',
      enabled: true,
    })

    const { result } = renderHook(() => useSettingsServiceHarness(), { wrapper })
    await waitFor(() => expect(result.current.isAuthLoading).toBe(false))

    await act(async () => {
      await result.current.createGuardrailPattern.mutateAsync({
        label: 'Block foo',
        patternText: 'foo bar',
      })
    })

    expect(settingsClient.createGuardrailPattern).toHaveBeenCalledWith(
      MOCK_TOKEN,
      expect.any(Function),
      'Block foo',
      'foo bar'
    )
    expect(result.current.createGuardrailPattern.data?.id).toBe('pattern-1')
  })

  it('setGuardrailPatternEnabled.mutateAsync() calls settingsClient.setGuardrailPatternEnabled with the constructor token', async () => {
    vi.mocked(settingsClient.setGuardrailPatternEnabled).mockResolvedValue({
      id: 'pattern-1',
      source: 'built_in',
      label: 'SQL injection',
      pattern_text: null,
      enabled: false,
    })

    const { result } = renderHook(() => useSettingsServiceHarness(), { wrapper })
    await waitFor(() => expect(result.current.isAuthLoading).toBe(false))

    await act(async () => {
      await result.current.setGuardrailPatternEnabled.mutateAsync({
        id: 'pattern-1',
        enabled: false,
      })
    })

    expect(settingsClient.setGuardrailPatternEnabled).toHaveBeenCalledWith(
      MOCK_TOKEN,
      expect.any(Function),
      'pattern-1',
      false
    )
    expect(result.current.setGuardrailPatternEnabled.data?.enabled).toBe(false)
  })

  it('deleteGuardrailPattern.mutateAsync() calls settingsClient.deleteGuardrailPattern with the constructor token', async () => {
    vi.mocked(settingsClient.deleteGuardrailPattern).mockResolvedValue(undefined)

    const { result } = renderHook(() => useSettingsServiceHarness(), { wrapper })
    await waitFor(() => expect(result.current.isAuthLoading).toBe(false))

    await act(async () => {
      await result.current.deleteGuardrailPattern.mutateAsync('pattern-1')
    })

    expect(settingsClient.deleteGuardrailPattern).toHaveBeenCalledWith(
      MOCK_TOKEN,
      expect.any(Function),
      'pattern-1'
    )
  })
})
