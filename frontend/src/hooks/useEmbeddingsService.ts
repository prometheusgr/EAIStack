import { useAuth } from '@/context/AuthContext'
import { embeddingsClient } from '@/api/embeddingsClient'
import { knowledgeBaseClient } from '@/api/knowledgeBaseClient'
import type { EmbeddingResponse, SemanticSearchResult } from '@/types/embeddings'
import { useApiCall } from './useApiCall'
import { useApiMutation } from './useApiMutation'

export function useEmbeddingsService(embeddingId?: string) {
  const { token, refreshAccessToken } = useAuth()

  const list = useApiCall(
    async () => {
      if (!token) throw new Error('No auth token available')
      const data = await embeddingsClient.listEmbeddings(token, refreshAccessToken)
      return data.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
    },
    { immediate: false }
  )

  const getEmbedding = useApiCall<EmbeddingResponse>(
    async () => {
      if (!token) throw new Error('No auth token available')
      if (!embeddingId) throw new Error('No embedding id provided')
      return embeddingsClient.getEmbedding(embeddingId, token, refreshAccessToken)
    },
    { immediate: false }
  )

  const search = useApiMutation<string, SemanticSearchResult[]>(
    async (queryText) => {
      if (!token) throw new Error('No auth token available')
      return embeddingsClient.semanticSearch(queryText, token, refreshAccessToken, 10)
    }
  )

  const upload = useApiMutation<{ title: string; content: string; metadata?: Record<string, unknown> }, void>(
    async ({ title, content, metadata }) => {
      if (!token) throw new Error('No auth token available')
      await knowledgeBaseClient.create(title, content, token, refreshAccessToken, metadata)
    }
  )

  const delete_ = useApiMutation<string, void>(
    async (docId) => {
      if (!token) throw new Error('No auth token available')
      return knowledgeBaseClient.delete(docId, token, refreshAccessToken)
    }
  )

  const update = useApiMutation<{ id: string; title: string; content: string; metadata?: Record<string, unknown> }, void>(
    async ({ id, title, content, metadata }) => {
      if (!token) throw new Error('No auth token available')
      await knowledgeBaseClient.update(id, title, content, token, refreshAccessToken, metadata)
    }
  )

  return {
    list,
    getEmbedding,
    search,
    upload,
    delete: delete_,
    update,
  }
}
