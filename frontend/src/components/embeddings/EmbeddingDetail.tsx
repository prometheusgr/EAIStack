import { useEffect, useState } from 'react'
import { useEmbeddingsService } from '@/hooks/useEmbeddingsService'
import { Button } from '@/components/ui/button'
import { SimilarityScore } from './SimilarityScore'
import { Skeleton } from '@/components/ui/skeleton'

interface EmbeddingDetailProps {
  id: string
  similarityScore?: number
  onBack?: () => void
  // Called after a successful delete, instead of onBack, so a caller that
  // keeps its own copy of the embeddings list (e.g. EmbeddingsList) can
  // remove the deleted row rather than leaving it stale once the user
  // returns to the list.
  onDeleted?: () => void
}

export function EmbeddingDetail({ id, similarityScore, onBack, onDeleted }: EmbeddingDetailProps) {
  const { getEmbedding, deleteDocument } = useEmbeddingsService(id)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  useEffect(() => {
    getEmbedding.execute()
  }, [id])

  const embedding = getEmbedding.data
  const loading = getEmbedding.isLoading || (!embedding && !getEmbedding.error)
  const error = getEmbedding.error?.message ?? null

  async function handleDelete() {
    if (!window.confirm('This will delete the document and all its embeddings. Are you sure?')) {
      return
    }
    setDeleteError(null)

    try {
      if (!embedding) {
        throw new Error('Embedding not loaded')
      }
      await deleteDocument.mutateAsync(embedding.doc_id)
      if (onDeleted) {
        onDeleted()
      } else if (onBack) {
        onBack()
      }
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="text-gray-500">Loading...</div>
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200" role="alert">
        {error}
      </div>
    )
  }

  if (!embedding) {
    return (
      <div className="p-4 bg-yellow-50 text-yellow-700 rounded border border-yellow-200">
        Embedding not found
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1">
          <h1 className="text-3xl font-bold">{embedding.title || 'Untitled'}</h1>
          <p className="text-sm text-gray-500 mt-1">ID: {embedding.id}</p>
        </div>
        {onBack && (
          <Button variant="outline" onClick={onBack}>
            ← Back
          </Button>
        )}
      </div>

      {similarityScore !== undefined && (
        <div className="bg-blue-50 p-4 rounded border border-blue-200">
          <div className="text-sm font-medium text-blue-900 mb-2">Similarity Score</div>
          <SimilarityScore score={similarityScore} />
        </div>
      )}

      {deleteError && (
        <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200" role="alert">
          {deleteError}
        </div>
      )}

      <div className="bg-white rounded border p-4">
        <h2 className="text-lg font-semibold mb-3">Content</h2>
        <p className="text-gray-700 whitespace-pre-wrap">{embedding.content}</p>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white rounded border p-4">
          <h2 className="text-lg font-semibold mb-3">Timestamps</h2>
          <div className="space-y-2 text-sm">
            <div>
              <span className="text-gray-600">Created:</span>
              <span className="ml-2 font-medium">
                {new Date(embedding.created_at).toLocaleString()}
              </span>
            </div>
            <div>
              <span className="text-gray-600">Updated:</span>
              <span className="ml-2 font-medium">
                {new Date(embedding.updated_at).toLocaleString()}
              </span>
            </div>
          </div>
        </div>

        {(embedding.embed_metadata || embedding.doc_metadata) && (
          <div className="bg-white rounded border p-4">
            <h2 className="text-lg font-semibold mb-3">Metadata</h2>
            <div className="space-y-3 text-sm">
              {embedding.embed_metadata && (
                <div>
                  <span className="text-gray-600">Embedding:</span>
                  <pre className="bg-gray-50 p-2 rounded mt-1 text-xs overflow-auto">
                    {JSON.stringify(embedding.embed_metadata, null, 2)}
                  </pre>
                </div>
              )}
              {embedding.doc_metadata && (
                <div>
                  <span className="text-gray-600">Document:</span>
                  <pre className="bg-gray-50 p-2 rounded mt-1 text-xs overflow-auto">
                    {JSON.stringify(embedding.doc_metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <Button variant="destructive" onClick={handleDelete}>
          Delete Document
        </Button>
      </div>
    </div>
  )
}
