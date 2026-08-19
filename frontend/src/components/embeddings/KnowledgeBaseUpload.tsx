import { useState } from 'react'
import { useEmbeddingsService } from '@/hooks/useEmbeddingsService'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export interface KnowledgeBaseUploadProps {
  onUploadSuccess?: () => void
  onUploadError?: (error: string) => void
}

export function KnowledgeBaseUpload({ onUploadSuccess, onUploadError }: KnowledgeBaseUploadProps) {
  const { upload } = useEmbeddingsService()
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim() || !content.trim()) {
      setError('Title and content are required')
      return
    }

    setError(null)

    try {
      await upload.mutateAsync({ title: title.trim(), content: content.trim(), metadata: {} })

      // Clear form
      setTitle('')
      setContent('')

      onUploadSuccess?.()
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Upload failed'
      setError(errorMsg)
      onUploadError?.(errorMsg)
    }
  }

  return (
    <div className="border rounded-lg p-6 bg-gray-50">
      <h3 className="text-lg font-semibold mb-4">Add Knowledge Base Entry</h3>

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded border border-red-200 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="kb-title" className="block text-sm font-medium mb-1">
            Title
          </label>
          <Input
            id="kb-title"
            placeholder="Document title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={upload.isPending}
            maxLength={500}
          />
          <p className="text-xs text-gray-500 mt-1">{title.length}/500 characters</p>
        </div>

        <div>
          <label htmlFor="kb-content" className="block text-sm font-medium mb-1">
            Content
          </label>
          <textarea
            id="kb-content"
            placeholder="Document content..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={upload.isPending}
            className="w-full p-2 border rounded-md font-mono text-sm min-h-[120px] focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-gray-500 mt-1">{content.length} characters</p>
        </div>

        <div className="flex gap-2 justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setTitle('')
              setContent('')
              setError(null)
            }}
            disabled={upload.isPending}
          >
            Clear
          </Button>
          <Button type="submit" disabled={upload.isPending || !title.trim() || !content.trim()}>
            {upload.isPending ? 'Uploading...' : 'Create Entry'}
          </Button>
        </div>
      </form>
    </div>
  )
}
