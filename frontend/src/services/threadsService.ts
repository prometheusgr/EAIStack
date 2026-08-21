import { threadsClient } from '@/api/threadsClient'
import type { AuthRefresh } from '@/api/authorizedFetch'
import type { ThreadHistoryResponse, ThreadListResponse } from '@/types/chat'

export class ThreadsService {
  constructor(
    private token: string,
    private onRefresh: AuthRefresh
  ) {}

  async listThreads(): Promise<ThreadListResponse> {
    if (!this.token) throw new Error('No auth token available')
    return threadsClient.listThreads(this.token, this.onRefresh)
  }

  async getThreadHistory(threadId: string): Promise<ThreadHistoryResponse> {
    if (!this.token) throw new Error('No auth token available')
    return threadsClient.getThreadHistory(threadId, this.token, this.onRefresh)
  }
}
