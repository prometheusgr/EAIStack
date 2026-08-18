import { useState } from 'react'
import { embeddingsClient } from '@/services/embeddingsClient'
import type { SemanticSearchResult } from '@/types/embeddings'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { KnowledgeBaseUpload } from './KnowledgeBaseUpload'

export function EmbeddingsSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SemanticSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)

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

  return (
    <div className="space-y-6">
      <KnowledgeBaseUpload />

      <div className="border-t pt-6">
        <h3 className="text-lg font-semibold mb-4">Search Knowledge Base</h3>
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

      {error && (
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
          <div key={result.id} className="border rounded p-4 hover:bg-gray-50 cursor-pointer transition">
            <div className="flex justify-between items-start mb-2">
              <h3 className="font-semibold text-lg">{result.title}</h3>
              <div className="text-sm font-medium text-blue-600 whitespace-nowrap ml-2">
                {(result.similarity_score * 100).toFixed(1)}%
              </div>
            </div>
            <p className="text-sm text-gray-600 mb-2">{result.preview}</p>
            <p className="text-xs text-gray-400">
              {new Date(result.created_at).toLocaleDateString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
