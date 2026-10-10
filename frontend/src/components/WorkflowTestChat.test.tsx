import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WorkflowTestChat } from './WorkflowTestChat'
import { AuthProvider } from '../context/AuthContext'
import { workflowsClient } from '../api/workflowsClient'
import { ApiErrorImpl } from '../api/authorizedFetch'
import type { TestChatReply } from '../types/workflows'

vi.mock('../api/workflowsClient', () => ({
  workflowsClient: { testChat: vi.fn() },
}))

function buildToken(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.invalid_sig`
}

const ADMIN_TOKEN = buildToken({
  sub: 'admin-1',
  preferred_username: 'admin',
  exp: 9999999999,
  realm_access: { roles: ['admin'] },
})

function reply(overrides: Partial<TestChatReply> = {}): TestChatReply {
  return {
    response: 'Welcome aboard!',
    threadId: 'test-thread-1',
    sources: [],
    wasModified: false,
    workflow: 'chat',
    testVersionId: 'v2-id',
    testVersionSequence: 2,
    ...overrides,
  }
}

function renderTestChat(onClose = vi.fn()) {
  const view = render(
    <AuthProvider>
      <WorkflowTestChat workflowName="chat" version={{ id: 'v2-id', sequence: 2 }} onClose={onClose} />
    </AuthProvider>
  )
  return { ...view, onClose }
}

async function send(text: string) {
  await userEvent.type(screen.getByLabelText('Test message'), text)
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
}

describe('WorkflowTestChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('access_token', ADMIN_TOKEN)
  })

  it('is headed as a draft test run of the exact version', () => {
    renderTestChat()

    expect(
      screen.getByRole('heading', { name: 'Draft test run: chat v2' })
    ).toBeInTheDocument()
    expect(screen.getByText(/nothing is published/i)).toBeInTheDocument()
  })

  it('labels every reply as a draft run of the version that answered', async () => {
    vi.mocked(workflowsClient.testChat).mockResolvedValue(reply())
    renderTestChat()

    await send('hello')

    expect(await screen.findByText('Welcome aboard!')).toBeInTheDocument()
    expect(screen.getByText('Draft run · v2')).toBeInTheDocument()
    expect(workflowsClient.testChat).toHaveBeenCalledWith(
      'chat',
      'v2-id',
      'hello',
      undefined,
      expect.anything(),
      expect.anything()
    )
  })

  it('continues the same test conversation on a follow-up', async () => {
    vi.mocked(workflowsClient.testChat).mockResolvedValue(reply())
    renderTestChat()

    await send('hello')
    await screen.findByText('Welcome aboard!')
    await send('and then?')

    await waitFor(() => expect(workflowsClient.testChat).toHaveBeenCalledTimes(2))
    expect(vi.mocked(workflowsClient.testChat).mock.calls[1][3]).toBe('test-thread-1')
  })

  it('says when the output guardrail filtered a reply', async () => {
    vi.mocked(workflowsClient.testChat).mockResolvedValue(reply({ wasModified: true }))
    renderTestChat()

    await send('hello')

    expect(
      await screen.findByText(/filtered by a content safety rule/i)
    ).toBeInTheDocument()
  })

  it('shows a refused message the same way production chat does', async () => {
    vi.mocked(workflowsClient.testChat).mockRejectedValue(
      new ApiErrorImpl(429, 'rate_limit_exceeded', 'Too many requests. Please wait before sending another message.')
    )
    renderTestChat()

    await send('hello')

    expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests')
  })

  it('ends the test run from its own control', async () => {
    const { onClose } = renderTestChat()

    await userEvent.click(screen.getByRole('button', { name: 'End test run' }))

    expect(onClose).toHaveBeenCalled()
  })

  it('does not update state when unmounted mid-request', async () => {
    let resolveReply: (value: TestChatReply) => void = () => {}
    vi.mocked(workflowsClient.testChat).mockReturnValue(
      new Promise((resolve) => {
        resolveReply = resolve
      })
    )
    const { unmount } = renderTestChat()
    await send('hello')

    unmount()
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    resolveReply(reply())
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(consoleError).not.toHaveBeenCalled()
    consoleError.mockRestore()
  })
})
