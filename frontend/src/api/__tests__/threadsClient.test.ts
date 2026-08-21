import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { threadsClient } from '../threadsClient'

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

describe('threadsClient', () => {
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

  describe('listThreads', () => {
    it('GETs /api/agents/threads and maps snake_case fields to camelCase', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({
          threads: [
            { id: 'thread-1', created_at: '2026-08-20T00:00:00Z', updated_at: '2026-08-20T01:00:00Z' },
          ],
        }),
      })

      const result = await threadsClient.listThreads(mockToken, mockRefresh)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agents/threads'),
        expect.objectContaining({ method: 'GET' })
      )
      expect(result).toEqual({
        threads: [{ id: 'thread-1', createdAt: '2026-08-20T00:00:00Z', updatedAt: '2026-08-20T01:00:00Z' }],
      })
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
          json: async () => ({ threads: [] }),
        })

      const result = await threadsClient.listThreads(mockToken, mockRefresh)

      expect(mockRefresh).toHaveBeenCalled()
      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(result.threads).toEqual([])
    })
  })

  describe('getThreadHistory', () => {
    it('GETs /api/agents/threads/{threadId} and returns the parsed response', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({
          id: 'thread-1',
          messages: [{ role: 'user', text: 'Hello' }],
        }),
      })

      const result = await threadsClient.getThreadHistory('thread-1', mockToken, mockRefresh)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agents/threads/thread-1'),
        expect.objectContaining({ method: 'GET' })
      )
      expect(result).toEqual({ id: 'thread-1', messages: [{ role: 'user', text: 'Hello' }] })
    })

    it('throws ApiError with detail on 404 (not found or not owned)', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 404,
        ok: false,
        statusText: 'Not Found',
        json: async () => ({ detail: 'Thread not found' }),
      })

      try {
        await threadsClient.getThreadHistory('unknown-thread', mockToken, mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(404)
        expect(apiError.detail).toBe('Thread not found')
      }
    })
  })
})
