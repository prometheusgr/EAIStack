import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { embeddingsClient } from '@/services/embeddingsClient'
import { knowledgeBaseClient } from '@/services/knowledgeBaseClient'
import type { EmbeddingResponse } from '@/types/embeddings'
import { Button } from '@/components/ui/button'
import { KnowledgeBaseUpload } from './KnowledgeBaseUpload'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'

export function EmbeddingsList() {
  const queryClient = useQueryClient()
  const [deleting, setDeleting] = useState<string | null>(null)

  const { data: embeddings = [], isLoading, error, refetch } = useQuery<EmbeddingResponse[]>({
    queryKey: ['embeddings'],
    queryFn: async () => {
      const data = await embeddingsClient.listEmbeddings()
      return data.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
    },
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  })

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => knowledgeBaseClient.delete(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['embeddings'] })
    },
  })

  async function handleDelete(docId: string, embeddingId: string) {
    if (!window.confirm('Are you sure you want to delete this entry?')) {
      return
    }

    setDeleting(embeddingId)
    try {
      await deleteMutation.mutateAsync(docId)
    } finally {
      setDeleting(null)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="text-gray-500">Loading...</div>
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200" role="alert">
        <p>{error instanceof Error ? error.message : 'Failed to load embeddings'}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          className="mt-2"
        >
          Retry
        </Button>
      </div>
    )
  }

  if (embeddings.length === 0) {
    return (
      <div className="space-y-6">
        <KnowledgeBaseUpload onUploadSuccess={() => refetch()} />
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg">No documents yet</p>
          <p className="text-sm">Create a knowledge base entry above to get started</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <KnowledgeBaseUpload onUploadSuccess={() => refetch()} />
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {embeddings.map((embedding) => (
              <TableRow key={embedding.id} className="hover:bg-gray-50">
                <TableCell className="font-medium">{embedding.title || 'Untitled'}</TableCell>
                <TableCell>{new Date(embedding.created_at).toLocaleDateString()}</TableCell>
                <TableCell>{new Date(embedding.updated_at).toLocaleDateString()}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(embedding.doc_id, embedding.id)}
                    disabled={deleting === embedding.id || deleteMutation.isPending}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    {deleting === embedding.id ? 'Deleting...' : 'Delete'}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
