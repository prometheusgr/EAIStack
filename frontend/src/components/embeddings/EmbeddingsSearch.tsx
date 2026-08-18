import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { embeddingsClient } from '@/services/embeddingsClient'
import { knowledgeBaseClient } from '@/services/knowledgeBaseClient'
import type { SemanticSearchResult } from '@/types/embeddings'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function EmbeddingsSearch() {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SemanticSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => knowledgeBaseClient.delete(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['embeddings'] })
    },
  })

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return

    setLoading(true)
    setError(null)
    setHasSearched(true)

    try {
      const searchResults = await embeddingsClient.semanticSearch(query, 10)
      setResults(searchResults)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(docId: string, embeddingId: string) {
    if (!window.confirm('Are you sure you want to delete this entry?')) {
      return
    }

    setDeleting(embeddingId)
    try {
      await deleteMutation.mutateAsync(docId)
      setResults((prev) => prev.filter((r) => r.id !== embeddingId))
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-4">Search</h3>
        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            placeholder="Search by topic or content..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
            aria-label="Search embeddings"
          />
          <Button type="submit" disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </Button>
        </form>
      </div>

      {error && !loading && (
        <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200" role="alert">
          {error}
        </div>
      )}

      {!loading && !hasSearched && (
        <div className="text-center text-gray-500 py-8">Enter a query to search</div>
      )}

      {!loading && hasSearched && results.length === 0 && (
        <div className="text-center text-gray-500 py-8">No results found</div>
      )}

      <div className="space-y-4">
        {results.map((result) => (
          <div key={result.id} className="border rounded p-4 hover:bg-gray-50 transition">
            <div className="flex justify-between items-start mb-2">
              <div className="flex-1">
                <h3 className="font-semibold text-lg">{result.title}</h3>
                <div className="text-sm font-medium text-blue-600 mt-1">
                  {(result.similarity_score * 100).toFixed(1)}% match
                </div>
              </div>
            </div>
            <p className="text-sm text-gray-600 mb-3">{result.preview}</p>
            <div className="flex justify-between items-center">
              <p className="text-xs text-gray-400">
                {new Date(result.created_at).toLocaleDateString()}
              </p>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleDelete(result.doc_id, result.id)}
                disabled={deleting === result.id || deleteMutation.isPending}
                className="text-red-600 hover:text-red-700 hover:bg-red-50"
              >
                {deleting === result.id ? 'Deleting...' : 'Delete'}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
