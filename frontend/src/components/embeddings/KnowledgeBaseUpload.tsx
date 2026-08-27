import { useRef, useState } from 'react'
import { useEmbeddingsService } from '@/hooks/useEmbeddingsService'
import { useIsMounted } from '@/hooks/useIsMounted'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export interface KnowledgeBaseUploadProps {
  onUploadSuccess?: () => void
  onUploadError?: (error: string) => void
}

type Mode = 'paste' | 'file'

export function KnowledgeBaseUpload({ onUploadSuccess, onUploadError }: KnowledgeBaseUploadProps) {
  const { upload, uploadFile } = useEmbeddingsService()
  const isMounted = useIsMounted()
  const [mode, setMode] = useState<Mode>('paste')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const isBusy = upload.isPending || uploadFile.isPending

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    // Clear both tabs' draft state on every switch, not just the
    // destination tab's: leaving stale text/a stale file selection behind
    // in the tab the user is leaving lets it resurface (and be
    // submittable) if they switch back later.
    setTitle('')
    setContent('')
    setSelectedFile(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  async function handlePasteSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim() || !content.trim()) {
      setError('Title and content are required')
      return
    }

    setError(null)

    try {
      await upload.mutateAsync({ title: title.trim(), content: content.trim(), metadata: {} })

      if (isMounted()) {
        setTitle('')
        setContent('')
      }

      onUploadSuccess?.()
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Upload failed'
      if (isMounted()) setError(errorMsg)
      onUploadError?.(errorMsg)
    }
  }

  async function handleFileSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedFile) {
      setError('Choose a file first')
      return
    }

    setError(null)

    try {
      await uploadFile.mutateAsync(selectedFile)

      if (isMounted()) {
        setSelectedFile(null)
        if (fileInputRef.current) {
          fileInputRef.current.value = ''
        }
      }

      onUploadSuccess?.()
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Upload failed'
      if (isMounted()) setError(errorMsg)
      onUploadError?.(errorMsg)
    }
  }

  return (
    <div className="border rounded-lg p-6 bg-gray-50">
      <h3 className="text-lg font-semibold mb-4">Add Knowledge Base Entry</h3>

      <div role="tablist" className="flex gap-1 mb-4 border-b">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'paste'}
          onClick={() => switchMode('paste')}
          disabled={isBusy}
          className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px disabled:opacity-50 disabled:pointer-events-none ${
            mode === 'paste'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Paste Text
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'file'}
          onClick={() => switchMode('file')}
          disabled={isBusy}
          className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px disabled:opacity-50 disabled:pointer-events-none ${
            mode === 'file'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Upload File
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded border border-red-200 text-sm">
          {error}
        </div>
      )}

      {mode === 'paste' ? (
        <form onSubmit={handlePasteSubmit} className="space-y-4">
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
      ) : (
        <form onSubmit={handleFileSubmit} className="space-y-4">
          <div>
            <label htmlFor="kb-file" className="block text-sm font-medium mb-1">
              Choose file
            </label>
            <input
              id="kb-file"
              ref={fileInputRef}
              type="file"
              accept=".txt,.pdf,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
              disabled={uploadFile.isPending}
              className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            <p className="text-xs text-gray-500 mt-1">
              Supported: plain text (.txt), PDF (.pdf), Word (.docx)
            </p>
          </div>

          <div className="flex gap-2 justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setSelectedFile(null)
                if (fileInputRef.current) fileInputRef.current.value = ''
                setError(null)
              }}
              disabled={uploadFile.isPending}
            >
              Clear
            </Button>
            <Button type="submit" disabled={uploadFile.isPending || !selectedFile}>
              {uploadFile.isPending ? 'Uploading...' : 'Upload'}
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}
