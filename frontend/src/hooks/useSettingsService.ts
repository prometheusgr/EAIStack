import { useAuth } from '@/context/AuthContext'
import { SettingsService } from '@/services/settingsService'
import type { SystemSettingsResponse, UpdateSettingsRequest } from '@/types/settings'
import { useApiCall } from './useApiCall'
import { useApiMutation } from './useApiMutation'

export function useSettingsService() {
  const { token, refreshAccessToken } = useAuth()

  const get = useApiCall<SystemSettingsResponse>(
    async () => {
      if (!token) throw new Error('No auth token available')
      const service = new SettingsService(token, refreshAccessToken)
      return service.getSettings()
    },
    { immediate: false }
  )

  const update = useApiMutation<UpdateSettingsRequest, SystemSettingsResponse>(
    async (payload) => {
      if (!token) throw new Error('No auth token available')
      const service = new SettingsService(token, refreshAccessToken)
      return service.updateSettings(payload)
    }
  )

  return {
    get,
    update,
  }
}
