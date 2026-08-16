import { useState } from 'react'
import { useAPIKeys, useCreateAPIKey, useUpdateAPIKey, useRevokeAPIKey } from '../api/apiKeysClient'
import { APIKeyList } from './APIKeyList'
import { APIKeyForm } from './APIKeyForm'
import { Button } from './ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'

export function APIKeys() {
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const { data: keys, isLoading, error, refetch } = useAPIKeys()
  const createMutation = useCreateAPIKey()
  const updateMutation = useUpdateAPIKey()
  const revokeMutation = useRevokeAPIKey()

  const handleCreate = async (data: { name: string; provider: string; secret_value: string }) => {
    try {
      await createMutation.mutateAsync(data)
      setIsCreateOpen(false)
      refetch()
    } catch (err) {
      console.error('Failed to create API key:', err)
    }
  }

  const handleUpdate = async (keyId: string, name: string) => {
    try {
      await updateMutation.mutateAsync({ keyId, name })
      refetch()
    } catch (err) {
      console.error('Failed to update API key:', err)
    }
  }

  const handleRevoke = async (keyId: string) => {
    try {
      await revokeMutation.mutateAsync(keyId)
      refetch()
    } catch (err) {
      console.error('Failed to revoke API key:', err)
    }
  }

  if (isLoading) {
    return <div className="text-center py-8">Loading API keys...</div>
  }

  if (error) {
    return <div className="text-center py-8 text-red-500">Failed to load API keys</div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">API Keys</h2>
        <Button onClick={() => setIsCreateOpen(true)}>Create API Key</Button>
      </div>

      <APIKeyList
        keys={keys || []}
        onUpdate={handleUpdate}
        onRevoke={handleRevoke}
      />

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
