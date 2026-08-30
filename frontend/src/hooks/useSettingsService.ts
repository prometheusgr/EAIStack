import { useAuth } from '@/context/AuthContext'
import { SettingsService } from '@/services/settingsService'
import type { GuardrailPattern, SystemSettingsResponse, UpdateSettingsRequest } from '@/types/settings'
import { useApiCall } from './useApiCall'
import { useApiMutation } from './useApiMutation'

export interface CreateGuardrailPatternArgs {
  label: string
  patternText: string
}

export interface SetGuardrailPatternEnabledArgs {
  id: string
  enabled: boolean
}

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

  const createGuardrailPattern = useApiMutation<CreateGuardrailPatternArgs, GuardrailPattern>(
    async ({ label, patternText }) => {
      if (!token) throw new Error('No auth token available')
      const service = new SettingsService(token, refreshAccessToken)
      return service.createGuardrailPattern(label, patternText)
    }
  )

  const setGuardrailPatternEnabled = useApiMutation<
    SetGuardrailPatternEnabledArgs,
    GuardrailPattern
  >(async ({ id, enabled }) => {
    if (!token) throw new Error('No auth token available')
    const service = new SettingsService(token, refreshAccessToken)
    return service.setGuardrailPatternEnabled(id, enabled)
  })

  const deleteGuardrailPattern = useApiMutation<string, void>(async (id) => {
    if (!token) throw new Error('No auth token available')
    const service = new SettingsService(token, refreshAccessToken)
    return service.deleteGuardrailPattern(id)
  })

  return {
    get,
    update,
    createGuardrailPattern,
    setGuardrailPatternEnabled,
    deleteGuardrailPattern,
  }
}
