import { useAuth } from '@/context/AuthContext'
import { sendChatMessage } from '@/api/agentsClient'
import type { ChatResponse } from '@/types/chat'
import { useApiMutation } from './useApiMutation'

export type { ChatResponse }

export function useChatService() {
  const { token, refreshAccessToken } = useAuth()

  return useApiMutation<{ message: string; threadId?: string }, ChatResponse>(
    async ({ message, threadId }) => {
      if (!token) {
        throw new Error('No auth token available')
      }
      return await sendChatMessage(message, threadId, token, refreshAccessToken)
    }
  )
}
