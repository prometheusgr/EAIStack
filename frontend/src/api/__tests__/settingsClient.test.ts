import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { settingsClient } from '../settingsClient'

/**
 * The subset of Response that authorizedFetch actually reads. Tests supply
 * these fields only, so typing the fetch mock against the full Response would
 * force every literal to carry a dozen irrelevant properties.
 */
type FetchStub = (input: string, init?: RequestInit) => Promise<{
  status: number
  ok: boolean
  statusText?: string
  json?: () => Promise<unknown>
}>

describe('settingsClient', () => {
  const mockToken = 'valid_token'
  let mockFetch: MockedFunction<FetchStub>
  let mockRefresh: MockedFunction<AuthRefresh>

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch = vi.fn() as MockedFunction<FetchStub>
    mockRefresh = vi.fn() as MockedFunction<AuthRefresh>

    global.fetch = mockFetch as unknown as typeof fetch
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

    it('throws ApiError with detail and message on 400 (invalid provider)', async () => {
      // Mirrors the real backend's current response shape
      // (backend/app/api/settings.py's _error_response): `detail` is a
      // stable, machine-readable code, `message` is the human-readable text
      // the Settings screen's toast actually displays -- see
      // ApiErrorImpl.message in authorizedFetch.ts, which never falls back
      // to `detail`.
      mockFetch.mockResolvedValueOnce({
        status: 400,
        ok: false,
        statusText: 'Bad Request',
        json: async () => ({
          detail: 'unknown_llm_provider:not-a-real-provider',
          message: 'Unknown LLM provider: not-a-real-provider',
        }),
      })

      try {
        await settingsClient.updateSettings(
          { llm_provider: 'not-a-real-provider' },
          mockToken,
          mockRefresh
        )
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string; message: string }
        expect(apiError.status).toBe(400)
        expect(apiError.detail).toBe('unknown_llm_provider:not-a-real-provider')
        expect(apiError.message).toBe('Unknown LLM provider: not-a-real-provider')
      }
    })
  })

  describe('createGuardrailPattern', () => {
    it('POSTs /api/settings/guardrail-patterns with label and pattern_text and returns the created pattern', async () => {
      const responseBody = {
        id: 'pattern-1',
        source: 'custom',
        label: 'Block foo',
        pattern_text: 'foo bar',
        enabled: true,
      }
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => responseBody,
      })

      const result = await settingsClient.createGuardrailPattern(
        mockToken,
        mockRefresh,
        'Block foo',
        'foo bar'
      )

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/settings/guardrail-patterns'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ label: 'Block foo', pattern_text: 'foo bar' }),
        })
      )
      expect(result).toEqual(responseBody)
    })
  })

  describe('setGuardrailPatternEnabled', () => {
    it('PUTs /api/settings/guardrail-patterns/{id} with enabled and returns the updated pattern', async () => {
      const responseBody = {
        id: 'pattern-1',
        source: 'built_in',
        label: 'SQL injection',
        pattern_text: null,
        enabled: false,
      }
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => responseBody,
      })

      const result = await settingsClient.setGuardrailPatternEnabled(
        mockToken,
        mockRefresh,
        'pattern-1',
        false
      )

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/settings/guardrail-patterns/pattern-1'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ enabled: false }),
        })
      )
      expect(result).toEqual(responseBody)
    })

    it('throws ApiError with detail on 404 (unknown id)', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 404,
        ok: false,
        statusText: 'Not Found',
        json: async () => ({ detail: 'Guardrail pattern not found' }),
      })

      try {
        await settingsClient.setGuardrailPatternEnabled(mockToken, mockRefresh, 'missing', true)
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(404)
        expect(apiError.detail).toBe('Guardrail pattern not found')
      }
    })
  })

  describe('getAuditLog', () => {
    it('GETs /api/settings/audit and returns the parsed entries', async () => {
      const responseBody = {
        entries: [
          {
            id: 'entry-1',
            actor_user_id: 'admin-1',
            action: 'retention.update',
            field_name: 'conversation_retention_hours',
            old_value: '72',
            new_value: '24',
            created_at: '2026-09-02T00:00:00Z',
          },
        ],
      }
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => responseBody,
      })

      const result = await settingsClient.getAuditLog(mockToken, mockRefresh)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/settings/audit'),
        expect.objectContaining({ method: 'GET' })
      )
      expect(result).toEqual(responseBody)
    })

    it('throws ApiError with detail on 403 (non-admin)', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 403,
        ok: false,
        statusText: 'Forbidden',
        json: async () => ({ detail: 'Admin access required' }),
      })

      try {
        await settingsClient.getAuditLog(mockToken, mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(403)
        expect(apiError.detail).toBe('Admin access required')
      }
    })
  })

  describe('deleteGuardrailPattern', () => {
    it('DELETEs /api/settings/guardrail-patterns/{id}', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 204,
        ok: true,
        json: async () => ({}),
      })

      await settingsClient.deleteGuardrailPattern(mockToken, mockRefresh, 'pattern-1')

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/settings/guardrail-patterns/pattern-1'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })

    it('throws ApiError with detail on 400 (attempting to delete a built-in)', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 400,
        ok: false,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Cannot delete a built-in guardrail pattern' }),
      })

      try {
        await settingsClient.deleteGuardrailPattern(mockToken, mockRefresh, 'built-in-1')
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(400)
        expect(apiError.detail).toBe('Cannot delete a built-in guardrail pattern')
      }
    })
  })
})
