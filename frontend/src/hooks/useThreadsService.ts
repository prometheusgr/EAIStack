import { useAuth } from '@/context/AuthContext'
import { ThreadsService } from '@/services/threadsService'
import type { ThreadHistoryResponse, ThreadListResponse } from '@/types/chat'
import { useApiCall } from './useApiCall'
import { useApiMutation } from './useApiMutation'

export function useThreadsService() {
  const { token, refreshAccessToken } = useAuth()

  const listThreads = useApiCall<ThreadListResponse>(
    async () => {
      if (!token) throw new Error('No auth token available')
      const service = new ThreadsService(token, refreshAccessToken)
      return service.listThreads()
    },
    { immediate: false }
  )

  const getThreadHistory = useApiMutation<string, ThreadHistoryResponse>(async (threadId) => {
    if (!token) throw new Error('No auth token available')
    const service = new ThreadsService(token, refreshAccessToken)
    return service.getThreadHistory(threadId)
  })

  return {
    listThreads,
    getThreadHistory,
  }
}
