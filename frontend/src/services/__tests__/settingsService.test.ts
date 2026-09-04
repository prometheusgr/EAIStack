import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MockedFunction } from 'vitest'
import type { AuthRefresh } from '@/api/authorizedFetch'
import { SettingsService } from '../settingsService'
import { settingsClient } from '@/api/settingsClient'

vi.mock('@/api/settingsClient', () => ({
  settingsClient: {
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
    getAuditLog: vi.fn(),
    getDashboard: vi.fn(),
    createGuardrailPattern: vi.fn(),
    setGuardrailPatternEnabled: vi.fn(),
    deleteGuardrailPattern: vi.fn(),
  },
}))

describe('SettingsService', () => {
  const mockToken = 'valid_token'
  let mockRefresh: MockedFunction<AuthRefresh>

  const settingsResponse = {
    llm_provider: 'fake',
    llm_url: '',
    llm_model: '',
    llm_provider_is_db_override: false,
    llm_url_is_db_override: false,
    llm_model_is_db_override: false,
    embedding_provider: 'fake',
    embedding_url: '',
    embedding_model: '',
    embedding_provider_is_db_override: false,
    embedding_url_is_db_override: false,
    embedding_model_is_db_override: false,
    conversation_retention_hours: 24,
    conversation_retention_hours_is_db_override: false,
    cleanup_on_logout: true,
    cleanup_on_logout_is_db_override: false,
    knowledge_base_purge_days: 30,
    knowledge_base_purge_days_is_db_override: false,
    api_key_purge_days: 30,
    api_key_purge_days_is_db_override: false,
    max_input_length: 4000,
    max_input_length_is_db_override: false,
    guardrails_input_enabled: true,
    guardrails_input_enabled_is_db_override: false,
    guardrails_output_enabled: true,
    guardrails_output_enabled_is_db_override: false,
    tracing_enabled: false,
    tracing_enabled_is_db_override: false,
    rate_limit_enabled: true,
    rate_limit_enabled_is_db_override: false,
    rate_limit_chat_capacity: 10,
    rate_limit_chat_capacity_is_db_override: false,
    rate_limit_chat_refill_per_minute: 10,
    rate_limit_chat_refill_per_minute_is_db_override: false,
    rate_limit_auth_capacity: 10,
    rate_limit_auth_capacity_is_db_override: false,
    rate_limit_auth_refill_per_minute: 10,
    rate_limit_auth_refill_per_minute_is_db_override: false,
    audit_log_ui_enabled: true,
    audit_log_ui_enabled_is_db_override: false,
    guardrail_patterns: [],
    available_providers: { llm: [], embedding: [] },
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockRefresh = vi.fn() as MockedFunction<AuthRefresh>
  })

  describe('getSettings', () => {
    it('delegates to settingsClient.getSettings with the constructor token', async () => {
      vi.mocked(settingsClient.getSettings).mockResolvedValueOnce(settingsResponse)

      const service = new SettingsService(mockToken, mockRefresh)
      const result = await service.getSettings()

      expect(settingsClient.getSettings).toHaveBeenCalledWith(mockToken, mockRefresh)
      expect(result).toEqual(settingsResponse)
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.getSettings()).rejects.toThrow('No auth token available')
      expect(settingsClient.getSettings).not.toHaveBeenCalled()
    })
  })

  describe('updateSettings', () => {
    it('delegates to settingsClient.updateSettings with the constructor token and payload', async () => {
      const updatedResponse = { ...settingsResponse, llm_provider: 'llama-cpp' }
      vi.mocked(settingsClient.updateSettings).mockResolvedValueOnce(updatedResponse)

      const payload = { llm_provider: 'llama-cpp' }
      const service = new SettingsService(mockToken, mockRefresh)
      const result = await service.updateSettings(payload)

      expect(settingsClient.updateSettings).toHaveBeenCalledWith(payload, mockToken, mockRefresh)
      expect(result.llm_provider).toBe('llama-cpp')
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.updateSettings({ llm_provider: 'fake' })).rejects.toThrow(
        'No auth token available'
      )
      expect(settingsClient.updateSettings).not.toHaveBeenCalled()
    })
  })

  describe('getAuditLog', () => {
    const auditLogResponse = {
      entries: [
        {
          id: 'entry-1',
          actor_user_id: 'admin-1',
          action: 'retention.update',
          field_name: 'conversation_retention_hours',
          old_value: '72',
          new_value: '24',
          created_at: '2026-09-02T00:00:00Z',
        },
      ],
    }

    it('delegates to settingsClient.getAuditLog with the constructor token', async () => {
      vi.mocked(settingsClient.getAuditLog).mockResolvedValueOnce(auditLogResponse)

      const service = new SettingsService(mockToken, mockRefresh)
      const result = await service.getAuditLog()

      expect(settingsClient.getAuditLog).toHaveBeenCalledWith(mockToken, mockRefresh)
      expect(result).toEqual(auditLogResponse)
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.getAuditLog()).rejects.toThrow('No auth token available')
      expect(settingsClient.getAuditLog).not.toHaveBeenCalled()
    })
  })

  describe('getDashboard', () => {
    const dashboardResponse = {
      rate_limit: { enabled: true, active_bucket_count: 2 },
      guardrails: {
        input_rejected_counts_by_pattern: { sql_injection: 1 },
        output_redacted_count: 0,
      },
      tracing: {
        db_desired_enabled: false,
        process_actually_configured: false,
        phoenix_ui_url: 'http://localhost:6006',
      },
      keycloak_console_url: 'http://localhost:8080',
    }

    it('delegates to settingsClient.getDashboard with the constructor token', async () => {
      vi.mocked(settingsClient.getDashboard).mockResolvedValueOnce(dashboardResponse)

      const service = new SettingsService(mockToken, mockRefresh)
      const result = await service.getDashboard()

      expect(settingsClient.getDashboard).toHaveBeenCalledWith(mockToken, mockRefresh)
      expect(result).toEqual(dashboardResponse)
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.getDashboard()).rejects.toThrow('No auth token available')
      expect(settingsClient.getDashboard).not.toHaveBeenCalled()
    })
  })

  describe('createGuardrailPattern', () => {
    const createdPattern = {
      id: 'pattern-1',
      source: 'custom' as const,
      label: 'Block foo',
      pattern_text: 'foo bar',
      enabled: true,
    }

    it('delegates to settingsClient.createGuardrailPattern with the constructor token', async () => {
      vi.mocked(settingsClient.createGuardrailPattern).mockResolvedValueOnce(createdPattern)

      const service = new SettingsService(mockToken, mockRefresh)
      const result = await service.createGuardrailPattern('Block foo', 'foo bar')

      expect(settingsClient.createGuardrailPattern).toHaveBeenCalledWith(
        mockToken,
        mockRefresh,
        'Block foo',
        'foo bar'
      )
      expect(result).toEqual(createdPattern)
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.createGuardrailPattern('Block foo', 'foo bar')).rejects.toThrow(
        'No auth token available'
      )
      expect(settingsClient.createGuardrailPattern).not.toHaveBeenCalled()
    })
  })

  describe('setGuardrailPatternEnabled', () => {
    const updatedPattern = {
      id: 'pattern-1',
      source: 'built_in' as const,
      label: 'SQL injection',
      pattern_text: null,
      enabled: false,
    }

    it('delegates to settingsClient.setGuardrailPatternEnabled with the constructor token', async () => {
      vi.mocked(settingsClient.setGuardrailPatternEnabled).mockResolvedValueOnce(updatedPattern)

      const service = new SettingsService(mockToken, mockRefresh)
      const result = await service.setGuardrailPatternEnabled('pattern-1', false)

      expect(settingsClient.setGuardrailPatternEnabled).toHaveBeenCalledWith(
        mockToken,
        mockRefresh,
        'pattern-1',
        false
      )
      expect(result).toEqual(updatedPattern)
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.setGuardrailPatternEnabled('pattern-1', false)).rejects.toThrow(
        'No auth token available'
      )
      expect(settingsClient.setGuardrailPatternEnabled).not.toHaveBeenCalled()
    })
  })

  describe('deleteGuardrailPattern', () => {
    it('delegates to settingsClient.deleteGuardrailPattern with the constructor token', async () => {
      vi.mocked(settingsClient.deleteGuardrailPattern).mockResolvedValueOnce(undefined)

      const service = new SettingsService(mockToken, mockRefresh)
      await service.deleteGuardrailPattern('pattern-1')

      expect(settingsClient.deleteGuardrailPattern).toHaveBeenCalledWith(
        mockToken,
        mockRefresh,
        'pattern-1'
      )
    })

    it('throws if no token is available', async () => {
      const service = new SettingsService('', mockRefresh)

      await expect(service.deleteGuardrailPattern('pattern-1')).rejects.toThrow(
        'No auth token available'
      )
      expect(settingsClient.deleteGuardrailPattern).not.toHaveBeenCalled()
    })
  })
})
