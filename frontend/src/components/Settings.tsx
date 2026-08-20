import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useSettingsService } from '@/hooks/useSettingsService'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/components/ui/toast'
import type { ProviderOption, UpdateSettingsRequest } from '@/types/settings'

function overrideLabel(isDbOverride: boolean): string {
  return isDbOverride ? 'Overridden' : 'Env default'
}

/** Admin-only screen for viewing and changing the runtime LLM/embedding
 * provider config. Assumes it is only ever mounted for an admin user — the
 * mount point (App.tsx) is responsible for that gate; this component does
 * not check isAdmin itself.
 */
export function Settings() {
  const { isLoading: isAuthLoading } = useAuth()
  const { get, update } = useSettingsService()
  const { addToast } = useToast()

  const [llmProvider, setLlmProvider] = useState('')
  const [llmUrl, setLlmUrl] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [embeddingProvider, setEmbeddingProvider] = useState('')
  const [embeddingUrl, setEmbeddingUrl] = useState('')
  const [embeddingModel, setEmbeddingModel] = useState('')

  useEffect(() => {
    // Wait for AuthContext's async init to finish resolving the token
    // before the first fetch — firing earlier would hit the "no auth
    // token available" guard in useSettingsService.
    if (isAuthLoading) return
    get.execute()
  }, [isAuthLoading])

  useEffect(() => {
    if (!get.data) return
    setLlmProvider(get.data.llm_provider)
    setLlmUrl(get.data.llm_url)
    setLlmModel(get.data.llm_model)
    setEmbeddingProvider(get.data.embedding_provider)
    setEmbeddingUrl(get.data.embedding_url)
    setEmbeddingModel(get.data.embedding_model)
  }, [get.data])

  function applyProviderSelection(
    options: ProviderOption[],
    provider: string,
    setUrl: (url: string) => void
  ) {
    const selected = options.find((option) => option.provider === provider)
    if (selected) {
      setUrl(selected.url)
    }
  }

  async function handleSave() {
    const payload: UpdateSettingsRequest = {
      llm_provider: llmProvider,
      llm_url: llmUrl,
      llm_model: llmModel,
      embedding_provider: embeddingProvider,
      embedding_url: embeddingUrl,
      embedding_model: embeddingModel,
    }

    try {
      await update.mutateAsync(payload)
      addToast('Settings saved', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save settings'
      addToast(message, 'error')
    }
  }

  if (get.isLoading && !get.data) {
    return <div className="text-muted-foreground">Loading settings...</div>
  }

  if (get.error && !get.data) {
    return (
      <div className="p-4 bg-red-50 text-red-700 rounded border border-red-200" role="alert">
        {get.error.message}
      </div>
    )
  }

  if (!get.data) {
    return null
  }

  const llmOptions = get.data.available_providers.llm
  const embeddingOptions = get.data.available_providers.embedding
  const llmShowAdvanced = !llmOptions.find((o) => o.provider === llmProvider)?.url
  const embeddingShowAdvanced = !embeddingOptions.find((o) => o.provider === embeddingProvider)?.url

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Settings</h2>
        <p className="text-sm text-muted-foreground">
          Runtime LLM and embedding provider configuration. Changes take effect on the next
          chat or embedding call — no restart required.
        </p>
      </div>

      <div className="space-y-4 rounded-lg border border-border p-4">
        <h3 className="text-lg font-semibold">LLM Provider</h3>
        <p className="text-sm text-muted-foreground">
          Current: {get.data.llm_provider} ({overrideLabel(get.data.llm_provider_is_db_override)})
        </p>

        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="llm-provider-select">
            Provider
          </label>
          <Select
            value={llmProvider}
            onValueChange={(value) => {
              setLlmProvider(value)
              applyProviderSelection(llmOptions, value, setLlmUrl)
            }}
          >
            <SelectTrigger id="llm-provider-select" aria-label="LLM provider">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {llmOptions.map((option) => (
                <SelectItem key={option.provider} value={option.provider}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {llmShowAdvanced && (
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="llm-url">
              Custom URL
            </label>
            <Input
              id="llm-url"
              value={llmUrl}
              onChange={(e) => setLlmUrl(e.target.value)}
              placeholder="http://localhost:8000/v1"
            />
            <label className="text-sm font-medium" htmlFor="llm-model">
              Custom Model
            </label>
            <Input
              id="llm-model"
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
              placeholder="model name"
            />
          </div>
        )}
      </div>

      <div className="space-y-4 rounded-lg border border-border p-4">
        <h3 className="text-lg font-semibold">Embedding Provider</h3>
        <p className="text-sm text-muted-foreground">
          Current: {get.data.embedding_provider} (
          {overrideLabel(get.data.embedding_provider_is_db_override)})
        </p>

        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="embedding-provider-select">
            Provider
          </label>
          <Select
            value={embeddingProvider}
            onValueChange={(value) => {
              setEmbeddingProvider(value)
              applyProviderSelection(embeddingOptions, value, setEmbeddingUrl)
            }}
          >
            <SelectTrigger id="embedding-provider-select" aria-label="Embedding provider">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {embeddingOptions.map((option) => (
                <SelectItem key={option.provider} value={option.provider}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {embeddingShowAdvanced && (
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="embedding-url">
              Custom URL
            </label>
            <Input
              id="embedding-url"
              value={embeddingUrl}
              onChange={(e) => setEmbeddingUrl(e.target.value)}
              placeholder="http://localhost:8002/v1"
            />
            <label className="text-sm font-medium" htmlFor="embedding-model">
              Custom Model
            </label>
            <Input
              id="embedding-model"
              value={embeddingModel}
              onChange={(e) => setEmbeddingModel(e.target.value)}
              placeholder="model name"
            />
          </div>
        )}
      </div>

      <Button onClick={handleSave} disabled={update.isPending}>
        {update.isPending ? 'Saving...' : 'Save'}
      </Button>
    </div>
  )
}
