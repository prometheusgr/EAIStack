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
})
