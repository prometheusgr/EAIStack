import { authorizedFetch, type AuthRefresh } from '@/api/authorizedFetch'

export interface APIKey {
  id: string
  user_id: string
  name: string
  provider: string
  secret_value_masked: string
  created_at: string
  updated_at?: string
  revoked_at?: string | null
}

export interface APIKeyCreate {
  name: string
  provider: string
  secret_value: string
}

export interface APIKeyUpdate {
  name: string
  provider: string
}

export class APIKeyService {
  constructor(
    private token: string,
    private onRefresh: AuthRefresh = async () => true
  ) {}

  async list(): Promise<APIKey[]> {
    const response = await authorizedFetch('/api/apikeys', this.token, this.onRefresh, {
      method: 'GET',
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch API keys: ${response.statusText}`)
    }

    return response.json()
  }

  async create(payload: APIKeyCreate): Promise<APIKey> {
    const response = await authorizedFetch('/api/apikeys', this.token, this.onRefresh, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      throw new Error(`Failed to create API key: ${response.statusText}`)
    }

    return response.json()
  }

  async update(keyId: string, payload: APIKeyUpdate): Promise<APIKey> {
    const response = await authorizedFetch(`/api/apikeys/${keyId}`, this.token, this.onRefresh, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      throw new Error(`Failed to update API key: ${response.statusText}`)
    }

    return response.json()
  }

  async delete(keyId: string): Promise<APIKey> {
    const response = await authorizedFetch(`/api/apikeys/${keyId}`, this.token, this.onRefresh, {
      method: 'DELETE',
    })

    if (!response.ok) {
      throw new Error(`Failed to revoke API key: ${response.statusText}`)
    }

    return response.json()
  }

  async getDetail(keyId: string): Promise<APIKey> {
    const response = await authorizedFetch(`/api/apikeys/${keyId}`, this.token, this.onRefresh, {
      method: 'GET',
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch API key detail: ${response.statusText}`)
    }

    return response.json()
  }
}
