import { useAuth } from '@/context/AuthContext'
import { embeddingsClient } from '@/api/embeddingsClient'
import { knowledgeBaseClient } from '@/api/knowledgeBaseClient'
import type { SemanticSearchResult } from '@/types/embeddings'
import { useApiCall } from './useApiCall'
import { useApiMutation } from './useApiMutation'

export function useEmbeddingsService() {
  const { token } = useAuth()

  const list = useApiCall(
    async () => {
      if (!token) throw new Error('No auth token available')
      const data = await embeddingsClient.listEmbeddings(token)
      return data.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
    },
    { immediate: false }
  )

  const search = useApiMutation<string, SemanticSearchResult[]>(
    async (queryText) => {
      if (!token) throw new Error('No auth token available')
      return embeddingsClient.semanticSearch(queryText, token, 10)
    }
  )

  const upload = useApiMutation<{ title: string; content: string; metadata?: Record<string, unknown> }, void>(
    async ({ title, content, metadata }) => {
      if (!token) throw new Error('No auth token available')
      await knowledgeBaseClient.create(title, content, token, metadata)
    }
  )

  const delete_ = useApiMutation<string, void>(
    async (docId) => {
      if (!token) throw new Error('No auth token available')
      return knowledgeBaseClient.delete(docId, token)
    }
  )

  const update = useApiMutation<{ id: string; title: string; content: string; metadata?: Record<string, unknown> }, void>(
    async ({ id, title, content, metadata }) => {
      if (!token) throw new Error('No auth token available')
      await knowledgeBaseClient.update(id, title, content, token, metadata)
    }
  )

  return {
    list,
    search,
    upload,
    delete: delete_,
    update,
  }
}
