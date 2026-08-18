export interface KnowledgeBase {
  id: string
  user_id: string
  title: string
  content: string
  doc_metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
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

export const knowledgeBaseClient = {
  async create(title: string, content: string, token: string, metadata?: Record<string, unknown>): Promise<KnowledgeBase> {
    const response = await authorizedFetch('/api/knowledge-base', token, {
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

    if (!response.ok) {
      throw new Error(`Failed to create knowledge base: ${response.statusText}`)
    }

    return response.json()
  },

  async list(token: string): Promise<KnowledgeBase[]> {
    const response = await authorizedFetch('/api/knowledge-base', token, {
      method: 'GET',
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch knowledge base: ${response.statusText}`)
    }

    const data = await response.json()
    return Array.isArray(data) ? data : []
  },

  async get(id: string, token: string): Promise<KnowledgeBase> {
    const response = await authorizedFetch(`/api/knowledge-base/${id}`, token, {
      method: 'GET',
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch knowledge base: ${response.statusText}`)
    }

    return response.json()
  },

  async update(id: string, title: string, content: string, token: string, metadata?: Record<string, unknown>): Promise<KnowledgeBase> {
    const response = await authorizedFetch(`/api/knowledge-base/${id}`, token, {
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

    if (!response.ok) {
      throw new Error(`Failed to update knowledge base: ${response.statusText}`)
    }

    return response.json()
  },

  async delete(id: string, token: string): Promise<void> {
    const response = await authorizedFetch(`/api/knowledge-base/${id}`, token, {
      method: 'DELETE',
    })

    if (!response.ok) {
      throw new Error(`Failed to delete knowledge base: ${response.statusText}`)
    }
  },
}
