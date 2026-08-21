import { authorizedFetch, type AuthRefresh } from './authorizedFetch'
import type { ThreadHistoryResponse, ThreadListResponse } from '@/types/chat'

export interface ThreadsClient {
  listThreads(token: string, onRefresh: AuthRefresh): Promise<ThreadListResponse>
  getThreadHistory(
    threadId: string,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<ThreadHistoryResponse>
}

const threadsClient: ThreadsClient = {
  async listThreads(token: string, onRefresh: AuthRefresh): Promise<ThreadListResponse> {
    const response = await authorizedFetch('/api/agents/threads', token, onRefresh, {
      method: 'GET',
    })
    const data = (await response.json()) as {
      threads: { id: string; created_at: string; updated_at: string }[]
    }
    return {
      threads: data.threads.map((t) => ({
        id: t.id,
        createdAt: t.created_at,
        updatedAt: t.updated_at,
      })),
    }
  },

  async getThreadHistory(
    threadId: string,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<ThreadHistoryResponse> {
    const response = await authorizedFetch(
      `/api/agents/threads/${threadId}`,
      token,
      onRefresh,
      { method: 'GET' }
    )
    const data = (await response.json()) as {
      id: string
      messages: { role: 'user' | 'agent'; text: string }[]
    }
    return { id: data.id, messages: data.messages }
  },
}

export { threadsClient }
