import type { EmbeddingResponse, SemanticSearchResult } from '@/types/embeddings'

export interface EmbeddingsClient {
  listEmbeddings(token: string): Promise<EmbeddingResponse[]>
  semanticSearch(query: string, token: string, topK?: number): Promise<SemanticSearchResult[]>
  getEmbedding(id: string, token: string): Promise<EmbeddingResponse>
  updateEmbedding(id: string, metadata: Record<string, unknown>, token: string): Promise<EmbeddingResponse>
  deleteEmbedding(id: string, token: string): Promise<void>
}

async function authorizedFetch(
  url: string,
  token: string,
  options?: RequestInit
): Promise<Response> {
  const headers = {
    ...options?.headers,
    Authorization: `Bearer ${token}`,
  } as Record<string, string>

  return fetch(url, {
    ...options,
    headers,
  })
}

const embeddingsClient: EmbeddingsClient = {
  async listEmbeddings(token: string): Promise<EmbeddingResponse[]> {
    const response = await authorizedFetch('/api/embeddings', token, {
      method: 'GET',
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch embeddings: ${response.statusText}`)
    }

    const data = await response.json()
    return Array.isArray(data) ? data : data.embeddings || []
  },

  async semanticSearch(query: string, token: string, topK = 10): Promise<SemanticSearchResult[]> {
    const response = await authorizedFetch('/api/embeddings/search', token, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query_text: query,
        top_k: topK,
      }),
    })

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`)
    }

    const data = await response.json()
    return data.results || []
  },

  async getEmbedding(id: string, token: string): Promise<EmbeddingResponse> {
    const response = await authorizedFetch(`/api/embeddings/${id}`, token, {
      method: 'GET',
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch embedding: ${response.statusText}`)
    }

    return response.json()
  },

  async updateEmbedding(id: string, metadata: Record<string, unknown>, token: string): Promise<EmbeddingResponse> {
    const response = await authorizedFetch(`/api/embeddings/${id}`, token, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ metadata }),
    })

    if (!response.ok) {
      throw new Error(`Failed to update embedding: ${response.statusText}`)
    }

    return response.json()
  },

  async deleteEmbedding(id: string, token: string): Promise<void> {
    const response = await authorizedFetch(`/api/embeddings/${id}`, token, {
      method: 'DELETE',
    })

    if (!response.ok) {
      throw new Error(`Failed to delete embedding: ${response.statusText}`)
    }
  },
}

export { embeddingsClient }
