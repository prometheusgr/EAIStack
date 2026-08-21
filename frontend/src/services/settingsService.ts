import { settingsClient } from '@/api/settingsClient'
import type { AuthRefresh } from '@/api/authorizedFetch'
import type { SystemSettingsResponse, UpdateSettingsRequest } from '@/types/settings'

export class SettingsService {
  constructor(
    private token: string,
    private onRefresh: AuthRefresh
  ) {}

  async getSettings(): Promise<SystemSettingsResponse> {
    if (!this.token) throw new Error('No auth token available')
    return settingsClient.getSettings(this.token, this.onRefresh)
  }

  async updateSettings(payload: UpdateSettingsRequest): Promise<SystemSettingsResponse> {
    if (!this.token) throw new Error('No auth token available')
    return settingsClient.updateSettings(payload, this.token, this.onRefresh)
  }
}
