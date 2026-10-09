import { useAuth } from '@/context/AuthContext'
import { listAvailableWorkflows, sendChatMessage } from '@/api/agentsClient'
import type { AvailableWorkflow, ChatResponse } from '@/types/chat'
import { useApiCall } from './useApiCall'
import { useApiMutation } from './useApiMutation'

export type { ChatResponse }

export function useChatService() {
  const { token, refreshAccessToken } = useAuth()

  return useApiMutation<{ message: string; threadId?: string; workflow?: string }, ChatResponse>(
    async ({ message, threadId, workflow }) => {
      if (!token) {
        throw new Error('No auth token available')
      }
      return await sendChatMessage(message, threadId, token, refreshAccessToken, workflow)
    }
  )
}

/** The published workflows a new conversation can be started with (issue #85). */
export function useAvailableWorkflows() {
  const { token, refreshAccessToken } = useAuth()

  return useApiCall<AvailableWorkflow[]>(async () => {
    if (!token) throw new Error('No auth token available')
    return await listAvailableWorkflows(token, refreshAccessToken)
  })
}
