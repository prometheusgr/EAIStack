import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { authorizedFetch, type AuthRefresh } from './authorizedFetch'

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
  keyId: string
  name: string
  provider: string
}

const QUERY_KEY = ['apikeys']

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

export function useAPIKeys() {
  return useQuery<APIKey[]>({
    queryKey: QUERY_KEY,
    queryFn: async () => {
      const token = getAuthToken()
      const response = await authorizedFetch(
        '/api/apikeys',
        token,
        getRefreshFn(),
        {
          method: 'GET',
        }
      )

      if (!response.ok) {
        throw new Error(`Failed to fetch API keys: ${response.statusText}`)
      }

      return response.json()
    },
  })
}

export function useCreateAPIKey() {
  const queryClient = useQueryClient()
  return useMutation<APIKey, Error, APIKeyCreate>({
    mutationFn: async (payload: APIKeyCreate) => {
      const token = getAuthToken()
      const response = await authorizedFetch(
        '/api/apikeys',
        token,
        getRefreshFn(),
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        }
      )

      if (!response.ok) {
        throw new Error(`Failed to create API key: ${response.statusText}`)
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}

export function useUpdateAPIKey() {
  const queryClient = useQueryClient()
  return useMutation<APIKey, Error, APIKeyUpdate>({
    mutationFn: async ({ keyId, name, provider }: APIKeyUpdate) => {
      const token = getAuthToken()
      const response = await authorizedFetch(
        `/api/apikeys/${keyId}`,
        token,
        getRefreshFn(),
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ name, provider }),
        }
      )

      if (!response.ok) {
        throw new Error(`Failed to update API key: ${response.statusText}`)
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}

export function useRevokeAPIKey() {
  const queryClient = useQueryClient()
  return useMutation<APIKey, Error, string>({
    mutationFn: async (keyId: string) => {
      const token = getAuthToken()
      const response = await authorizedFetch(
        `/api/apikeys/${keyId}`,
        token,
        getRefreshFn(),
        {
          method: 'DELETE',
        }
      )

      if (!response.ok) {
        throw new Error(`Failed to revoke API key: ${response.statusText}`)
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}

export async function getAPIKeyDetail(keyId: string): Promise<APIKey> {
  const token = getAuthToken()
  const response = await authorizedFetch(
    `/api/apikeys/${keyId}`,
    token,
    getRefreshFn(),
    {
      method: 'GET',
    }
  )

  if (!response.ok) {
    throw new Error(`Failed to fetch API key detail: ${response.statusText}`)
  }

  return response.json()
}
