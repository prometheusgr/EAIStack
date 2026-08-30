export interface ProviderOption {
  provider: string
  url: string
  label: string
  requires_manual_entry: boolean
}

export interface GuardrailPattern {
  id: string
  source: 'built_in' | 'custom'
  label: string
  pattern_text: string | null
  enabled: boolean
}

export interface SystemSettingsResponse {
  llm_provider: string
  llm_url: string
  llm_model: string
  llm_provider_is_db_override: boolean
  llm_url_is_db_override: boolean
  llm_model_is_db_override: boolean
  embedding_provider: string
  embedding_url: string
  embedding_model: string
  embedding_provider_is_db_override: boolean
  embedding_url_is_db_override: boolean
  embedding_model_is_db_override: boolean
  conversation_retention_hours: number | null
  conversation_retention_hours_is_db_override: boolean
  cleanup_on_logout: boolean
  cleanup_on_logout_is_db_override: boolean
  knowledge_base_purge_days: number | null
  knowledge_base_purge_days_is_db_override: boolean
  api_key_purge_days: number | null
  api_key_purge_days_is_db_override: boolean
  max_input_length: number
  max_input_length_is_db_override: boolean
  guardrails_input_enabled: boolean
  guardrails_input_enabled_is_db_override: boolean
  guardrails_output_enabled: boolean
  guardrails_output_enabled_is_db_override: boolean
  guardrail_patterns: GuardrailPattern[]
  available_providers: {
    llm: ProviderOption[]
    embedding: ProviderOption[]
  }
}

export interface UpdateSettingsRequest {
  llm_provider?: string | null
  llm_url?: string | null
  llm_model?: string | null
  embedding_provider?: string | null
  embedding_url?: string | null
  embedding_model?: string | null
  conversation_retention_hours?: number | null
  cleanup_on_logout?: boolean | null
  knowledge_base_purge_days?: number | null
  api_key_purge_days?: number | null
  max_input_length?: number | null
  guardrails_input_enabled?: boolean | null
  guardrails_output_enabled?: boolean | null
}
