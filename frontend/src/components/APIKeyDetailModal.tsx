import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { APIKey } from '../api/apiKeysClient'
import { APIKeyUpdateSchema, type APIKeyUpdateFormData } from '../lib/apiKeySchemas'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from './ui/dialog'
import { Button } from './ui/button'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from './ui/form'
import { Input } from './ui/input'

interface APIKeyDetailModalProps {
  apiKey: APIKey
  open: boolean
  onOpenChange: (open: boolean) => void
  onUpdate: (keyId: string, name: string, provider: string) => Promise<void>
}

export function APIKeyDetailModal({
  apiKey,
  open,
  onOpenChange,
  onUpdate,
}: APIKeyDetailModalProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const form = useForm<APIKeyUpdateFormData>({
    resolver: zodResolver(APIKeyUpdateSchema),
    defaultValues: {
      name: apiKey.name,
      provider: apiKey.provider,
    },
  })

  const handleSave = async (data: APIKeyUpdateFormData) => {
    setIsSaving(true)
    try {
      await onUpdate(apiKey.id, data.name, data.provider)
      setIsEditing(false)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit API Key' : 'API Key Details'}</DialogTitle>
        </DialogHeader>

        {!isEditing ? (
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-base">{apiKey.name}</p>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Provider</label>
              <p className="text-base">{apiKey.provider}</p>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Secret (Masked)</label>
              <p className="text-base font-mono text-sm">{apiKey.secret_value_masked}</p>
              <p className="text-xs text-muted-foreground mt-1">
                For security, the full secret value is never displayed.
              </p>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Created</label>
              <p className="text-base">{new Date(apiKey.created_at).toLocaleString()}</p>
            </div>

            {apiKey.revoked_at && (
              <div className="p-3 bg-destructive/10 rounded">
                <p className="text-sm font-medium text-destructive">
                  This key was revoked on {new Date(apiKey.revoked_at).toLocaleString()}
                </p>
              </div>
            )}

            <DialogFooter>
              {!apiKey.revoked_at && (
                <Button onClick={() => setIsEditing(true)}>Edit Name</Button>
              )}
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Close
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleSave)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="Enter key name" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Provider</FormLabel>
                    <FormControl>
                      <select
                        {...field}
                        className="flex h-10 rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm"
                      >
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic</option>
                        <option value="huggingface">HuggingFace</option>
                        <option value="custom">Custom</option>
                      </select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setIsEditing(false)
                    form.reset()
                  }}
                  disabled={isSaving}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isSaving}>
                  {isSaving ? 'Saving...' : 'Save'}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        )}
      </DialogContent>
    </Dialog>
  )
}
