import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { workflowsClient } from '../workflowsClient'

type FetchStub = (input: string, init?: RequestInit) => Promise<{
  status: number
  ok: boolean
  json?: () => Promise<unknown>
}>

describe('workflowsClient.testChat (issue #84)', () => {
  let mockFetch: MockedFunction<FetchStub>
  let mockRefresh: MockedFunction<AuthRefresh>

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch = vi.fn() as MockedFunction<FetchStub>
    mockRefresh = vi.fn() as MockedFunction<AuthRefresh>
    global.fetch = mockFetch as unknown as typeof fetch
    mockFetch.mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({
        response: 'Welcome aboard!',
        thread_id: 'test-thread-1',
        sources: [{ knowledge_base_id: 'kb-1', title: 'Handbook', heading_path: null }],
        was_modified: false,
        workflow: 'chat',
        test_version_id: 'v2-id',
        test_version_sequence: 2,
      }),
    })
  })

  it('posts to the version it runs, sending thread_id only for a follow-up', async () => {
    await workflowsClient.testChat('chat', 'v2-id', 'hello', undefined, 'token', mockRefresh)
    await workflowsClient.testChat('chat', 'v2-id', 'again', 'test-thread-1', 'token', mockRefresh)

    const [firstUrl, firstInit] = mockFetch.mock.calls[0]
    expect(firstUrl).toBe('/api/workflows/chat/versions/v2-id/test-chat')
    expect(firstInit?.method).toBe('POST')
    expect(JSON.parse(String(firstInit?.body))).toEqual({ message: 'hello' })
    const [, secondInit] = mockFetch.mock.calls[1]
    expect(JSON.parse(String(secondInit?.body))).toEqual({
      message: 'again',
      thread_id: 'test-thread-1',
    })
  })

  it('returns the reply with the version that ran', async () => {
    const reply = await workflowsClient.testChat(
      'chat',
      'v2-id',
      'hello',
      undefined,
      'token',
      mockRefresh
    )

    expect(reply).toEqual({
      response: 'Welcome aboard!',
      threadId: 'test-thread-1',
      sources: [{ knowledgeBaseId: 'kb-1', title: 'Handbook', headingPath: null }],
      wasModified: false,
      workflow: 'chat',
      testVersionId: 'v2-id',
      testVersionSequence: 2,
    })
  })
})
