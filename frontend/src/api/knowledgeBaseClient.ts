import { authorizedFetch, type AuthRefresh } from './authorizedFetch'

export interface KnowledgeBase {
  id: string
  user_id: string
  title: string
  content: string
  doc_metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export const knowledgeBaseClient = {
  async create(title: string, content: string, token: string, onRefresh: AuthRefresh, metadata?: Record<string, unknown>): Promise<KnowledgeBase> {
    const response = await authorizedFetch('/api/knowledge-base', token, onRefresh, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        title,
        content,
        metadata: metadata || {},
      }),
    })

    return response.json()
  },

  async list(token: string, onRefresh: AuthRefresh): Promise<KnowledgeBase[]> {
    const response = await authorizedFetch('/api/knowledge-base', token, onRefresh, {
      method: 'GET',
    })

    const data = await response.json()
    return Array.isArray(data) ? data : []
  },

  async get(id: string, token: string, onRefresh: AuthRefresh): Promise<KnowledgeBase> {
    const response = await authorizedFetch(`/api/knowledge-base/${id}`, token, onRefresh, {
      method: 'GET',
    })

    return response.json()
  },

  async update(id: string, title: string, content: string, token: string, onRefresh: AuthRefresh, metadata?: Record<string, unknown>): Promise<KnowledgeBase> {
    const response = await authorizedFetch(`/api/knowledge-base/${id}`, token, onRefresh, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        title,
        content,
        metadata: metadata || {},
      }),
    })

    return response.json()
  },

  async delete(id: string, token: string, onRefresh: AuthRefresh): Promise<void> {
    const response = await authorizedFetch(`/api/knowledge-base/${id}`, token, onRefresh, {
      method: 'DELETE',
    })
  },
}
