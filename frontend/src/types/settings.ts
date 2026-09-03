export interface ProviderOption {
  provider: string
  url: string
  label: string
  requires_manual_entry: boolean
}

export interface TestConnectionResult {
  ok: boolean
  models: string[]
  error: string | null
}

export interface GuardrailPattern {
  id: string
  source: 'built_in' | 'custom'
  label: string
  pattern_text: string | null
  enabled: boolean
}

export interface AuditLogEntry {
  id: string
  actor_user_id: string
  action: string
  field_name: string
  old_value: string | null
  new_value: string | null
  created_at: string
}

export interface AuditLogResponse {
  entries: AuditLogEntry[]
}

export interface RateLimitStatus {
  enabled: boolean
  active_bucket_count: number
}

export interface GuardrailStatus {
  input_rejected_counts_by_pattern: Record<string, number>
  output_redacted_count: number
}

export interface TracingStatus {
  db_desired_enabled: boolean
  process_actually_configured: boolean
  phoenix_ui_url: string
}

export interface DashboardResponse {
  rate_limit: RateLimitStatus
  guardrails: GuardrailStatus
  tracing: TracingStatus
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
  // LLM observability (issue #4). Unlike every other field above, a change
  // here requires a backend restart to take effect - it is resolved once
  // at process startup, not per-request.
  tracing_enabled: boolean
  tracing_enabled_is_db_override: boolean
  // Rate limiting (issue #25). Shares one on/off switch across both the
  // chat and auth-token buckets -- see docs/SECURITY.md's "Rate Limiting"
  // section for why that differs from the guardrails' separate switches.
  rate_limit_enabled: boolean
  rate_limit_enabled_is_db_override: boolean
  rate_limit_chat_capacity: number
  rate_limit_chat_capacity_is_db_override: boolean
  rate_limit_chat_refill_per_minute: number
  rate_limit_chat_refill_per_minute_is_db_override: boolean
  rate_limit_auth_capacity: number
  rate_limit_auth_capacity_is_db_override: boolean
  rate_limit_auth_refill_per_minute: number
  rate_limit_auth_refill_per_minute_is_db_override: boolean
  // Admin audit log viewer (issue #45). Transparent-by-default (true):
  // hides the in-product Audit Log nav entry/view for forks that route
  // audit consumption through an external SIEM instead.
  audit_log_ui_enabled: boolean
  audit_log_ui_enabled_is_db_override: boolean
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
  // See SystemSettingsResponse.tracing_enabled: takes effect on the next
  // backend restart, not the next request.
  tracing_enabled?: boolean | null
  rate_limit_enabled?: boolean | null
  rate_limit_chat_capacity?: number | null
  rate_limit_chat_refill_per_minute?: number | null
  rate_limit_auth_capacity?: number | null
  rate_limit_auth_refill_per_minute?: number | null
  // See SystemSettingsResponse.audit_log_ui_enabled: takes effect on the
  // next request, no restart required.
  audit_log_ui_enabled?: boolean | null
}
