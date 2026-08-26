import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { embeddingsClient } from '../embeddingsClient'

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

describe('embeddingsClient', () => {
  const mockToken = 'valid_token'
  const mockNewToken = 'refreshed_token'
  let mockFetch: MockedFunction<FetchStub>
  let mockRefresh: MockedFunction<AuthRefresh>

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch = vi.fn() as MockedFunction<FetchStub>
    mockRefresh = vi.fn() as MockedFunction<AuthRefresh>

    global.fetch = mockFetch as unknown as typeof fetch
    localStorage.clear()
  })

  describe('401 refresh behavior', () => {
    it('should retry with refreshed token on 401 response', async () => {
      mockRefresh.mockResolvedValue(true)
      localStorage.setItem('access_token', mockNewToken)

      // First call: 401, Second call: 200
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
            id: 'emb-1',
            doc_id: 'doc-1',
            title: 'Test',
            content: 'Test content',
          }),
        })

      const result = await embeddingsClient.getEmbedding('emb-1', mockToken, mockRefresh)

      expect(mockRefresh).toHaveBeenCalled()
      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(result.id).toBe('emb-1')
    })

    it('should throw ApiError with detail when refresh fails', async () => {
      mockRefresh.mockResolvedValue(false)

      mockFetch.mockResolvedValueOnce({
        status: 401,
        ok: false,
        statusText: 'Unauthorized',
        json: async () => ({ detail: 'Invalid credentials' }),
      })

      try {
        await embeddingsClient.getEmbedding('emb-1', mockToken, mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string; message: string }
        expect(apiError.status).toBe(401)
        expect(apiError.detail).toBe('Invalid credentials')
        // detail is the internal machine-readable code; message must stay
        // empty (not silently default to detail) when the backend response
        // has no message field.
        expect(apiError.message).toBe('')
      }
    })

    it('should throw ApiError on other non-ok responses', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 500,
        ok: false,
        statusText: 'Internal Server Error',
        json: async () => ({ detail: 'Server error occurred' }),
      })

      try {
        await embeddingsClient.semanticSearch('query', mockToken, mockRefresh, 10)
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(500)
        expect(apiError.detail).toBe('Server error occurred')
      }
    })

    it('should parse error detail from JSON response', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 400,
        ok: false,
        json: async () => ({ detail: 'Invalid query format' }),
      })

      try {
        await embeddingsClient.listEmbeddings(mockToken, mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { detail: string }
        expect(apiError.detail).toBe('Invalid query format')
      }
    })
  })

  describe('normal success cases', () => {
    it('should return embeddings list on 200', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => [
          { id: 'emb-1', doc_id: 'doc-1', title: 'Test 1' },
          { id: 'emb-2', doc_id: 'doc-2', title: 'Test 2' },
        ],
      })

      const result = await embeddingsClient.listEmbeddings(mockToken, mockRefresh)

      expect(result).toHaveLength(2)
      expect(result[0].id).toBe('emb-1')
    })

    it('should handle delete (204 No Content)', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 204,
        ok: true,
      })

      await embeddingsClient.deleteEmbedding('doc-1', mockToken, mockRefresh)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/embeddings/doc-1'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })
})
