import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WorkflowEvalRun } from './WorkflowEvalRun'
import { AuthProvider } from '../context/AuthContext'
import { workflowsClient } from '../api/workflowsClient'
import { ApiErrorImpl } from '../api/authorizedFetch'
import type { EvalCaseReport, EvalRun } from '../types/workflows'

vi.mock('../api/workflowsClient', () => ({
  workflowsClient: {
    startEvalRun: vi.fn(),
    advanceEvalRun: vi.fn(),
    cancelEvalRun: vi.fn(),
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

function caseReport(overrides: Partial<EvalCaseReport> = {}): EvalCaseReport {
  return {
    name: 'mentions_days',
    runs: 2,
    required_passes: 1,
    runs_done: 0,
    passes: 0,
    passed: null,
    results: [],
    ...overrides,
  }
}

function evalRun(overrides: Partial<EvalRun> = {}): EvalRun {
  return {
    id: 'run-1',
    workflow_name: 'chat',
    workflow_version_id: 'v2-id',
    version_sequence: 2,
    status: 'running',
    passed: null,
    case_runs_total: 2,
    case_runs_done: 0,
    started_by_user_id: 'admin-1',
    started_at: '2026-10-13T12:00:00Z',
    finished_at: null,
    cases: [caseReport()],
    ...overrides,
  }
}

const PASSED_RUN = {
  run_index: 0,
  outcome: 'completed' as const,
  passed: true,
  checks: [
    { check: 'reply_contains', kind: 'content' as const, passed: true, detail: "reply contains 'days'" },
  ],
  thread_id: 't-1',
  duration_ms: 1200,
}
const FAILED_RUN = {
  run_index: 1,
  outcome: 'completed' as const,
  passed: false,
  checks: [
    {
      check: 'reply_contains',
      kind: 'content' as const,
      passed: false,
      detail: "reply does not contain 'days'",
    },
  ],
  thread_id: 't-2',
  duration_ms: 900,
}

function renderPanel(onClose = vi.fn()) {
  const view = render(
    <AuthProvider>
      <WorkflowEvalRun workflowName="chat" version={{ id: 'v2-id', sequence: 2 }} onClose={onClose} />
    </AuthProvider>
  )
  return { ...view, onClose }
}

describe('WorkflowEvalRun', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('access_token', ADMIN_TOKEN)
  })

  it('names the version and waits for the admin to start the run', () => {
    renderPanel()

    expect(screen.getByRole('heading', { name: 'Eval run: chat v2' })).toBeInTheDocument()
    expect(workflowsClient.startEvalRun).not.toHaveBeenCalled()
  })

  it('runs every case run in turn and shows each case pass rate and the verdict', async () => {
    vi.mocked(workflowsClient.startEvalRun).mockResolvedValue(evalRun())
    vi.mocked(workflowsClient.advanceEvalRun)
      .mockResolvedValueOnce(
        evalRun({
          case_runs_done: 1,
          cases: [caseReport({ runs_done: 1, passes: 1, results: [PASSED_RUN] })],
        })
      )
      .mockResolvedValueOnce(
        evalRun({
          status: 'completed',
          passed: true,
          case_runs_done: 2,
          cases: [
            caseReport({ runs_done: 2, passes: 1, passed: true, results: [PASSED_RUN, FAILED_RUN] }),
          ],
        })
      )
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Start eval run' }))

    expect(await screen.findByText('Eval run passed')).toBeInTheDocument()
    expect(workflowsClient.startEvalRun).toHaveBeenCalledWith(
      'chat',
      'v2-id',
      ADMIN_TOKEN,
      expect.any(Function)
    )
    expect(workflowsClient.advanceEvalRun).toHaveBeenCalledTimes(2)
    const row = screen.getByRole('row', { name: /mentions_days/ })
    expect(within(row).getByText('1 of 2 runs passed')).toBeInTheDocument()
    expect(within(row).getByText('needs 1')).toBeInTheDocument()
    expect(within(row).getByText('Passed')).toBeInTheDocument()
    expect(screen.getByText("reply does not contain 'days'")).toBeInTheDocument()
  })

  it('shows progress while the run executes', async () => {
    vi.mocked(workflowsClient.startEvalRun).mockResolvedValue(evalRun())
    vi.mocked(workflowsClient.advanceEvalRun).mockReturnValue(new Promise(() => {}))
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Start eval run' }))

    expect(await screen.findByText('0 of 2 case runs done')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stop eval run' })).toBeInTheDocument()
  })

  it('reports a failed run', async () => {
    vi.mocked(workflowsClient.startEvalRun).mockResolvedValue(evalRun())
    vi.mocked(workflowsClient.advanceEvalRun).mockResolvedValue(
      evalRun({
        status: 'completed',
        passed: false,
        case_runs_done: 2,
        cases: [caseReport({ runs_done: 2, passes: 0, passed: false, results: [FAILED_RUN] })],
      })
    )
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Start eval run' }))

    expect(await screen.findByText('Eval run failed')).toBeInTheDocument()
    expect(within(screen.getByRole('row', { name: /mentions_days/ })).getByText('Failed')).toBeInTheDocument()
  })

  it('stops the run when the admin asks', async () => {
    vi.mocked(workflowsClient.startEvalRun).mockResolvedValue(evalRun())
    let finishAdvance: (run: EvalRun) => void = () => {}
    vi.mocked(workflowsClient.advanceEvalRun).mockReturnValue(
      new Promise((resolve) => {
        finishAdvance = resolve
      })
    )
    vi.mocked(workflowsClient.cancelEvalRun).mockResolvedValue(evalRun({ status: 'cancelled' }))
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Start eval run' }))

    await userEvent.click(await screen.findByRole('button', { name: 'Stop eval run' }))
    finishAdvance(evalRun({ case_runs_done: 1 }))

    expect(await screen.findByText('Eval run cancelled')).toBeInTheDocument()
    expect(workflowsClient.cancelEvalRun).toHaveBeenCalledWith(
      'chat',
      'run-1',
      ADMIN_TOKEN,
      expect.any(Function)
    )
    expect(workflowsClient.advanceEvalRun).toHaveBeenCalledTimes(1)
  })

  it('shows why a run could not start', async () => {
    vi.mocked(workflowsClient.startEvalRun).mockRejectedValue(
      new ApiErrorImpl(400, 'no_test_cases', 'This version declares no test cases under `tests:`.')
    )
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Start eval run' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('declares no test cases')
  })

  it('cancels a run that is still executing when the panel closes', async () => {
    vi.mocked(workflowsClient.startEvalRun).mockResolvedValue(evalRun())
    vi.mocked(workflowsClient.advanceEvalRun).mockReturnValue(new Promise(() => {}))
    vi.mocked(workflowsClient.cancelEvalRun).mockResolvedValue(evalRun({ status: 'cancelled' }))
    const { unmount } = renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Start eval run' }))
    await screen.findByText('0 of 2 case runs done')

    unmount()

    await waitFor(() => expect(workflowsClient.cancelEvalRun).toHaveBeenCalled())
  })
})
