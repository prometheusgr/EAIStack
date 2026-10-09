import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Workflows } from './Workflows'
import { AuthProvider } from '../context/AuthContext'
import { workflowsClient } from '../api/workflowsClient'
import { ApiErrorImpl } from '../api/authorizedFetch'
import type { WorkflowVersionDetail, WorkflowVersionSummary } from '../types/workflows'

vi.mock('../api/workflowsClient', () => ({
  workflowsClient: {
    list: vi.fn(),
    create: vi.fn(),
    listVersions: vi.fn(),
    getVersion: vi.fn(),
    saveDraft: vi.fn(),
    diff: vi.fn(),
    moveActive: vi.fn(),
  },
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

const BUILTIN_YAML = 'name: chat\nversion: 1\nentry: respond\n'
const EDITED_YAML = 'name: chat\nversion: 2\nentry: respond\n'

function version(overrides: Partial<WorkflowVersionDetail>): WorkflowVersionDetail {
  return {
    id: 'v1-id',
    workflow_name: 'chat',
    sequence: 1,
    source: 'builtin',
    author_user_id: 'system',
    change_note: 'Built-in definition shipped with this release.',
    content_hash: 'abc',
    parent_version_id: null,
    created_at: '2026-10-08T12:00:00Z',
    is_active: true,
    yaml_text: BUILTIN_YAML,
    ...overrides,
  }
}

const V1 = version({})
const V2 = version({
  id: 'v2-id',
  sequence: 2,
  source: 'admin',
  author_user_id: 'admin-1',
  change_note: 'terser',
  is_active: false,
  yaml_text: EDITED_YAML,
})

function summary(v: WorkflowVersionDetail): WorkflowVersionSummary {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { yaml_text, ...rest } = v
  return rest
}

function mockStore(versions: WorkflowVersionDetail[]) {
  const active = versions.find((v) => v.is_active) ?? null
  vi.mocked(workflowsClient.list).mockResolvedValue({
    change_management_mode: 'direct',
    workflows: [
      {
        name: 'chat',
        active_version_id: active?.id ?? null,
        active_version_sequence: active?.sequence ?? null,
        active_version_source: active?.source ?? null,
        latest_version_sequence: Math.max(...versions.map((v) => v.sequence)),
        builtin_update_available: false,
      },
    ],
  })
  vi.mocked(workflowsClient.listVersions).mockResolvedValue({
    versions: [...versions].sort((a, b) => b.sequence - a.sequence).map(summary),
  })
  vi.mocked(workflowsClient.getVersion).mockImplementation(async (_name, id) => {
    const found = versions.find((v) => v.id === id)
    if (!found) throw new Error('not found')
    return found
  })
}

async function openChat() {
  render(
    <AuthProvider>
      <Workflows />
    </AuthProvider>
  )
  await userEvent.click(await screen.findByRole('button', { name: /^chat/i }))
  await waitFor(() => expect(screen.getByLabelText('Workflow YAML')).toHaveValue(BUILTIN_YAML))
}

describe('Workflows', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('access_token', ADMIN_TOKEN)
  })

  it('lists each workflow with its active version and shows the change-management mode', async () => {
    mockStore([V1])

    render(
      <AuthProvider>
        <Workflows />
      </AuthProvider>
    )

    const chat = await screen.findByRole('button', { name: /^chat/i })
    expect(chat).toHaveTextContent('v1 · built-in')
    expect(screen.getByText(/change management: direct/i)).toBeInTheDocument()
  })

  it('loads the active version into the editor when a workflow is opened', async () => {
    mockStore([V1])

    await openChat()

    expect(screen.getByLabelText('Workflow YAML')).toHaveValue(BUILTIN_YAML)
    expect(within(screen.getByRole('table')).getByText('Active')).toBeInTheDocument()
  })

  it('saves a draft with the edited YAML and a change note', async () => {
    mockStore([V1])
    vi.mocked(workflowsClient.saveDraft).mockResolvedValue(V2)

    await openChat()
    const editor = screen.getByLabelText('Workflow YAML')
    await userEvent.clear(editor)
    await userEvent.type(editor, 'name: chat{enter}')
    await userEvent.type(screen.getByLabelText('Change note'), 'terser')
    mockStore([V1, V2])
    await userEvent.click(screen.getByRole('button', { name: 'Save draft' }))

    await waitFor(() => expect(workflowsClient.saveDraft).toHaveBeenCalled())
    const [name, payload] = vi.mocked(workflowsClient.saveDraft).mock.calls[0]
    expect(name).toBe('chat')
    expect(payload).toEqual({ yaml_text: 'name: chat\n', change_note: 'terser' })
    expect(await screen.findByText(/saved as draft v2/i)).toBeInTheDocument()
  })

  it('shows the server validation error next to the editor', async () => {
    mockStore([V1])
    vi.mocked(workflowsClient.saveDraft).mockRejectedValue(
      new ApiErrorImpl(422, 'workflow_draft_rejected', "entry: entry step 'nowhere' does not exist")
    )

    await openChat()
    await userEvent.type(screen.getByLabelText('Change note'), 'broken')
    await userEvent.click(screen.getByRole('button', { name: 'Save draft' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("entry: entry step 'nowhere'")
  })

  it('publishes a draft only after confirming the diff against the active version', async () => {
    mockStore([V1, V2])
    vi.mocked(workflowsClient.diff).mockResolvedValue({
      diff: '-version: 1\n+version: 2\n',
    })
    vi.mocked(workflowsClient.moveActive).mockResolvedValue({ ...V2, is_active: true })

    await openChat()
    await userEvent.click(screen.getByRole('button', { name: 'Publish v2' }))

    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(/\+version: 2/)).toBeInTheDocument()
    expect(workflowsClient.moveActive).not.toHaveBeenCalled()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish' }))

    await waitFor(() =>
      expect(workflowsClient.moveActive).toHaveBeenCalledWith(
        'publish',
        'chat',
        'v2-id',
        expect.anything(),
        expect.anything()
      )
    )
  })

  it('rolls back to an older version as a rollback, not a publish', async () => {
    mockStore([{ ...V1, is_active: false }, { ...V2, is_active: true }])
    vi.mocked(workflowsClient.diff).mockResolvedValue({ diff: '-version: 2\n+version: 1\n' })
    vi.mocked(workflowsClient.moveActive).mockResolvedValue(V1)

    render(
      <AuthProvider>
        <Workflows />
      </AuthProvider>
    )
    await userEvent.click(await screen.findByRole('button', { name: /^chat/i }))
    await userEvent.click(await screen.findByRole('button', { name: 'Roll back to v1' }))
    await userEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Roll back' })
    )

    await waitFor(() =>
      expect(workflowsClient.moveActive).toHaveBeenCalledWith(
        'rollback',
        'chat',
        'v1-id',
        expect.anything(),
        expect.anything()
      )
    )
  })

  it('creates a new workflow from the editor', async () => {
    mockStore([V1])
    vi.mocked(workflowsClient.create).mockResolvedValue(
      version({ id: 'new-id', workflow_name: 'summarizer', source: 'admin', is_active: false })
    )

    render(
      <AuthProvider>
        <Workflows />
      </AuthProvider>
    )
    await userEvent.click(await screen.findByRole('button', { name: 'New workflow' }))
    await userEvent.type(screen.getByLabelText('Change note'), 'first cut')
    await userEvent.click(screen.getByRole('button', { name: 'Create workflow' }))

    await waitFor(() => expect(workflowsClient.create).toHaveBeenCalled())
    const [payload] = vi.mocked(workflowsClient.create).mock.calls[0]
    expect(payload.yaml_text).toContain('name: my_workflow')
    expect(payload.change_note).toBe('first cut')
  })
})
