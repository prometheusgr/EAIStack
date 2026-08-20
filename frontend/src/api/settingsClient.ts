import { authorizedFetch, type AuthRefresh } from './authorizedFetch'
import type { SystemSettingsResponse, UpdateSettingsRequest } from '@/types/settings'

export interface SettingsClient {
  getSettings(token: string, onRefresh: AuthRefresh): Promise<SystemSettingsResponse>
  updateSettings(
    payload: UpdateSettingsRequest,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<SystemSettingsResponse>
}

const settingsClient: SettingsClient = {
  async getSettings(token: string, onRefresh: AuthRefresh): Promise<SystemSettingsResponse> {
    const response = await authorizedFetch('/api/settings', token, onRefresh, {
      method: 'GET',
    })

    return response.json()
  },

  async updateSettings(
    payload: UpdateSettingsRequest,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<SystemSettingsResponse> {
    const response = await authorizedFetch('/api/settings', token, onRefresh, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })

    return response.json()
  },
}

export { settingsClient }
