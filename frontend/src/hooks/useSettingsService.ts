import { useAuth } from '@/context/AuthContext'
import { settingsClient } from '@/api/settingsClient'
import type { SystemSettingsResponse, UpdateSettingsRequest } from '@/types/settings'
import { useApiCall } from './useApiCall'
import { useApiMutation } from './useApiMutation'

export function useSettingsService() {
  const { token, refreshAccessToken } = useAuth()

  const get = useApiCall<SystemSettingsResponse>(
    async () => {
      if (!token) throw new Error('No auth token available')
      return settingsClient.getSettings(token, refreshAccessToken)
    },
    { immediate: false }
  )

  const update = useApiMutation<UpdateSettingsRequest, SystemSettingsResponse>(
    async (payload) => {
      if (!token) throw new Error('No auth token available')
      return settingsClient.updateSettings(payload, token, refreshAccessToken)
    }
  )

  return {
    get,
    update,
  }
}
