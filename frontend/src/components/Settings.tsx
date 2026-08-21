import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useSettingsService } from '@/hooks/useSettingsService'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/components/ui/toast'
import type { ProviderOption, UpdateSettingsRequest } from '@/types/settings'

function overrideLabel(isDbOverride: boolean): string {
  return isDbOverride ? 'Overridden' : 'Env default'
}

/** A retention window as held in form state. Empty string means the admin
 * cleared the field, which saves as null (fall back to the env default).
 */
type RetentionInput = string

function toRetentionPayloadValue(value: RetentionInput): number | null {
  return value === '' ? null : Number(value)
}

/** One retention window that the admin is shortening, for the confirmation
 * dialog to describe.
 */
interface ShortenedWindow {
  label: string
  unit: string
  from: number
  to: number
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
  const [conversationRetentionHours, setConversationRetentionHours] = useState<RetentionInput>('')
  const [cleanupOnLogout, setCleanupOnLogout] = useState(true)
  const [knowledgeBasePurgeDays, setKnowledgeBasePurgeDays] = useState<RetentionInput>('')
  const [apiKeyPurgeDays, setApiKeyPurgeDays] = useState<RetentionInput>('')

  // Set when a save is paused awaiting confirmation of a shortened window.
  // Shortening irreversibly deletes data belonging to users other than the
  // admin making the change, so it must never be a one-click action.
  const [pendingShortenedWindows, setPendingShortenedWindows] = useState<ShortenedWindow[] | null>(
    null
  )

  // Fields the admin has explicitly reset to their env-var default. Cleared
  // whenever the field is edited again, and sent as `null` in the save
  // payload instead of the (now-stale) string state.
  const [clearedFields, setClearedFields] = useState<Set<keyof UpdateSettingsRequest>>(
    new Set()
  )

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
    setConversationRetentionHours(String(get.data.conversation_retention_hours ?? ''))
    setCleanupOnLogout(get.data.cleanup_on_logout)
    setKnowledgeBasePurgeDays(String(get.data.knowledge_base_purge_days ?? ''))
    setApiKeyPurgeDays(String(get.data.api_key_purge_days ?? ''))
    setClearedFields(new Set())
  }, [get.data])

  function applyProviderSelection(
    options: ProviderOption[],
    provider: string,
    setUrl: (url: string) => void,
    setModel: (model: string) => void
  ) {
    const selected = options.find((option) => option.provider === provider)
    if (selected) {
      setUrl(selected.url)
      // The old provider's model name is meaningless for the new provider
      // (available_providers carries no per-provider model), so it must not
      // carry over — otherwise a stale model could be silently saved.
      setModel('')
    }
  }

  function markFieldCleared(field: keyof UpdateSettingsRequest) {
    setClearedFields((prev) => new Set(prev).add(field))
  }

  function markFieldEdited(field: keyof UpdateSettingsRequest) {
    setClearedFields((prev) => {
      if (!prev.has(field)) return prev
      const next = new Set(prev)
      next.delete(field)
      return next
    })
  }

  function buildPayload(): UpdateSettingsRequest {
    return {
      llm_provider: clearedFields.has('llm_provider') ? null : llmProvider,
      llm_url: clearedFields.has('llm_url') ? null : llmUrl,
      llm_model: clearedFields.has('llm_model') ? null : llmModel,
      embedding_provider: clearedFields.has('embedding_provider') ? null : embeddingProvider,
      embedding_url: clearedFields.has('embedding_url') ? null : embeddingUrl,
      embedding_model: clearedFields.has('embedding_model') ? null : embeddingModel,
      conversation_retention_hours: clearedFields.has('conversation_retention_hours')
        ? null
        : toRetentionPayloadValue(conversationRetentionHours),
      cleanup_on_logout: cleanupOnLogout,
      knowledge_base_purge_days: clearedFields.has('knowledge_base_purge_days')
        ? null
        : toRetentionPayloadValue(knowledgeBasePurgeDays),
      api_key_purge_days: clearedFields.has('api_key_purge_days')
        ? null
        : toRetentionPayloadValue(apiKeyPurgeDays),
    }
  }

  /** Which retention windows this save would shorten, relative to what is
   * currently in effect. Only shortening destroys data, so lengthening a
   * window (or clearing it back to the env default) needs no confirmation.
   */
  function shortenedWindows(payload: UpdateSettingsRequest): ShortenedWindow[] {
    if (!get.data) return []

    const candidates: { label: string; unit: string; current: number | null; next: number | null }[] =
      [
        {
          label: 'Conversation history',
          unit: 'hours',
          current: get.data.conversation_retention_hours,
          next: payload.conversation_retention_hours ?? null,
        },
        {
          label: 'Deleted documents',
          unit: 'days',
          current: get.data.knowledge_base_purge_days,
          next: payload.knowledge_base_purge_days ?? null,
        },
        {
          label: 'Revoked API keys',
          unit: 'days',
          current: get.data.api_key_purge_days,
          next: payload.api_key_purge_days ?? null,
        },
      ]

    return candidates
      .filter((c) => c.current !== null && c.next !== null && c.next < c.current)
      .map((c) => ({
        label: c.label,
        unit: c.unit,
        from: c.current as number,
        to: c.next as number,
      }))
  }

  async function save(payload: UpdateSettingsRequest) {
    try {
      await update.mutateAsync(payload)
      addToast('Settings saved', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save settings'
      addToast(message, 'error')
    }
  }

  async function handleSave() {
    const payload = buildPayload()
    const shortened = shortenedWindows(payload)

    if (shortened.length > 0) {
      setPendingShortenedWindows(shortened)
      return
    }

    await save(payload)
  }

  async function handleConfirmShortenedWindows() {
    setPendingShortenedWindows(null)
    await save(buildPayload())
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
  const llmShowAdvanced = Boolean(
    llmOptions.find((o) => o.provider === llmProvider)?.requires_manual_entry
  )
  const embeddingShowAdvanced = Boolean(
    embeddingOptions.find((o) => o.provider === embeddingProvider)?.requires_manual_entry
  )

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
              applyProviderSelection(llmOptions, value, setLlmUrl, setLlmModel)
              markFieldEdited('llm_url')
              markFieldEdited('llm_model')
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
              onChange={(e) => {
                setLlmUrl(e.target.value)
                markFieldEdited('llm_url')
              }}
              placeholder="http://localhost:8000/v1"
            />
            <label className="text-sm font-medium" htmlFor="llm-model">
              Custom Model
            </label>
            <Input
              id="llm-model"
              value={llmModel}
              onChange={(e) => {
                setLlmModel(e.target.value)
                markFieldEdited('llm_model')
              }}
              placeholder="model name"
            />
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-sm"
              onClick={() => {
                setLlmUrl('')
                setLlmModel('')
                markFieldCleared('llm_url')
                markFieldCleared('llm_model')
              }}
            >
              Reset to default
            </Button>
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
              applyProviderSelection(embeddingOptions, value, setEmbeddingUrl, setEmbeddingModel)
              markFieldEdited('embedding_url')
              markFieldEdited('embedding_model')
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
              onChange={(e) => {
                setEmbeddingUrl(e.target.value)
                markFieldEdited('embedding_url')
              }}
              placeholder="http://localhost:8002/v1"
            />
            <label className="text-sm font-medium" htmlFor="embedding-model">
              Custom Model
            </label>
            <Input
              id="embedding-model"
              value={embeddingModel}
              onChange={(e) => {
                setEmbeddingModel(e.target.value)
                markFieldEdited('embedding_model')
              }}
              placeholder="model name"
            />
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-sm"
              onClick={() => {
                setEmbeddingUrl('')
                setEmbeddingModel('')
                markFieldCleared('embedding_url')
                markFieldCleared('embedding_model')
              }}
            >
              Reset to default
            </Button>
          </div>
        )}
      </div>

      <section
        className="space-y-4 rounded-lg border border-border p-4"
        aria-label="Data retention"
      >
        <h3 className="text-lg font-semibold">Data Retention</h3>
        <p className="text-sm text-muted-foreground">
          How long each store is kept before it is permanently deleted. Shortening a window
          deletes data belonging to all users, not just yours. Audit records are never deleted
          by retention.
        </p>

        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="conversation-retention-hours">
            Conversation history (hours) (
            {overrideLabel(get.data.conversation_retention_hours_is_db_override)})
          </label>
          <Input
            id="conversation-retention-hours"
            type="number"
            min={0}
            value={conversationRetentionHours}
            onChange={(e) => {
              setConversationRetentionHours(e.target.value)
              markFieldEdited('conversation_retention_hours')
            }}
            placeholder="Leave empty to keep forever"
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="knowledge-base-purge-days">
            Deleted documents (days) (
            {overrideLabel(get.data.knowledge_base_purge_days_is_db_override)})
          </label>
          <Input
            id="knowledge-base-purge-days"
            type="number"
            min={0}
            value={knowledgeBasePurgeDays}
            onChange={(e) => {
              setKnowledgeBasePurgeDays(e.target.value)
              markFieldEdited('knowledge_base_purge_days')
            }}
            placeholder="Leave empty to keep forever"
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="api-key-purge-days">
            Revoked API keys (days) ({overrideLabel(get.data.api_key_purge_days_is_db_override)})
          </label>
          <Input
            id="api-key-purge-days"
            type="number"
            min={0}
            value={apiKeyPurgeDays}
            onChange={(e) => {
              setApiKeyPurgeDays(e.target.value)
              markFieldEdited('api_key_purge_days')
            }}
            placeholder="Leave empty to keep forever"
          />
        </div>

        <div className="flex items-center gap-2">
          <input
            id="cleanup-on-logout"
            type="checkbox"
            checked={cleanupOnLogout}
            onChange={(e) => setCleanupOnLogout(e.target.checked)}
          />
          <label className="text-sm font-medium" htmlFor="cleanup-on-logout">
            Purge conversations on logout (
            {overrideLabel(get.data.cleanup_on_logout_is_db_override)})
          </label>
        </div>

        <Button
          type="button"
          variant="link"
          className="h-auto p-0 text-sm"
          onClick={() => {
            setConversationRetentionHours('')
            setKnowledgeBasePurgeDays('')
            setApiKeyPurgeDays('')
            markFieldCleared('conversation_retention_hours')
            markFieldCleared('knowledge_base_purge_days')
            markFieldCleared('api_key_purge_days')
          }}
        >
          Reset retention to default
        </Button>
      </section>

      <Button onClick={handleSave} disabled={update.isPending}>
        {update.isPending ? 'Saving...' : 'Save'}
      </Button>

      <AlertDialog
        open={pendingShortenedWindows !== null}
        onOpenChange={(open) => {
          if (!open) setPendingShortenedWindows(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Shorten retention window?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>
                  Data outside the new window will be permanently deleted on the next retention
                  sweep, for all users — not only your own. This cannot be undone.
                </p>
                <ul className="list-disc pl-5">
                  {(pendingShortenedWindows ?? []).map((window) => (
                    <li key={window.label}>
                      {window.label}: {window.from} {window.unit} → {window.to} {window.unit}
                    </li>
                  ))}
                </ul>
                <p>This change will be recorded in the audit log.</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmShortenedWindows}>
              Shorten and delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
