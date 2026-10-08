import { workflowsClient } from '@/api/workflowsClient'
import type { AuthRefresh } from '@/api/authorizedFetch'
import type {
  SaveWorkflowDraftRequest,
  WorkflowDiffResponse,
  WorkflowListResponse,
  WorkflowVersionDetail,
  WorkflowVersionListResponse,
} from '@/types/workflows'

/** Workflows screen business logic over workflowsClient (issue #83). */
export class WorkflowsService {
  constructor(
    private token: string,
    private onRefresh: AuthRefresh
  ) {}

  private requireToken(): string {
    if (!this.token) throw new Error('No auth token available')
    return this.token
  }

  async list(): Promise<WorkflowListResponse> {
    return workflowsClient.list(this.requireToken(), this.onRefresh)
  }

  async create(payload: SaveWorkflowDraftRequest): Promise<WorkflowVersionDetail> {
    return workflowsClient.create(payload, this.requireToken(), this.onRefresh)
  }

  async listVersions(name: string): Promise<WorkflowVersionListResponse> {
    return workflowsClient.listVersions(name, this.requireToken(), this.onRefresh)
  }

  async getVersion(name: string, versionId: string): Promise<WorkflowVersionDetail> {
    return workflowsClient.getVersion(name, versionId, this.requireToken(), this.onRefresh)
  }

  async saveDraft(name: string, payload: SaveWorkflowDraftRequest): Promise<WorkflowVersionDetail> {
    return workflowsClient.saveDraft(name, payload, this.requireToken(), this.onRefresh)
  }

  async diff(name: string, fromVersion: string, toVersion: string): Promise<WorkflowDiffResponse> {
    return workflowsClient.diff(name, fromVersion, toVersion, this.requireToken(), this.onRefresh)
  }

  /** Publish when moving forward, roll back when moving to an older
   * version - the backend records the two as different audit actions. */
  async makeActive(
    name: string,
    target: { id: string; sequence: number },
    activeSequence: number | null
  ): Promise<WorkflowVersionDetail> {
    const action =
      activeSequence !== null && target.sequence < activeSequence ? 'rollback' : 'publish'
    return workflowsClient.moveActive(action, name, target.id, this.requireToken(), this.onRefresh)
  }
}
