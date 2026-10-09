/** Shapes of the admin-only /api/workflows endpoints (issue #83). */

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
