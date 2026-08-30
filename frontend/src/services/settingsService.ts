import { settingsClient } from '@/api/settingsClient'
import type { AuthRefresh } from '@/api/authorizedFetch'
import type {
  GuardrailPattern,
  SystemSettingsResponse,
  UpdateSettingsRequest,
} from '@/types/settings'

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

  async createGuardrailPattern(label: string, patternText: string): Promise<GuardrailPattern> {
    if (!this.token) throw new Error('No auth token available')
    return settingsClient.createGuardrailPattern(this.token, this.onRefresh, label, patternText)
  }

  async setGuardrailPatternEnabled(id: string, enabled: boolean): Promise<GuardrailPattern> {
    if (!this.token) throw new Error('No auth token available')
    return settingsClient.setGuardrailPatternEnabled(this.token, this.onRefresh, id, enabled)
  }

  async deleteGuardrailPattern(id: string): Promise<void> {
    if (!this.token) throw new Error('No auth token available')
    return settingsClient.deleteGuardrailPattern(this.token, this.onRefresh, id)
  }
}
