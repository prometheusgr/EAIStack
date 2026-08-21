import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { ThreadsService } from '../threadsService'
import { threadsClient } from '@/api/threadsClient'

vi.mock('@/api/threadsClient', () => ({
  threadsClient: {
    listThreads: vi.fn(),
    getThreadHistory: vi.fn(),
  },
}))

describe('ThreadsService', () => {
  const mockToken = 'valid_token'
  let mockRefresh: MockedFunction<AuthRefresh>

  beforeEach(() => {
    vi.clearAllMocks()
    mockRefresh = vi.fn() as MockedFunction<AuthRefresh>
  })

  describe('listThreads', () => {
    it('delegates to threadsClient.listThreads with the constructor token', async () => {
      const response = { threads: [{ id: 'thread-1', createdAt: 'a', updatedAt: 'b' }] }
      vi.mocked(threadsClient.listThreads).mockResolvedValueOnce(response)

      const service = new ThreadsService(mockToken, mockRefresh)
      const result = await service.listThreads()

      expect(threadsClient.listThreads).toHaveBeenCalledWith(mockToken, mockRefresh)
      expect(result).toEqual(response)
    })

    it('throws if no token is available', async () => {
      const service = new ThreadsService('', mockRefresh)

      await expect(service.listThreads()).rejects.toThrow('No auth token available')
      expect(threadsClient.listThreads).not.toHaveBeenCalled()
    })
  })

  describe('getThreadHistory', () => {
    it('delegates to threadsClient.getThreadHistory with the constructor token and threadId', async () => {
      const response = { id: 'thread-1', messages: [{ role: 'user' as const, text: 'Hi' }] }
      vi.mocked(threadsClient.getThreadHistory).mockResolvedValueOnce(response)

      const service = new ThreadsService(mockToken, mockRefresh)
      const result = await service.getThreadHistory('thread-1')

      expect(threadsClient.getThreadHistory).toHaveBeenCalledWith(
        'thread-1',
        mockToken,
        mockRefresh
      )
      expect(result).toEqual(response)
    })

    it('throws if no token is available', async () => {
      const service = new ThreadsService('', mockRefresh)

      await expect(service.getThreadHistory('thread-1')).rejects.toThrow(
        'No auth token available'
      )
      expect(threadsClient.getThreadHistory).not.toHaveBeenCalled()
    })
  })
})
