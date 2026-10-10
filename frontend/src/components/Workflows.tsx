import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useWorkflowsService } from '@/hooks/useWorkflowsService'
import { useIsMounted } from '@/hooks/useIsMounted'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { WorkflowTestChat } from '@/components/WorkflowTestChat'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { WorkflowSummary, WorkflowVersionSummary } from '@/types/workflows'

const NEW_WORKFLOW_TEMPLATE = `name: my_workflow
version: 1
entry: respond
steps:
  respond:
    type: agent
    prompt: >-
      You are a helpful assistant. Be brief and direct.
    tools:
      - search_knowledge_base
`

interface PendingMove {
  target: WorkflowVersionSummary
  kind: 'publish' | 'rollback'
  diff: string
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

/** Admin-only screen for the versioned workflow store (issue #83): list
 * workflows, edit one as YAML, save drafts, publish or roll back with a
 * diff confirmation, and create new workflows. Every action is
 * audit-logged by the backend. Assumes it is only mounted for an admin
 * (App.tsx owns that gate). */
export function Workflows() {
  const { isLoading: isAuthLoading } = useAuth()
  const isMounted = useIsMounted()
  const { list, listVersions, getVersion, saveDraft, create, diff, makeActive } =
    useWorkflowsService()

  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [yamlText, setYamlText] = useState('')
  const [changeNote, setChangeNote] = useState('')
  const [editorError, setEditorError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pendingMove, setPendingMove] = useState<PendingMove | null>(null)
  const [testTarget, setTestTarget] = useState<WorkflowVersionSummary | null>(null)

  useEffect(() => {
    if (isAuthLoading) return
    list.execute()
  }, [isAuthLoading])

  const workflows = list.data?.workflows ?? []
  const selected = workflows.find((w) => w.name === selectedName) ?? null
  const versions = listVersions.data?.versions ?? []
  const activeVersion = versions.find((v) => v.is_active) ?? null

  const openWorkflow = async (workflow: WorkflowSummary) => {
    setSelectedName(workflow.name)
    setIsCreating(false)
    setTestTarget(null)
    setEditorError(null)
    setNotice(null)
    setChangeNote('')
    const history = await listVersions.mutateAsync(workflow.name).catch(() => null)
    const toLoad = history?.versions.find((v) => v.is_active) ?? history?.versions[0]
    if (toLoad) await loadIntoEditor(workflow.name, toLoad.id)
  }

  const loadIntoEditor = async (name: string, versionId: string) => {
    const detail = await getVersion.mutateAsync({ name, versionId }).catch(() => null)
    if (detail && isMounted()) setYamlText(detail.yaml_text)
  }

  const startNewWorkflow = () => {
    setSelectedName(null)
    setIsCreating(true)
    setYamlText(NEW_WORKFLOW_TEMPLATE)
    setChangeNote('')
    setEditorError(null)
    setNotice(null)
  }

  const handleSave = async () => {
    setEditorError(null)
    setNotice(null)
    try {
      if (isCreating) {
        const created = await create.mutateAsync({ yaml_text: yamlText, change_note: changeNote })
        await Promise.all([list.execute(), listVersions.mutateAsync(created.workflow_name)])
        if (isMounted()) setIsCreating(false)
        if (isMounted()) setSelectedName(created.workflow_name)
        if (isMounted()) {
          setNotice(`Created ${created.workflow_name} as unpublished draft v${created.sequence}.`)
        }
      } else if (selectedName) {
        const saved = await saveDraft.mutateAsync({
          name: selectedName,
          yaml_text: yamlText,
          change_note: changeNote,
        })
        await Promise.all([listVersions.mutateAsync(selectedName), list.execute()])
        if (isMounted()) {
          setNotice(`Saved as draft v${saved.sequence}. Publish it from the history below.`)
        }
      }
      if (isMounted()) setChangeNote('')
    } catch (error) {
      if (isMounted()) setEditorError(errorMessage(error, 'Saving failed.'))
    }
  }

  const requestMove = async (target: WorkflowVersionSummary) => {
    if (!selectedName) return
    const kind =
      activeVersion && target.sequence < activeVersion.sequence ? 'rollback' : 'publish'
    const result = activeVersion
      ? await diff
          .mutateAsync({ name: selectedName, fromVersion: activeVersion.id, toVersion: target.id })
          .catch(() => null)
      : null
    if (isMounted()) setPendingMove({ target, kind, diff: result?.diff ?? '' })
  }

  const confirmMove = async () => {
    if (!selectedName || !pendingMove) return
    const { target, kind } = pendingMove
    setPendingMove(null)
    try {
      await makeActive.mutateAsync({
        name: selectedName,
        target: { id: target.id, sequence: target.sequence },
        activeSequence: activeVersion?.sequence ?? null,
      })
      await Promise.all([listVersions.mutateAsync(selectedName), list.execute()])
      if (isMounted()) {
        setNotice(
          kind === 'rollback'
            ? `Rolled back ${selectedName} to v${target.sequence}.`
            : `Published v${target.sequence} of ${selectedName}.`
        )
      }
    } catch (error) {
      if (isMounted()) setEditorError(errorMessage(error, 'Publishing failed.'))
    }
  }

  if (list.isLoading && !list.data) {
    return (
      <div className="space-y-4">
        <div className="text-gray-500">Loading workflows...</div>
        <Skeleton className="h-12 w-full" />
      </div>
    )
  }

  if (list.error && !list.data) {
    return (
      <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200" role="alert">
        <p>{errorMessage(list.error, 'Failed to load workflows')}</p>
        <Button variant="outline" size="sm" onClick={() => list.execute()} className="mt-2">
          Retry
        </Button>
      </div>
    )
  }

  const editorOpen = isCreating || selected !== null

  return (
    <section className="space-y-6" aria-label="Workflows">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Workflows</h2>
          <p className="text-sm text-gray-500">
            Change management: {list.data?.change_management_mode ?? 'direct'} (publish from this
            screen). Every save, publish and rollback is recorded in the audit log.
          </p>
        </div>
        <Button variant="outline" onClick={startNewWorkflow}>
          New workflow
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        {workflows.map((workflow) => (
          <Button
            key={workflow.name}
            variant={workflow.name === selectedName ? 'default' : 'outline'}
            onClick={() => openWorkflow(workflow)}
            className="flex flex-col items-start h-auto py-2"
          >
            <span className="font-medium">{workflow.name}</span>
            <span className="text-xs opacity-80">
              {workflow.active_version_sequence === null
                ? 'unpublished'
                : `v${workflow.active_version_sequence} · ${
                    workflow.active_version_source === 'builtin' ? 'built-in' : 'admin'
                  }`}
              {workflow.builtin_update_available && ' · built-in update available'}
            </span>
          </Button>
        ))}
      </div>

      {notice && (
        <p className="text-sm text-green-700" role="status">
          {notice}
        </p>
      )}

      {editorOpen && (
        <div className="space-y-3">
          <h3 className="font-medium">
            {isCreating ? 'New workflow' : `Edit ${selectedName}`}
          </h3>
          {isCreating && (
            <p className="text-sm text-gray-500">
              The workflow&apos;s name comes from the YAML. New workflows are saved unpublished;
              only <code>chat</code> is used by the chat screen until workflow selection lands.
            </p>
          )}
          <label htmlFor="workflow-yaml" className="block text-sm font-medium">
            Workflow YAML
          </label>
          <textarea
            id="workflow-yaml"
            className="w-full h-80 font-mono text-sm border rounded p-2"
            spellCheck={false}
            value={yamlText}
            onChange={(e) => setYamlText(e.target.value)}
          />
          <label htmlFor="workflow-change-note" className="block text-sm font-medium">
            Change note
          </label>
          <Input
            id="workflow-change-note"
            value={changeNote}
            onChange={(e) => setChangeNote(e.target.value)}
            placeholder="What changed and why (required)"
          />
          {editorError && (
            <div
              className="p-3 bg-red-50 text-red-700 rounded border border-red-200 text-sm"
              role="alert"
            >
              {editorError}
            </div>
          )}
          <Button onClick={handleSave} disabled={saveDraft.isPending || create.isPending}>
            {isCreating ? 'Create workflow' : 'Save draft'}
          </Button>
        </div>
      )}

      {selected && versions.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-medium">History</h3>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Version</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Author</TableHead>
                  <TableHead>Change note</TableHead>
                  <TableHead>Saved</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {versions.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell className="font-medium">v{v.sequence}</TableCell>
                    <TableCell>{v.source === 'builtin' ? 'built-in' : 'admin'}</TableCell>
                    <TableCell>{v.author_user_id}</TableCell>
                    <TableCell>{v.change_note}</TableCell>
                    <TableCell>{new Date(v.created_at).toLocaleString()}</TableCell>
                    <TableCell className="space-x-2 whitespace-nowrap">
                      {v.is_active ? (
                        <span className="font-semibold text-green-700">Active</span>
                      ) : (
                        <Button size="sm" onClick={() => requestMove(v)}>
                          {activeVersion && v.sequence < activeVersion.sequence
                            ? `Roll back to v${v.sequence}`
                            : `Publish v${v.sequence}`}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setTestTarget(v)}
                        aria-label={`Test v${v.sequence}`}
                      >
                        Test
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => selectedName && loadIntoEditor(selectedName, v.id)}
                        aria-label={`Open v${v.sequence} in editor`}
                      >
                        Open
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {selected && testTarget && (
        <WorkflowTestChat
          key={testTarget.id}
          workflowName={selected.name}
          version={{ id: testTarget.id, sequence: testTarget.sequence }}
          onClose={() => setTestTarget(null)}
        />
      )}

      <AlertDialog
        open={pendingMove !== null}
        onOpenChange={(open) => {
          if (!open) setPendingMove(null)
        }}
      >
        <AlertDialogContent className="max-w-3xl">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingMove?.kind === 'rollback'
                ? `Roll back ${selectedName} to v${pendingMove?.target.sequence}?`
                : `Publish v${pendingMove?.target.sequence} of ${selectedName}?`}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>
                  It takes effect on the next chat turn. This change will be recorded in the audit
                  log.
                </p>
                {pendingMove?.diff ? (
                  <pre
                    aria-label="Diff against the active version"
                    className="max-h-80 overflow-auto bg-gray-50 border rounded p-2 text-xs font-mono"
                  >
                    {pendingMove.diff}
                  </pre>
                ) : (
                  <p>No active version to compare against.</p>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmMove}>
              {pendingMove?.kind === 'rollback' ? 'Roll back' : 'Publish'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
