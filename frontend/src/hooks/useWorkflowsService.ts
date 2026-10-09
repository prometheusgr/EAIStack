import { useAuth } from '@/context/AuthContext'
import { WorkflowsService } from '@/services/workflowsService'
import type {
  SaveWorkflowDraftRequest,
  WorkflowDiffResponse,
  WorkflowListResponse,
  WorkflowVersionDetail,
  WorkflowVersionListResponse,
} from '@/types/workflows'
import { useApiCall } from './useApiCall'
import { useApiMutation } from './useApiMutation'

export interface SaveDraftArgs extends SaveWorkflowDraftRequest {
  name: string
}

export interface MakeActiveArgs {
  name: string
  target: { id: string; sequence: number }
  activeSequence: number | null
}

/** Hooks for the admin Workflows screen (issue #83). Reads that take an
 * argument (a workflow name, a version ID) are mutations, the same way
 * useEmbeddingsService exposes search. */
export function useWorkflowsService() {
  const { token, refreshAccessToken } = useAuth()

  const service = () => {
    if (!token) throw new Error('No auth token available')
    return new WorkflowsService(token, refreshAccessToken)
  }

  const list = useApiCall<WorkflowListResponse>(async () => service().list(), {
    immediate: false,
  })

  const listVersions = useApiMutation<string, WorkflowVersionListResponse>(async (name) =>
    service().listVersions(name)
  )

  const getVersion = useApiMutation<{ name: string; versionId: string }, WorkflowVersionDetail>(
    async ({ name, versionId }) => service().getVersion(name, versionId)
  )

  const saveDraft = useApiMutation<SaveDraftArgs, WorkflowVersionDetail>(
    async ({ name, yaml_text, change_note }) => service().saveDraft(name, { yaml_text, change_note })
  )

  const create = useApiMutation<SaveWorkflowDraftRequest, WorkflowVersionDetail>(async (payload) =>
    service().create(payload)
  )

  const diff = useApiMutation<
    { name: string; fromVersion: string; toVersion: string },
    WorkflowDiffResponse
  >(async ({ name, fromVersion, toVersion }) => service().diff(name, fromVersion, toVersion))

  const makeActive = useApiMutation<MakeActiveArgs, WorkflowVersionDetail>(
    async ({ name, target, activeSequence }) => service().makeActive(name, target, activeSequence)
  )

  return { list, listVersions, getVersion, saveDraft, create, diff, makeActive }
}
