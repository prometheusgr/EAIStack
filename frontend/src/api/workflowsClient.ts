import { authorizedFetch, type AuthRefresh } from './authorizedFetch'
import type {
  SaveWorkflowDraftRequest,
  WorkflowDiffResponse,
  WorkflowListResponse,
  WorkflowVersionDetail,
  WorkflowVersionListResponse,
} from '@/types/workflows'

/** HTTP-only client for the admin /api/workflows endpoints (issue #83). */
const workflowsClient = {
  async list(token: string, onRefresh: AuthRefresh): Promise<WorkflowListResponse> {
    const response = await authorizedFetch('/api/workflows', token, onRefresh, { method: 'GET' })
    return response.json()
  },

  async create(
    payload: SaveWorkflowDraftRequest,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<WorkflowVersionDetail> {
    const response = await authorizedFetch('/api/workflows', token, onRefresh, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return response.json()
  },

  async listVersions(
    name: string,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<WorkflowVersionListResponse> {
    const response = await authorizedFetch(
      `/api/workflows/${encodeURIComponent(name)}/versions`,
      token,
      onRefresh,
      { method: 'GET' }
    )
    return response.json()
  },

  async getVersion(
    name: string,
    versionId: string,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<WorkflowVersionDetail> {
    const response = await authorizedFetch(
      `/api/workflows/${encodeURIComponent(name)}/versions/${encodeURIComponent(versionId)}`,
      token,
      onRefresh,
      { method: 'GET' }
    )
    return response.json()
  },

  async saveDraft(
    name: string,
    payload: SaveWorkflowDraftRequest,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<WorkflowVersionDetail> {
    const response = await authorizedFetch(
      `/api/workflows/${encodeURIComponent(name)}/versions`,
      token,
      onRefresh,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }
    )
    return response.json()
  },

  async diff(
    name: string,
    fromVersion: string,
    toVersion: string,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<WorkflowDiffResponse> {
    const query = new URLSearchParams({ from_version: fromVersion, to_version: toVersion })
    const response = await authorizedFetch(
      `/api/workflows/${encodeURIComponent(name)}/diff?${query}`,
      token,
      onRefresh,
      { method: 'GET' }
    )
    return response.json()
  },

  async moveActive(
    action: 'publish' | 'rollback',
    name: string,
    versionId: string,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<WorkflowVersionDetail> {
    const response = await authorizedFetch(
      `/api/workflows/${encodeURIComponent(name)}/${action}`,
      token,
      onRefresh,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version_id: versionId }),
      }
    )
    return response.json()
  },
}

export { workflowsClient }
