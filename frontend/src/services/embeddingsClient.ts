import { authorizedFetch, type AuthRefresh } from '@/api/authorizedFetch'
import type { EmbeddingResponse, SemanticSearchResult, SemanticSearchResponse } from '@/types/embeddings'

export interface EmbeddingsClient {
  listEmbeddings(): Promise<EmbeddingResponse[]>
  semanticSearch(queryText: string, topK?: number): Promise<SemanticSearchResult[]>
  getEmbedding(id: string): Promise<EmbeddingResponse>
  updateEmbedding(id: string, metadata: Record<string, unknown>): Promise<EmbeddingResponse>
  deleteEmbedding(id: string): Promise<void>
}

function getAuthToken(): string {
  const token = localStorage.getItem('access_token')
  if (!token) {
    throw new Error('No auth token available')
  }
  return token
}

function getRefreshFn(): AuthRefresh {
  return async () => {
    const event = new CustomEvent('auth-refresh-needed')
    window.dispatchEvent(event)
    return true
  }
}

const embeddingsClient: EmbeddingsClient = {
  async listEmbeddings(): Promise<EmbeddingResponse[]> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      '/api/embeddings',
      token,
      getRefreshFn(),
      {
        method: 'GET',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch embeddings: ${response.statusText}`)
    }

    const data = await response.json()
    return Array.isArray(data) ? data : data.embeddings || []
  },

  async semanticSearch(queryText: string, topK = 10): Promise<SemanticSearchResult[]> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      '/api/embeddings/search',
      token,
      getRefreshFn(),
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query_text: queryText,
          top_k: topK,
        }),
      }
    )

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`)
    }

    const data: SemanticSearchResponse = await response.json()
    return data.results || []
  },

  async getEmbedding(id: string): Promise<EmbeddingResponse> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      `/api/embeddings/${id}`,
      token,
      getRefreshFn(),
      {
        method: 'GET',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch embedding: ${response.statusText}`)
    }

    return response.json()
  },

  async updateEmbedding(id: string, metadata: Record<string, unknown>): Promise<EmbeddingResponse> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      `/api/embeddings/${id}`,
      token,
      getRefreshFn(),
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ metadata }),
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to update embedding: ${response.statusText}`)
    }

    return response.json()
  },

  async deleteEmbedding(id: string): Promise<void> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      `/api/embeddings/${id}`,
      token,
      getRefreshFn(),
      {
        method: 'DELETE',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to delete embedding: ${response.statusText}`)
    }
  },
}

export { embeddingsClient }
