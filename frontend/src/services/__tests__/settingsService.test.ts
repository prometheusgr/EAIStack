import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { SettingsService } from '../settingsService'
import { settingsClient } from '@/api/settingsClient'

vi.mock('@/api/settingsClient', () => ({
  settingsClient: {
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
  },
}))

describe('SettingsService', () => {
  const mockToken = 'valid_token'
  let mockRefresh: MockedFunction<AuthRefresh>

  const settingsResponse = {
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
    available_providers: { llm: [], embedding: [] },
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockRefresh = vi.fn() as MockedFunction<AuthRefresh>
  })

  describe('getSettings', () => {
    it('delegates to settingsClient.getSettings with the constructor token', async () => {
      vi.mocked(settingsClient.getSettings).mockResolvedValueOnce(settingsResponse)

      const service = new SettingsService(mockToken, mockRefresh)
      const result = await service.getSettings()

      expect(settingsClient.getSettings).toHaveBeenCalledWith(mockToken, mockRefresh)
      expect(result).toEqual(settingsResponse)
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.getSettings()).rejects.toThrow('No auth token available')
      expect(settingsClient.getSettings).not.toHaveBeenCalled()
    })
  })

  describe('updateSettings', () => {
    it('delegates to settingsClient.updateSettings with the constructor token and payload', async () => {
      const updatedResponse = { ...settingsResponse, llm_provider: 'llama-cpp' }
      vi.mocked(settingsClient.updateSettings).mockResolvedValueOnce(updatedResponse)

      const payload = { llm_provider: 'llama-cpp' }
      const service = new SettingsService(mockToken, mockRefresh)
      const result = await service.updateSettings(payload)

      expect(settingsClient.updateSettings).toHaveBeenCalledWith(payload, mockToken, mockRefresh)
      expect(result.llm_provider).toBe('llama-cpp')
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.updateSettings({ llm_provider: 'fake' })).rejects.toThrow(
        'No auth token available'
      )
      expect(settingsClient.updateSettings).not.toHaveBeenCalled()
    })
  })
})
