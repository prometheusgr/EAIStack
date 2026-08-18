import { authorizedFetch, type AuthRefresh } from '@/api/authorizedFetch'

export interface KnowledgeBase {
  id: string
  user_id: string
  title: string
  content: string
  doc_metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
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

export const knowledgeBaseClient = {
  async create(title: string, content: string, metadata?: Record<string, unknown>): Promise<KnowledgeBase> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      '/api/knowledge-base',
      token,
      getRefreshFn(),
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title,
          content,
          metadata: metadata || {},
        }),
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to create knowledge base: ${response.statusText}`)
    }

    return response.json()
  },

  async list(): Promise<KnowledgeBase[]> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      '/api/knowledge-base',
      token,
      getRefreshFn(),
      {
        method: 'GET',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch knowledge base: ${response.statusText}`)
    }

    const data = await response.json()
    return Array.isArray(data) ? data : []
  },

  async get(id: string): Promise<KnowledgeBase> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      `/api/knowledge-base/${id}`,
      token,
      getRefreshFn(),
      {
        method: 'GET',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch knowledge base: ${response.statusText}`)
    }

    return response.json()
  },

  async update(id: string, title: string, content: string, metadata?: Record<string, unknown>): Promise<KnowledgeBase> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      `/api/knowledge-base/${id}`,
      token,
      getRefreshFn(),
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title,
          content,
          metadata: metadata || {},
        }),
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to update knowledge base: ${response.statusText}`)
    }

    return response.json()
  },

  async delete(id: string): Promise<void> {
    const token = getAuthToken()
    const response = await authorizedFetch(
      `/api/knowledge-base/${id}`,
      token,
      getRefreshFn(),
      {
        method: 'DELETE',
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to delete knowledge base: ${response.statusText}`)
    }
  },
}
