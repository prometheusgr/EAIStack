import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { authorizedFetch } from './authorizedFetch'

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

export function useAPIKeys() {
  const { token, refreshAccessToken } = useAuth()
  return useQuery<APIKey[]>({
    queryKey: QUERY_KEY,
    queryFn: async () => {
      const response = await authorizedFetch(
        '/api/apikeys',
        token,
        refreshAccessToken,
        {
          method: 'GET',
        }
      )

      return response.json()
    },
  })
}

export function useCreateAPIKey() {
  const { token, refreshAccessToken } = useAuth()
  const queryClient = useQueryClient()
  return useMutation<APIKey, Error, APIKeyCreate>({
    mutationFn: async (payload: APIKeyCreate) => {
      const response = await authorizedFetch(
        '/api/apikeys',
        token,
        refreshAccessToken,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        }
      )

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}

export function useUpdateAPIKey() {
  const { token, refreshAccessToken } = useAuth()
  const queryClient = useQueryClient()
  return useMutation<APIKey, Error, APIKeyUpdate>({
    mutationFn: async ({ keyId, name, provider }: APIKeyUpdate) => {
      const response = await authorizedFetch(
        `/api/apikeys/${keyId}`,
        token,
        refreshAccessToken,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ name, provider }),
        }
      )

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}

export function useRevokeAPIKey() {
  const { token, refreshAccessToken } = useAuth()
  const queryClient = useQueryClient()
  return useMutation<APIKey, Error, string>({
    mutationFn: async (keyId: string) => {
      const response = await authorizedFetch(
        `/api/apikeys/${keyId}`,
        token,
        refreshAccessToken,
        {
          method: 'DELETE',
        }
      )

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}
