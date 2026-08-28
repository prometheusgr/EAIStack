import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { knowledgeBaseClient } from '../knowledgeBaseClient'

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

describe('knowledgeBaseClient', () => {
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
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(401)
        expect(apiError.detail).toBe('Invalid credentials')
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
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(500)
        expect(apiError.detail).toBe('Internal server error')
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

  describe('upload', () => {
    it('should POST the file as multipart form data to the upload endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 201,
        ok: true,
        json: async () => ({
          id: 'kb-1',
          user_id: 'user-1',
          title: 'spec.pdf',
          content: 'Extracted text',
          storage_key: 'user-1/kb-1/spec.pdf',
          original_filename: 'spec.pdf',
          content_type: 'application/pdf',
        }),
      })

      const file = new File(['file bytes'], 'spec.pdf', { type: 'application/pdf' })
      const result = await knowledgeBaseClient.upload(file, mockToken, mockRefresh)

      expect(result.id).toBe('kb-1')
      expect(result.storage_key).toBe('user-1/kb-1/spec.pdf')

      const [url, init] = mockFetch.mock.calls[0]
      expect(url).toContain('/api/knowledge-base/upload')
      expect(init?.method).toBe('POST')
      expect(init?.body).toBeInstanceOf(FormData)
      // No explicit Content-Type: the browser must set the multipart
      // boundary itself: fetch() computes it from the FormData body, and
      // a manually-set header here would omit that boundary and break
      // the server's multipart parser.
      expect((init?.headers as Record<string, string> | undefined)?.['Content-Type']).toBeUndefined()
    })

    it('should reject on 415 with the server-provided detail', async () => {
      mockFetch.mockResolvedValueOnce({
        status: 415,
        ok: false,
        json: async () => ({ detail: 'Unsupported file type: application/x-executable' }),
      })

      const file = new File(['bytes'], 'virus.exe', { type: 'application/x-executable' })

      try {
        await knowledgeBaseClient.upload(file, mockToken, mockRefresh)
        expect.fail('Should have thrown')
      } catch (error: Error | unknown) {
        const apiError = error as { status: number; detail: string }
        expect(apiError.status).toBe(415)
        expect(apiError.detail).toBe('Unsupported file type: application/x-executable')
      }
    })
  })
})
