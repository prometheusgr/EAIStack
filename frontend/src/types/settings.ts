export interface ProviderOption {
  provider: string
  url: string
  label: string
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
}
