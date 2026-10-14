import { useEffect, useRef, useState } from 'react'
import { useWorkflowsService } from '@/hooks/useWorkflowsService'
import { useIsMounted } from '@/hooks/useIsMounted'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { EvalCaseReport, EvalRun, EvalRunOutcome } from '@/types/workflows'

interface WorkflowEvalRunProps {
  workflowName: string
  version: { id: string; sequence: number }
  onClose: () => void
}

const OUTCOME_LABELS: Record<EvalRunOutcome, string> = {
  completed: 'completed',
  timed_out: 'timed out',
  rejected_by_input_guardrail: 'rejected by the input guardrail',
  error: 'error',
}

const STATUS_HEADLINES: Record<Exclude<EvalRun['status'], 'running' | 'completed'>, string> = {
  cancelled: 'Eval run cancelled',
  abandoned: 'Eval run abandoned',
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function verdictLabel(passed: boolean | null): string {
  if (passed === null) return '—'
  return passed ? 'Passed' : 'Failed'
}

function headline(run: EvalRun): string | null {
  if (run.status === 'running') return null
  if (run.status === 'completed') return run.passed ? 'Eval run passed' : 'Eval run failed'
  return STATUS_HEADLINES[run.status]
}

/** An eval run of one workflow version's test suite (issue #84): runs each
 * test case the number of times its YAML asks for, against the real model
 * and tools, and shows each case's pass rate.
 *
 * This page drives the run, one case run per request, so every request
 * forwards a freshly refreshed sign-in to the tools. Closing the panel
 * cancels a run still executing; results recorded so far are kept. */
export function WorkflowEvalRun({ workflowName, version, onClose }: WorkflowEvalRunProps) {
  const isMounted = useIsMounted()
  const { startEvalRun, advanceEvalRun, cancelEvalRun } = useWorkflowsService()
  const [run, setRun] = useState<EvalRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const stopRequested = useRef(false)
  const executingRunId = useRef<string | null>(null)
  const cancelRef = useRef(cancelEvalRun.mutateAsync)
  cancelRef.current = cancelEvalRun.mutateAsync

  useEffect(
    () => () => {
      stopRequested.current = true
      const runId = executingRunId.current
      if (runId) void cancelRef.current({ name: workflowName, runId }).catch(() => {})
    },
    [workflowName]
  )

  const handleStart = async () => {
    stopRequested.current = false
    setError(null)
    let current: EvalRun
    try {
      current = await startEvalRun.mutateAsync({ name: workflowName, versionId: version.id })
    } catch (startError) {
      if (isMounted()) setError(errorMessage(startError, 'The eval run could not start.'))
      return
    }
    executingRunId.current = current.id
    if (isMounted()) setRun(current)

    try {
      while (current.status === 'running' && !stopRequested.current) {
        current = await advanceEvalRun.mutateAsync({ name: workflowName, runId: current.id })
        if (isMounted() && !stopRequested.current) setRun(current)
      }
      if (current.status !== 'running') executingRunId.current = null
    } catch (advanceError) {
      if (isMounted()) setError(errorMessage(advanceError, 'The eval run stopped with an error.'))
    }
  }

  const handleStop = async () => {
    stopRequested.current = true
    const runId = executingRunId.current
    if (!runId) return
    try {
      const cancelled = await cancelEvalRun.mutateAsync({ name: workflowName, runId })
      executingRunId.current = null
      if (isMounted()) setRun(cancelled)
    } catch (cancelError) {
      if (isMounted()) setError(errorMessage(cancelError, 'The eval run could not be stopped.'))
    }
  }

  const isRunning = run?.status === 'running'
  const runHeadline = run ? headline(run) : null

  return (
    <section
      aria-label="Eval run"
      className="space-y-3 rounded-lg border-2 border-dashed border-sky-400 p-4"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium">
            Eval run: {workflowName} v{version.sequence}
          </h3>
          <p className="text-sm text-gray-500">
            Runs every test case in this version&apos;s <code>tests:</code> against the real model
            and tools, as many times as each case asks. Nothing is published. Only one eval run
            executes at a time, since it shares the model with production chat.
          </p>
        </div>
        <div className="flex gap-2">
          {isRunning ? (
            <Button variant="outline" size="sm" onClick={handleStop}>
              Stop eval run
            </Button>
          ) : (
            <Button size="sm" onClick={handleStart} disabled={startEvalRun.isPending}>
              {run ? 'Run again' : 'Start eval run'}
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {run && (
        <div className="space-y-3">
          <p className="text-sm" role="status">
            {runHeadline ? (
              <span
                className={`font-semibold ${
                  run.status === 'completed' && run.passed ? 'text-green-700' : 'text-red-700'
                }`}
              >
                {runHeadline}
              </span>
            ) : (
              <span>
                {run.case_runs_done} of {run.case_runs_total} case runs done
              </span>
            )}
          </p>

          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Test case</TableHead>
                  <TableHead>Pass rate</TableHead>
                  <TableHead>Required</TableHead>
                  <TableHead>Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {run.cases.map((evalCase) => (
                  <TableRow key={evalCase.name}>
                    <TableCell className="font-medium">{evalCase.name}</TableCell>
                    <TableCell>
                      {evalCase.passes} of {evalCase.runs} runs passed
                    </TableCell>
                    <TableCell>needs {evalCase.required_passes}</TableCell>
                    <TableCell>{verdictLabel(evalCase.passed)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {run.cases.map((evalCase) => (
            <CaseRunDetails key={evalCase.name} evalCase={evalCase} />
          ))}
        </div>
      )}
    </section>
  )
}

function CaseRunDetails({ evalCase }: { evalCase: EvalCaseReport }) {
  if (evalCase.results.length === 0) return null
  return (
    <details className="text-sm">
      <summary className="cursor-pointer">{evalCase.name}: run details</summary>
      <ul className="mt-2 space-y-2 pl-4">
        {evalCase.results.map((result) => (
          <li key={result.run_index}>
            <span className="font-medium">
              Run {result.run_index + 1}: {result.passed ? 'passed' : 'failed'}
            </span>{' '}
            <span className="text-gray-500">
              ({OUTCOME_LABELS[result.outcome]}, {(result.duration_ms / 1000).toFixed(1)} s)
            </span>
            <ul className="pl-4">
              {result.checks.map((check, index) => (
                <li key={index}>
                  <span aria-label={check.passed ? 'passed' : 'failed'}>
                    {check.passed ? '✓' : '✗'}
                  </span>{' '}
                  <span>{check.detail}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </details>
  )
}
