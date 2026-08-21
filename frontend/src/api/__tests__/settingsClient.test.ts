import { describe, it, expect, vi, beforeEach } from 'vitest'
import { settingsClient } from '../settingsClient'

describe('settingsClient', () => {
  const mockToken = 'valid_token'
  let mockFetch: ReturnType<typeof vi.fn>
  let mockRefresh: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch = vi.fn()
    mockRefresh = vi.fn()

    global.fetch = mockFetch
    localStorage.clear()
  })

  describe('getSettings', () => {
    it('GETs /api/settings and returns the parsed response', async () => {
      const responseBody = {
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
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => responseBody,
      })

      const result = await settingsClient.getSettings(mockToken, mockRefresh)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/settings'),
        expect.objectContaining({ method: 'GET' })
      )
      expect(result).toEqual(responseBody)
    })

    it('never includes llm_api_key in the parsed response', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({
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
        }),
      })

      const result = await settingsClient.getSettings(mockToken, mockRefresh)

      expect(result).not.toHaveProperty('llm_api_key')
    })

    it('retries with refreshed token on 401 response', async () => {
      mockRefresh.mockResolvedValue(true)
      localStorage.setItem('access_token', 'refreshed_token')

      mockFetch
        .mockResolvedValueOnce({
          status: 401,
          ok: false,
          statusText: 'Unauthorized',
          json: async () => ({ detail: 'Token expired' }),
        })
        .mockResolvedValueOnce({
          status: 200,
          ok: true,
          json: async () => ({
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
          }),
        })

      const result = await settingsClient.getSettings(mockToken, mockRefresh)

      expect(mockRefresh).toHaveBeenCalled()
      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(result.llm_provider).toBe('fake')
    })

    it('throws ApiError with detail on 403 (non-admin)', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 403,
        ok: false,
        statusText: 'Forbidden',
        json: async () => ({ detail: 'Admin access required' }),
      })

      try {
        await settingsClient.getSettings(mockToken, mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(403)
        expect(apiError.detail).toBe('Admin access required')
      }
    })
  })

  describe('updateSettings', () => {
    it('PUTs /api/settings with the given payload', async () => {
      const responseBody = {
        llm_provider: 'llama-cpp',
        llm_url: 'http://llama-server:8000/v1',
        llm_model: 'llama-3',
        llm_provider_is_db_override: true,
        llm_url_is_db_override: true,
        llm_model_is_db_override: true,
        embedding_provider: 'fake',
        embedding_url: '',
        embedding_model: '',
        embedding_provider_is_db_override: false,
        embedding_url_is_db_override: false,
        embedding_model_is_db_override: false,
        available_providers: { llm: [], embedding: [] },
      }
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => responseBody,
      })

      const payload = {
        llm_provider: 'llama-cpp',
        llm_url: 'http://llama-server:8000/v1',
        llm_model: 'llama-3',
      }
      const result = await settingsClient.updateSettings(payload, mockToken, mockRefresh)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/settings'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      )
      expect(result.llm_provider).toBe('llama-cpp')
    })

    it('throws ApiError with detail on 400 (invalid provider)', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 400,
        ok: false,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Unknown llm_provider: not-a-real-provider' }),
      })

      try {
        await settingsClient.updateSettings(
          { llm_provider: 'not-a-real-provider' },
          mockToken,
          mockRefresh
        )
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(400)
        expect(apiError.detail).toBe('Unknown llm_provider: not-a-real-provider')
      }
    })
  })
})
