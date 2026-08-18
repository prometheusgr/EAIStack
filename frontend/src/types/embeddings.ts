export interface EmbeddingResponse {
  id: string
  doc_id: string
  embedding: number[]
  embed_metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
  deleted_at?: string | null
  title?: string
  content?: string
  doc_metadata?: Record<string, unknown>
}

export interface SemanticSearchResult {
  id: string
  doc_id: string
  title: string
  content: string
  preview: string
  similarity_score: number
  created_at: string
  embed_metadata?: Record<string, unknown>
  doc_metadata?: Record<string, unknown>
}

export interface ListEmbeddingsResponse {
  embeddings: EmbeddingResponse[]
}

export interface SemanticSearchResponse {
  results: SemanticSearchResult[]
  query_count: number
}
