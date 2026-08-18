import { embeddingsClient } from '@/api/embeddingsClient'
import type { EmbeddingResponse, SemanticSearchResult } from '@/types/embeddings'

export class EmbeddingsService {
  constructor(private token: string) {}

  async listEmbeddings(): Promise<EmbeddingResponse[]> {
    return embeddingsClient.listEmbeddings(this.token)
  }

  async search(query: string, topK?: number): Promise<SemanticSearchResult[]> {
    return embeddingsClient.semanticSearch(query, this.token, topK)
  }

  async getEmbedding(id: string): Promise<EmbeddingResponse> {
    return embeddingsClient.getEmbedding(id, this.token)
  }

  async updateEmbedding(id: string, metadata: Record<string, unknown>): Promise<EmbeddingResponse> {
    return embeddingsClient.updateEmbedding(id, metadata, this.token)
  }

  async deleteEmbedding(id: string): Promise<void> {
    return embeddingsClient.deleteEmbedding(id, this.token)
  }
}
