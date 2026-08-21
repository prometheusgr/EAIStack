import { describe, it, expect, vi, beforeEach } from 'vitest'
import { threadsClient } from '../threadsClient'

describe('threadsClient', () => {
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
