import { ChatRequest, ChatResponse } from '@/types/chat'
import { authorizedFetch, type AuthRefresh } from '@/api/authorizedFetch'

export class ChatService {
  constructor(
    private token: string,
    private onRefresh: AuthRefresh = async () => true
  ) {}

  async sendMessage(message: string, threadId?: string): Promise<ChatResponse> {
    const request: ChatRequest = {
      message,
      threadId,
    }

    if (!this.onRefresh) {
      throw new Error('Auth refresh callback is required')
    }

    const response = await authorizedFetch('/api/agents/chat', this.token, this.onRefresh, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`Chat request failed: ${response.statusText}`)
    }

    const data = (await response.json()) as {
      response: string
      thread_id: string
    }

    return {
      response: data.response,
      threadId: data.thread_id,
    }
  }
}
