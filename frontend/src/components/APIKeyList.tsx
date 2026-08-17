import { useState } from 'react'
import { APIKey } from '../api/apiKeysClient'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table'
import { Button } from './ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from './ui/alert-dialog'
import { APIKeyDetailModal } from './APIKeyDetailModal'

interface APIKeyListProps {
  keys: APIKey[]
  onUpdate: (keyId: string, name: string, provider: string) => Promise<void>
  onRevoke: (keyId: string) => Promise<void>
}

export function APIKeyList({ keys, onUpdate, onRevoke }: APIKeyListProps) {
  const [selectedKey, setSelectedKey] = useState<APIKey | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [isRevokeConfirmOpen, setIsRevokeConfirmOpen] = useState(false)
  const [keyToRevoke, setKeyToRevoke] = useState<string | null>(null)

  const handleRowClick = (key: APIKey) => {
    setSelectedKey(key)
    setIsDetailOpen(true)
  }

  const handleRevokeClick = (e: React.MouseEvent, keyId: string) => {
    e.stopPropagation()
    setKeyToRevoke(keyId)
    setIsRevokeConfirmOpen(true)
  }

  const handleConfirmRevoke = async () => {
    if (keyToRevoke) {
      await onRevoke(keyToRevoke)
      setIsRevokeConfirmOpen(false)
      setKeyToRevoke(null)
    }
  }

  if (keys.length === 0) {
    return (
      <div className="text-center py-12 px-4">
        <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-muted mb-4">
          <span className="text-2xl">🔑</span>
        </div>
        <h3 className="text-lg font-semibold mb-1">No API keys yet</h3>
        <p className="text-muted-foreground mb-4">
          Create your first API key to manage third-party service credentials.
        </p>
      </div>
    )
  }

  return (
    <>
      <div className="border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {keys.map((key) => (
              <TableRow
                key={key.id}
                className="cursor-pointer hover:bg-muted"
                onClick={() => handleRowClick(key)}
              >
                <TableCell className="font-medium">{key.name}</TableCell>
                <TableCell>{key.provider}</TableCell>
                <TableCell>{new Date(key.created_at).toLocaleDateString()}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={(e) => handleRevokeClick(e, key.id)}
                  >
                    Revoke
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {selectedKey && (
        <APIKeyDetailModal
          key={selectedKey.id}
          apiKey={selectedKey}
          open={isDetailOpen}
          onOpenChange={setIsDetailOpen}
          onUpdate={onUpdate}
        />
      )}

      <AlertDialog open={isRevokeConfirmOpen} onOpenChange={setIsRevokeConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke API Key?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. The API key will be permanently revoked and can no longer be used.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex gap-4">
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmRevoke} className="bg-destructive text-destructive-foreground">
              Revoke
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
