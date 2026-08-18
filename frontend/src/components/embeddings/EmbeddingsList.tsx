import { useEffect, useState } from 'react'
import { embeddingsClient } from '@/services/embeddingsClient'
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
  const [embeddings, setEmbeddings] = useState<EmbeddingResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadEmbeddings()
  }, [])

  async function loadEmbeddings() {
    setLoading(true)
    setError(null)

    try {
      const data = await embeddingsClient.listEmbeddings()
      const sorted = data.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      setEmbeddings(sorted)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load embeddings')
      setEmbeddings([])
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(id: string) {
    try {
      await embeddingsClient.deleteEmbedding(id)
      setEmbeddings((prev) => prev.filter((e) => e.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  if (loading) {
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
        {error}
      </div>
    )
  }

  if (embeddings.length === 0) {
    return (
      <div className="space-y-6">
        <KnowledgeBaseUpload onUploadSuccess={loadEmbeddings} />
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg">No embeddings found yet</p>
          <p className="text-sm">Add a knowledge base entry above to get started</p>
        </div>
      </div>
    )
  }

  return (
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
                  onClick={() => handleDelete(embedding.id)}
                  className="text-red-600 hover:text-red-700 hover:bg-red-50"
                >
                  Delete
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
