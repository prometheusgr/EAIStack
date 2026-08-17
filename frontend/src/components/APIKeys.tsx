import { useState } from 'react'
import { useAPIKeys, useCreateAPIKey, useUpdateAPIKey, useRevokeAPIKey } from '../api/apiKeysClient'
import { APIKeyList } from './APIKeyList'
import { APIKeyForm } from './APIKeyForm'
import { Button } from './ui/button'
import { TableSkeleton } from './ui/skeleton'
import { useToast } from './ui/toast'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'
import { AlertCircle, RotateCcw } from 'lucide-react'

export function APIKeys() {
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const { data: keys, isLoading, error, refetch } = useAPIKeys()
  const { addToast } = useToast()
  const createMutation = useCreateAPIKey()
  const updateMutation = useUpdateAPIKey()
  const revokeMutation = useRevokeAPIKey()

  const handleCreate = async (data: { name: string; provider: string; secret_value: string }) => {
    try {
      await createMutation.mutateAsync(data)
      addToast('API key created successfully', 'success')
      setIsCreateOpen(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create API key'
      addToast(message, 'error')
    }
  }

  const handleUpdate = async (keyId: string, name: string, provider: string) => {
    try {
      await updateMutation.mutateAsync({ keyId, name, provider })
      addToast('API key updated successfully', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update API key'
      addToast(message, 'error')
    }
  }

  const handleRevoke = async (keyId: string) => {
    try {
      await revokeMutation.mutateAsync(keyId)
      addToast('API key revoked successfully', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to revoke API key'
      addToast(message, 'error')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-2xl font-bold">API Keys</h2>
          <p className="text-sm text-muted-foreground">Manage your API keys for third-party services</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
            className="gap-2"
          >
            <RotateCcw className="h-4 w-4" />
            Refresh
          </Button>
          <Button onClick={() => setIsCreateOpen(true)} disabled={isLoading}>
            Create API Key
          </Button>
        </div>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex gap-3">
          <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-900">Failed to load API keys</p>
            <p className="text-sm text-red-800 mt-1">
              {error instanceof Error ? error.message : 'An error occurred while fetching your API keys'}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="mt-3 text-red-600 border-red-200 hover:bg-red-100"
            >
              Try again
            </Button>
          </div>
        </div>
      ) : (
        <APIKeyList
          keys={keys || []}
          onUpdate={handleUpdate}
          onRevoke={handleRevoke}
        />
      )}

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
          </DialogHeader>
          <APIKeyForm
            onSubmit={handleCreate}
            isLoading={createMutation.isPending}
          />
        </DialogContent>
      </Dialog>
    </div>
  )
}
