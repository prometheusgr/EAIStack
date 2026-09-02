import { authorizedFetch, type AuthRefresh } from './authorizedFetch'
import type {
  AuditLogResponse,
  GuardrailPattern,
  SystemSettingsResponse,
  TestConnectionResult,
  UpdateSettingsRequest,
} from '@/types/settings'

export interface SettingsClient {
  getSettings(token: string, onRefresh: AuthRefresh): Promise<SystemSettingsResponse>
  updateSettings(
    payload: UpdateSettingsRequest,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<SystemSettingsResponse>
  getAuditLog(token: string, onRefresh: AuthRefresh): Promise<AuditLogResponse>
  testConnection(
    url: string,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<TestConnectionResult>
  createGuardrailPattern(
    token: string,
    onRefresh: AuthRefresh,
    label: string,
    patternText: string
  ): Promise<GuardrailPattern>
  setGuardrailPatternEnabled(
    token: string,
    onRefresh: AuthRefresh,
    id: string,
    enabled: boolean
  ): Promise<GuardrailPattern>
  deleteGuardrailPattern(token: string, onRefresh: AuthRefresh, id: string): Promise<void>
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

  async getAuditLog(token: string, onRefresh: AuthRefresh): Promise<AuditLogResponse> {
    const response = await authorizedFetch('/api/settings/audit', token, onRefresh, {
      method: 'GET',
    })

    return response.json()
  },

  async testConnection(
    url: string,
    token: string,
    onRefresh: AuthRefresh
  ): Promise<TestConnectionResult> {
    const response = await authorizedFetch('/api/settings/test-connection', token, onRefresh, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url }),
    })

    return response.json()
  },

  async createGuardrailPattern(
    token: string,
    onRefresh: AuthRefresh,
    label: string,
    patternText: string
  ): Promise<GuardrailPattern> {
    const response = await authorizedFetch(
      '/api/settings/guardrail-patterns',
      token,
      onRefresh,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ label, pattern_text: patternText }),
      }
    )

    return response.json()
  },

  async setGuardrailPatternEnabled(
    token: string,
    onRefresh: AuthRefresh,
    id: string,
    enabled: boolean
  ): Promise<GuardrailPattern> {
    const response = await authorizedFetch(
      `/api/settings/guardrail-patterns/${id}`,
      token,
      onRefresh,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ enabled }),
      }
    )

    return response.json()
  },

  async deleteGuardrailPattern(
    token: string,
    onRefresh: AuthRefresh,
    id: string
  ): Promise<void> {
    await authorizedFetch(`/api/settings/guardrail-patterns/${id}`, token, onRefresh, {
      method: 'DELETE',
    })
  },
}

export { settingsClient }
