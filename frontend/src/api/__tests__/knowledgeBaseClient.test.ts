import { describe, it, expect, vi, beforeEach } from 'vitest'
import { knowledgeBaseClient } from '../knowledgeBaseClient'

describe('knowledgeBaseClient', () => {
  const mockToken = 'valid_token'
  const mockNewToken = 'refreshed_token'
  let mockFetch: ReturnType<typeof vi.fn>
  let mockRefresh: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch = vi.fn()
    mockRefresh = vi.fn()

    global.fetch = mockFetch
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
            id: 'kb-1',
            user_id: 'user-1',
            title: 'Test KB',
            content: 'Content here',
          }),
        })

      const result = await knowledgeBaseClient.get('kb-1', mockToken, mockRefresh)

      expect(mockRefresh).toHaveBeenCalled()
      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(result.id).toBe('kb-1')
    })

    it('should throw ApiError with detail when refresh fails', async () => {
      mockRefresh.mockResolvedValue(false)

      mockFetch.mockResolvedValueOnce({
        status: 401,
        ok: false,
        json: async () => ({ detail: 'Invalid credentials' }),
      })

      try {
        await knowledgeBaseClient.delete('kb-1', mockToken, mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: any) {
        expect(error.status).toBe(401)
        expect(error.detail).toBe('Invalid credentials')
      }
    })

    it('should throw ApiError on server error', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 500,
        ok: false,
        json: async () => ({ detail: 'Internal server error' }),
      })

      try {
        await knowledgeBaseClient.create('Title', 'Content', mockToken, mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: any) {
        expect(error.status).toBe(500)
        expect(error.detail).toBe('Internal server error')
      }
    })
  })

  describe('normal success cases', () => {
    it('should create knowledge base on 201', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 201,
        ok: true,
        json: async () => ({
          id: 'kb-1',
          user_id: 'user-1',
          title: 'New KB',
          content: 'Content',
        }),
      })

      const result = await knowledgeBaseClient.create('New KB', 'Content', mockToken, mockRefresh)

      expect(result.id).toBe('kb-1')
    })

    it('should update knowledge base on 200', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({
          id: 'kb-1',
          user_id: 'user-1',
          title: 'Updated Title',
          content: 'Updated content',
        }),
      })

      const result = await knowledgeBaseClient.update('kb-1', 'Updated Title', 'Updated content', mockToken, mockRefresh)

      expect(result.title).toBe('Updated Title')
    })

    it('should delete knowledge base on 204', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 204,
        ok: true,
      })

      await knowledgeBaseClient.delete('kb-1', mockToken, mockRefresh)

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/knowledge-base/kb-1'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })
})
