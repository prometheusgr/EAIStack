/** Shapes of the admin-only /api/workflows endpoints (issue #83). */

import type { ChatResponse } from './chat'

export interface WorkflowSummary {
  name: string
  active_version_id: string | null
  active_version_sequence: number | null
  active_version_source: 'builtin' | 'admin' | null
  latest_version_sequence: number
  builtin_update_available: boolean
}

export interface WorkflowListResponse {
  /** Read-only deployment config (issue #87); always "direct" today. */
  change_management_mode: string
  workflows: WorkflowSummary[]
}

export interface WorkflowVersionSummary {
  id: string
  workflow_name: string
  sequence: number
  source: 'builtin' | 'admin'
  author_user_id: string
  change_note: string
  content_hash: string
  parent_version_id: string | null
  created_at: string
  is_active: boolean
}

export interface WorkflowVersionDetail extends WorkflowVersionSummary {
  yaml_text: string
}

export interface WorkflowVersionListResponse {
  versions: WorkflowVersionSummary[]
}

export interface SaveWorkflowDraftRequest {
  yaml_text: string
  change_note: string
}

export interface WorkflowDiffResponse {
  diff: string
}

/** A chat reply from an admin's draft test run (issue #84), naming the
 * exact version that answered. */
export interface TestChatReply extends ChatResponse {
  testVersionId: string
  testVersionSequence: number
}

/** One check's verdict on one case run (issue #84). `detail` quotes only
 * the test case's own expectation, never the model's reply. */
export interface EvalCheckResult {
  check: string
  kind: 'structural' | 'content'
  passed: boolean
  detail: string
}

export type EvalRunOutcome = 'completed' | 'timed_out' | 'rejected_by_input_guardrail' | 'error'

export interface EvalCaseRunResult {
  run_index: number
  outcome: EvalRunOutcome
  passed: boolean
  checks: EvalCheckResult[]
  thread_id: string | null
  duration_ms: number
}

/** One test case within an eval run: `passes` of `runs_done` so far, out of
 * `runs`; `passed` stays null until all its runs are recorded. */
export interface EvalCaseReport {
  name: string
  runs: number
  required_passes: number
  runs_done: number
  passes: number
  passed: boolean | null
  results: EvalCaseRunResult[]
}

export type EvalRunStatus = 'running' | 'completed' | 'cancelled' | 'abandoned'

export interface EvalRun {
  id: string
  workflow_name: string
  workflow_version_id: string
  version_sequence: number
  status: EvalRunStatus
  /** Every case met its required passes; null until the run completes. */
  passed: boolean | null
  case_runs_total: number
  case_runs_done: number
  started_by_user_id: string
  started_at: string
  finished_at: string | null
  cases: EvalCaseReport[]
}
