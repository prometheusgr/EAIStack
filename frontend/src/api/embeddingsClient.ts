import { authorizedFetch, type AuthRefresh } from './authorizedFetch'
import type { EmbeddingResponse, SemanticSearchResult } from '@/types/embeddings'

export interface EmbeddingsClient {
  listEmbeddings(token: string, onRefresh: AuthRefresh): Promise<EmbeddingResponse[]>
  semanticSearch(query: string, token: string, onRefresh: AuthRefresh, topK?: number): Promise<SemanticSearchResult[]>
  getEmbedding(id: string, token: string, onRefresh: AuthRefresh): Promise<EmbeddingResponse>
  updateEmbedding(id: string, metadata: Record<string, unknown>, token: string, onRefresh: AuthRefresh): Promise<EmbeddingResponse>
  deleteEmbedding(id: string, token: string, onRefresh: AuthRefresh): Promise<void>
}

const embeddingsClient: EmbeddingsClient = {
  async listEmbeddings(token: string, onRefresh: AuthRefresh): Promise<EmbeddingResponse[]> {
    const response = await authorizedFetch('/api/embeddings', token, onRefresh, {
      method: 'GET',
    })

    const data = await response.json()
    return Array.isArray(data) ? data : data.embeddings || []
  },

  async semanticSearch(query: string, token: string, onRefresh: AuthRefresh, topK = 10): Promise<SemanticSearchResult[]> {
    const response = await authorizedFetch('/api/embeddings/search', token, onRefresh, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query_text: query,
        top_k: topK,
      }),
    })

    const data = await response.json()
    return data.results || []
  },

  async getEmbedding(id: string, token: string, onRefresh: AuthRefresh): Promise<EmbeddingResponse> {
    const response = await authorizedFetch(`/api/embeddings/${id}`, token, onRefresh, {
      method: 'GET',
    })

    return response.json()
  },

  async updateEmbedding(id: string, metadata: Record<string, unknown>, token: string, onRefresh: AuthRefresh): Promise<EmbeddingResponse> {
    const response = await authorizedFetch(`/api/embeddings/${id}`, token, onRefresh, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ metadata }),
    })

    return response.json()
  },

  async deleteEmbedding(id: string, token: string, onRefresh: AuthRefresh): Promise<void> {
    const response = await authorizedFetch(`/api/embeddings/${id}`, token, onRefresh, {
      method: 'DELETE',
    })
  },
}

export { embeddingsClient }
