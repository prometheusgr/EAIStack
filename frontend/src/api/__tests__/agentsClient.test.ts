import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { listAvailableWorkflows, sendChatMessage } from '../agentsClient'

type FetchStub = (input: string, init?: RequestInit) => Promise<{
  status: number
  ok: boolean
  json?: () => Promise<unknown>
}>

const OK_RESPONSE = {
  status: 200,
  ok: true,
  json: async () => ({ response: 'hi', thread_id: 'thread-1', sources: [], was_modified: false }),
}

function sentBody(mockFetch: MockedFunction<FetchStub>): Record<string, unknown> {
  const [, init] = mockFetch.mock.calls[0]
  return JSON.parse(String(init?.body))
}

describe('sendChatMessage', () => {
  let mockFetch: MockedFunction<FetchStub>
  let mockRefresh: MockedFunction<AuthRefresh>

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch = vi.fn() as MockedFunction<FetchStub>
    mockRefresh = vi.fn() as MockedFunction<AuthRefresh>
    global.fetch = mockFetch as unknown as typeof fetch
  })

  it('sends the thread id as thread_id, the field the backend reads', async () => {
    // The backend's ChatRequest model reads `thread_id`. Sending `threadId`
    // was silently dropped, so every follow-up message started a brand-new
    // conversation with no memory of the previous turns.
    mockFetch.mockResolvedValueOnce(OK_RESPONSE)

    await sendChatMessage('follow-up', 'thread-1', 'token', mockRefresh)

    expect(sentBody(mockFetch)).toEqual({ message: 'follow-up', thread_id: 'thread-1' })
  })

  it('omits thread_id when starting a new conversation', async () => {
    mockFetch.mockResolvedValueOnce(OK_RESPONSE)

    await sendChatMessage('hello', undefined, 'token', mockRefresh)

    expect(sentBody(mockFetch)).toEqual({ message: 'hello' })
  })
})

describe('sendChatMessage workflow selection (issue #85)', () => {
  let mockFetch: MockedFunction<FetchStub>
  let mockRefresh: MockedFunction<AuthRefresh>

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch = vi.fn() as MockedFunction<FetchStub>
    mockRefresh = vi.fn() as MockedFunction<AuthRefresh>
    global.fetch = mockFetch as unknown as typeof fetch
  })

  it('sends the chosen workflow when starting a new conversation', async () => {
    mockFetch.mockResolvedValueOnce(OK_RESPONSE)

    await sendChatMessage('hello', undefined, 'token', mockRefresh, 'triage')

    expect(sentBody(mockFetch)).toEqual({ message: 'hello', workflow: 'triage' })
  })

  it('does not send a workflow for a follow-up, which keeps its bound workflow', async () => {
    mockFetch.mockResolvedValueOnce(OK_RESPONSE)

    await sendChatMessage('again', 'thread-1', 'token', mockRefresh, 'triage')

    expect(sentBody(mockFetch)).toEqual({ message: 'again', thread_id: 'thread-1' })
  })

  it('returns the workflow that answered', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => ({
        response: 'hi',
        thread_id: 'thread-1',
        sources: [],
        was_modified: false,
        workflow: 'triage',
      }),
    })

    const result = await sendChatMessage('hello', undefined, 'token', mockRefresh, 'triage')

    expect(result.workflow).toBe('triage')
  })
})

describe('listAvailableWorkflows', () => {
  it('GETs /api/agents/workflows and maps snake_case fields to camelCase', async () => {
    const mockFetch = vi.fn() as MockedFunction<FetchStub>
    global.fetch = mockFetch as unknown as typeof fetch
    mockFetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      json: async () => ({
        workflows: [
          { name: 'chat', description: 'General assistant.', is_default: true },
          { name: 'triage', description: 'Routes to a specialist.', is_default: false },
        ],
      }),
    })

    const result = await listAvailableWorkflows('token', vi.fn() as unknown as AuthRefresh)

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/agents/workflows'),
      expect.objectContaining({ method: 'GET' })
    )
    expect(result).toEqual([
      { name: 'chat', description: 'General assistant.', isDefault: true },
      { name: 'triage', description: 'Routes to a specialist.', isDefault: false },
    ])
  })
})
