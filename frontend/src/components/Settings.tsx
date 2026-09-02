import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useIsMounted } from '@/hooks/useIsMounted'
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
import { InfoTooltip } from '@/components/ui/info-tooltip'
import type {
  GuardrailPattern,
  ProviderOption,
  TestConnectionResult,
  UpdateSettingsRequest,
} from '@/types/settings'

/** A numeric setting as held in form state. Empty string means the admin
 * cleared the field, which saves as null (fall back to the env default) --
 * same convention as RetentionInput, but max_input_length has no meaningful
 * "0" value (server validates it as >= 1), so there's no truthiness caveat.
 */
type NumericSettingInput = string

function toNumericSettingPayloadValue(value: NumericSettingInput): number | null {
  return value === '' ? null : Number(value)
}

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
  const {
    get,
    update,
    testConnection,
    createGuardrailPattern,
    setGuardrailPatternEnabled,
    deleteGuardrailPattern,
  } = useSettingsService()
  const { addToast } = useToast()
  const isMounted = useIsMounted()

  const [llmProvider, setLlmProvider] = useState('')
  const [llmUrl, setLlmUrl] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [embeddingProvider, setEmbeddingProvider] = useState('')
  const [embeddingUrl, setEmbeddingUrl] = useState('')
  const [embeddingModel, setEmbeddingModel] = useState('')
  // Result of the last "Test connection" click for each URL field, reset to
  // null whenever that URL is edited so a stale "Connected" badge never
  // survives a change to the field it was testing.
  const [llmTestResult, setLlmTestResult] = useState<TestConnectionResult | null>(null)
  const [embeddingTestResult, setEmbeddingTestResult] = useState<TestConnectionResult | null>(
    null
  )
  const [conversationRetentionHours, setConversationRetentionHours] = useState<RetentionInput>('')
  const [cleanupOnLogout, setCleanupOnLogout] = useState(true)
  const [knowledgeBasePurgeDays, setKnowledgeBasePurgeDays] = useState<RetentionInput>('')
  const [apiKeyPurgeDays, setApiKeyPurgeDays] = useState<RetentionInput>('')
  const [maxInputLength, setMaxInputLength] = useState<NumericSettingInput>('')
  const [guardrailsInputEnabled, setGuardrailsInputEnabled] = useState(true)
  const [guardrailsOutputEnabled, setGuardrailsOutputEnabled] = useState(true)
  const [tracingEnabled, setTracingEnabled] = useState(false)
  const [rateLimitEnabled, setRateLimitEnabled] = useState(true)
  const [rateLimitChatCapacity, setRateLimitChatCapacity] = useState<NumericSettingInput>('')
  const [rateLimitChatRefillPerMinute, setRateLimitChatRefillPerMinute] =
    useState<NumericSettingInput>('')
  const [rateLimitAuthCapacity, setRateLimitAuthCapacity] = useState<NumericSettingInput>('')
  const [rateLimitAuthRefillPerMinute, setRateLimitAuthRefillPerMinute] =
    useState<NumericSettingInput>('')
  const [newPatternLabel, setNewPatternLabel] = useState('')
  const [newPatternPhrase, setNewPatternPhrase] = useState('')
  // Mirrors get.data.guardrail_patterns locally, patched in place by each
  // pattern mutation's own response (see handleTogglePattern/handleAddPattern/
  // handleDeletePattern below) rather than re-fetched via get.execute(): a
  // refetch briefly sets get.data back to null while in flight (see
  // useApiCall), and this component's own `if (!get.data) return null` guard
  // would unmount the whole settings form for that instant -- including
  // whatever a test or user was mid-interaction with (e.g. a checkbox click),
  // which is both a jarring flicker and breaks Playwright's post-click state
  // re-verification. Patching this array locally from the mutation's return
  // value (each pattern endpoint returns the affected GuardrailPattern) is
  // both cheaper and avoids that unmount entirely.
  const [guardrailPatterns, setGuardrailPatterns] = useState<GuardrailPattern[]>([])

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
    setMaxInputLength(String(get.data.max_input_length))
    setGuardrailsInputEnabled(get.data.guardrails_input_enabled)
    setGuardrailsOutputEnabled(get.data.guardrails_output_enabled)
    setGuardrailPatterns(get.data.guardrail_patterns)
    setTracingEnabled(get.data.tracing_enabled)
    setRateLimitEnabled(get.data.rate_limit_enabled)
    setRateLimitChatCapacity(String(get.data.rate_limit_chat_capacity))
    setRateLimitChatRefillPerMinute(String(get.data.rate_limit_chat_refill_per_minute))
    setRateLimitAuthCapacity(String(get.data.rate_limit_auth_capacity))
    setRateLimitAuthRefillPerMinute(String(get.data.rate_limit_auth_refill_per_minute))
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

  async function handleTestConnection(
    url: string,
    setResult: (result: TestConnectionResult | null) => void
  ) {
    // A failed probe's reason is shown inline next to the button (see
    // llmTestResult/embeddingTestResult rendering below), not as a toast --
    // it's a diagnostic result the admin is likely to read right there
    // while still editing the field, not a transient event. A toast is
    // still used for a genuine request failure (network/auth error talking
    // to our own backend), which the inline result has no way to represent.
    try {
      const result = await testConnection.mutateAsync(url)
      if (isMounted()) setResult(result)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to test connection'
      addToast(message, 'error')
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
      cleanup_on_logout: clearedFields.has('cleanup_on_logout') ? null : cleanupOnLogout,
      knowledge_base_purge_days: clearedFields.has('knowledge_base_purge_days')
        ? null
        : toRetentionPayloadValue(knowledgeBasePurgeDays),
      api_key_purge_days: clearedFields.has('api_key_purge_days')
        ? null
        : toRetentionPayloadValue(apiKeyPurgeDays),
      max_input_length: clearedFields.has('max_input_length')
        ? null
        : toNumericSettingPayloadValue(maxInputLength),
      guardrails_input_enabled: clearedFields.has('guardrails_input_enabled')
        ? null
        : guardrailsInputEnabled,
      guardrails_output_enabled: clearedFields.has('guardrails_output_enabled')
        ? null
        : guardrailsOutputEnabled,
      tracing_enabled: clearedFields.has('tracing_enabled') ? null : tracingEnabled,
      rate_limit_enabled: clearedFields.has('rate_limit_enabled') ? null : rateLimitEnabled,
      rate_limit_chat_capacity: clearedFields.has('rate_limit_chat_capacity')
        ? null
        : toNumericSettingPayloadValue(rateLimitChatCapacity),
      rate_limit_chat_refill_per_minute: clearedFields.has('rate_limit_chat_refill_per_minute')
        ? null
        : toNumericSettingPayloadValue(rateLimitChatRefillPerMinute),
      rate_limit_auth_capacity: clearedFields.has('rate_limit_auth_capacity')
        ? null
        : toNumericSettingPayloadValue(rateLimitAuthCapacity),
      rate_limit_auth_refill_per_minute: clearedFields.has('rate_limit_auth_refill_per_minute')
        ? null
        : toNumericSettingPayloadValue(rateLimitAuthRefillPerMinute),
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

  // Each pattern mutation hits its own endpoint immediately (unlike the main
  // settings form, which batches edits into one PUT via the Save button) --
  // see the plan for issue #16. Each endpoint's response carries the single
  // affected GuardrailPattern, which is enough to patch guardrailPatterns
  // locally -- no need to re-fetch the whole settings payload (see that
  // state's own comment for why a get.execute() refetch is the wrong tool
  // here).
  async function handleTogglePattern(id: string, enabled: boolean) {
    try {
      const updated = await setGuardrailPatternEnabled.mutateAsync({ id, enabled })
      if (isMounted()) {
        setGuardrailPatterns((prev) => prev.map((p) => (p.id === id ? updated : p)))
      }
      addToast('Pattern updated', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update pattern'
      addToast(message, 'error')
    }
  }

  async function handleAddPattern() {
    try {
      const created = await createGuardrailPattern.mutateAsync({
        label: newPatternLabel,
        patternText: newPatternPhrase,
      })
      if (isMounted()) {
        setGuardrailPatterns((prev) => [...prev, created])
        setNewPatternLabel('')
        setNewPatternPhrase('')
      }
      addToast('Pattern added', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add pattern'
      addToast(message, 'error')
    }
  }

  async function handleDeletePattern(id: string) {
    try {
      await deleteGuardrailPattern.mutateAsync(id)
      if (isMounted()) {
        setGuardrailPatterns((prev) => prev.filter((p) => p.id !== id))
      }
      addToast('Pattern deleted', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete pattern'
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

      <section
        className="space-y-2 rounded-lg border border-border bg-muted/50 p-4 text-sm"
        aria-label="Common setups"
      >
        <h3 className="font-semibold">Common setups</h3>
        <p className="text-muted-foreground">
          Hover the (i) next to any field below for what it does. A few starting points:
        </p>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>
            <span className="font-medium text-foreground">Privacy-sensitive</span>: conversation
            history 24 hours, purge on logout on, deleted documents 7 days.
          </li>
          <li>
            <span className="font-medium text-foreground">General-purpose</span>: conversation
            history 720 hours (30 days), purge on logout off, deleted documents 30 days —
            the defaults most fields already start at.
          </li>
          <li>
            <span className="font-medium text-foreground">Exposed to untrusted users</span>: keep
            both guardrails on, keep rate limiting on, and consider lowering the chat burst
            capacity below its default of 10.
          </li>
        </ul>
      </section>

      <section
        className="space-y-4 rounded-lg border border-border p-4"
        aria-label="LLM configuration"
      >
        <h3 className="text-lg font-semibold">LLM Provider</h3>
        <p className="text-sm text-muted-foreground">
          Current: {get.data.llm_provider} ({overrideLabel(get.data.llm_provider_is_db_override)})
        </p>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="llm-provider-select">
              Provider
            </label>
            <InfoTooltip>
              Which service generates chat responses. &quot;Fake&quot; returns
              canned responses for testing and requires no running model.
              &quot;llama-cpp&quot; talks to a local llama-server instance
              (the default self-hosted path). &quot;OpenAI-compatible&quot;
              works with any service that implements the OpenAI chat
              completions API, including a remote-hosted one.
            </InfoTooltip>
          </div>
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
            <div className="flex items-center gap-2">
              <Input
                id="llm-url"
                value={llmUrl}
                onChange={(e) => {
                  setLlmUrl(e.target.value)
                  markFieldEdited('llm_url')
                  setLlmTestResult(null)
                }}
                placeholder="http://localhost:8000/v1"
              />
              <Button
                type="button"
                variant="outline"
                className="shrink-0"
                disabled={llmUrl === '' || testConnection.isPending}
                onClick={() => handleTestConnection(llmUrl, setLlmTestResult)}
              >
                {testConnection.isPending ? 'Testing...' : 'Test connection'}
              </Button>
            </div>
            {llmTestResult?.ok && (
              <p className="text-sm text-green-700">
                Connected — {llmTestResult.models.length}{' '}
                {llmTestResult.models.length === 1 ? 'model' : 'models'} found
              </p>
            )}
            {llmTestResult && !llmTestResult.ok && (
              <p className="text-sm text-red-700">{llmTestResult.error}</p>
            )}

            <label className="text-sm font-medium" htmlFor="llm-model">
              Custom Model
            </label>
            {llmTestResult?.ok && llmTestResult.models.length > 0 ? (
              <Select
                value={llmModel}
                onValueChange={(value) => {
                  setLlmModel(value)
                  markFieldEdited('llm_model')
                }}
              >
                <SelectTrigger id="llm-model" aria-label="LLM model">
                  <SelectValue placeholder="Select a model" />
                </SelectTrigger>
                <SelectContent>
                  {llmTestResult.models.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                id="llm-model"
                value={llmModel}
                onChange={(e) => {
                  setLlmModel(e.target.value)
                  markFieldEdited('llm_model')
                }}
                placeholder="model name"
              />
            )}
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-sm"
              onClick={() => {
                setLlmUrl('')
                setLlmModel('')
                markFieldCleared('llm_url')
                markFieldCleared('llm_model')
                setLlmTestResult(null)
              }}
            >
              Reset to default
            </Button>
          </div>
        )}
      </section>

      <section
        className="space-y-4 rounded-lg border border-border p-4"
        aria-label="Embedding configuration"
      >
        <h3 className="text-lg font-semibold">Embedding Provider</h3>
        <p className="text-sm text-muted-foreground">
          Current: {get.data.embedding_provider} (
          {overrideLabel(get.data.embedding_provider_is_db_override)})
        </p>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="embedding-provider-select">
              Provider
            </label>
            <InfoTooltip>
              Which service converts text into vectors for knowledge-base
              search. Must produce vectors of a consistent dimension and
              model across every document already indexed — switching
              providers on a knowledge base that already has documents will
              make new searches inconsistent with old embeddings until it is
              re-indexed.
            </InfoTooltip>
          </div>
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
            <div className="flex items-center gap-2">
              <Input
                id="embedding-url"
                value={embeddingUrl}
                onChange={(e) => {
                  setEmbeddingUrl(e.target.value)
                  markFieldEdited('embedding_url')
                  setEmbeddingTestResult(null)
                }}
                placeholder="http://localhost:8002/v1"
              />
              <Button
                type="button"
                variant="outline"
                className="shrink-0"
                disabled={embeddingUrl === '' || testConnection.isPending}
                onClick={() => handleTestConnection(embeddingUrl, setEmbeddingTestResult)}
              >
                {testConnection.isPending ? 'Testing...' : 'Test connection'}
              </Button>
            </div>
            {embeddingTestResult?.ok && (
              <p className="text-sm text-green-700">
                Connected — {embeddingTestResult.models.length}{' '}
                {embeddingTestResult.models.length === 1 ? 'model' : 'models'} found
              </p>
            )}
            {embeddingTestResult && !embeddingTestResult.ok && (
              <p className="text-sm text-red-700">{embeddingTestResult.error}</p>
            )}

            <label className="text-sm font-medium" htmlFor="embedding-model">
              Custom Model
            </label>
            {embeddingTestResult?.ok && embeddingTestResult.models.length > 0 ? (
              <Select
                value={embeddingModel}
                onValueChange={(value) => {
                  setEmbeddingModel(value)
                  markFieldEdited('embedding_model')
                }}
              >
                <SelectTrigger id="embedding-model" aria-label="Embedding model">
                  <SelectValue placeholder="Select a model" />
                </SelectTrigger>
                <SelectContent>
                  {embeddingTestResult.models.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                id="embedding-model"
                value={embeddingModel}
                onChange={(e) => {
                  setEmbeddingModel(e.target.value)
                  markFieldEdited('embedding_model')
                }}
                placeholder="model name"
              />
            )}
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-sm"
              onClick={() => {
                setEmbeddingUrl('')
                setEmbeddingModel('')
                markFieldCleared('embedding_url')
                markFieldCleared('embedding_model')
                setEmbeddingTestResult(null)
              }}
            >
              Reset to default
            </Button>
          </div>
        )}
      </section>

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
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="conversation-retention-hours">
              Conversation history (hours) (
              {overrideLabel(get.data.conversation_retention_hours_is_db_override)})
            </label>
            <InfoTooltip>
              How long chat threads are kept before being permanently
              deleted. Leave empty to keep conversations forever. 0 purges
              immediately (on the next retention sweep, not the instant a
              conversation happens). Common setups: 24 hours for a
              privacy-sensitive deployment, 720 hours (30 days) for a
              general-purpose one.
            </InfoTooltip>
          </div>
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
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="knowledge-base-purge-days">
              Deleted documents (days) (
              {overrideLabel(get.data.knowledge_base_purge_days_is_db_override)})
            </label>
            <InfoTooltip>
              How long a knowledge-base document is kept in soft-deleted
              form, recoverable, after a user deletes it, before it is
              permanently purged. Leave empty to keep soft-deleted documents
              forever (never auto-purged). A common default is 30 days —
              long enough to recover an accidental deletion.
            </InfoTooltip>
          </div>
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
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="api-key-purge-days">
              Revoked API keys (days) ({overrideLabel(get.data.api_key_purge_days_is_db_override)})
            </label>
            <InfoTooltip>
              How long a revoked API key&apos;s record is kept before being
              permanently purged. Leave empty to keep revoked keys forever —
              useful if you need a historical record of who had access. A
              common default is 30 days.
            </InfoTooltip>
          </div>
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
            onChange={(e) => {
              setCleanupOnLogout(e.target.checked)
              markFieldEdited('cleanup_on_logout')
            }}
          />
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="cleanup-on-logout">
              Purge conversations on logout (
              {overrideLabel(get.data.cleanup_on_logout_is_db_override)})
            </label>
            <InfoTooltip>
              When enabled, a user&apos;s conversation history is deleted
              immediately when they log out, in addition to (not instead of)
              the retention window above. Enable for a shared-device or
              high-privacy deployment; leave off if users expect their chat
              history to still be there next time they log in.
            </InfoTooltip>
          </div>
        </div>

        <Button
          type="button"
          variant="link"
          className="h-auto p-0 text-sm"
          onClick={() => {
            setConversationRetentionHours('')
            setKnowledgeBasePurgeDays('')
            setApiKeyPurgeDays('')
            setCleanupOnLogout(true)
            markFieldCleared('conversation_retention_hours')
            markFieldCleared('knowledge_base_purge_days')
            markFieldCleared('api_key_purge_days')
            markFieldCleared('cleanup_on_logout')
          }}
        >
          Reset retention to default
        </Button>
      </section>

      <section className="space-y-4 rounded-lg border border-border p-4" aria-label="Guardrails">
        <h3 className="text-lg font-semibold">Guardrails</h3>
        <p className="text-sm text-muted-foreground">
          Thresholds and detection rules used to reject unsafe input and filter unsafe output
          before it reaches the model or the user.
        </p>

        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <input
              id="guardrails-input-enabled"
              type="checkbox"
              checked={guardrailsInputEnabled}
              onChange={(e) => {
                setGuardrailsInputEnabled(e.target.checked)
                markFieldEdited('guardrails_input_enabled')
              }}
            />
            <div className="flex items-center gap-1.5">
              <label className="text-sm font-medium" htmlFor="guardrails-input-enabled">
                Reject unsafe input (
                {overrideLabel(get.data.guardrails_input_enabled_is_db_override)})
              </label>
              <InfoTooltip>
                When enabled, a message matching a detection pattern below
                (e.g. a prompt-injection attempt) is rejected with an error
                before it reaches the LLM. Recommended on for any deployment
                exposed to untrusted users.
              </InfoTooltip>
            </div>
          </div>
          {get.data.guardrails_input_enabled && !guardrailsInputEnabled && (
            <p className="text-sm text-amber-600">
              Disabling this removes protection against unsafe input for all users until
              re-enabled.
            </p>
          )}
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <input
              id="guardrails-output-enabled"
              type="checkbox"
              checked={guardrailsOutputEnabled}
              onChange={(e) => {
                setGuardrailsOutputEnabled(e.target.checked)
                markFieldEdited('guardrails_output_enabled')
              }}
            />
            <div className="flex items-center gap-1.5">
              <label className="text-sm font-medium" htmlFor="guardrails-output-enabled">
                Filter unsafe output (
                {overrideLabel(get.data.guardrails_output_enabled_is_db_override)})
              </label>
              <InfoTooltip>
                When enabled, the LLM&apos;s response is sanitized before it
                reaches the user, rather than rejected outright — unlike
                input rejection, this guardrail trips silently from the
                user&apos;s point of view. Recommended on alongside input
                rejection.
              </InfoTooltip>
            </div>
          </div>
          {get.data.guardrails_output_enabled && !guardrailsOutputEnabled && (
            <p className="text-sm text-amber-600">
              Disabling this removes protection against unsafe output for all users until
              re-enabled.
            </p>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="max-input-length">
              Maximum input length (characters) (
              {overrideLabel(get.data.max_input_length_is_db_override)})
            </label>
            <InfoTooltip>
              Rejects a chat message longer than this many characters before
              it reaches the LLM, bounding worst-case prompt size. Capped at
              8000 regardless of what is entered here. Leave empty to use
              the env default (typically 8000, same as the cap).
            </InfoTooltip>
          </div>
          <Input
            id="max-input-length"
            type="number"
            min={1}
            // 8000 mirrors the backend's hard ceiling
            // (input_guardrail.MAX_INPUT_LENGTH_CEILING, enforced via
            // UpdateSettingsRequest's Field(le=...) in schemas.py) but is
            // only a soft UX hint here, not the real enforcement -- the
            // backend still authoritatively rejects an out-of-range value
            // with a 422 regardless of what the browser's number input
            // allows through. SystemSettingsResponse doesn't carry this
            // ceiling as a field (deliberately: it's a fixed constant, not
            // per-deployment config), so there's no live value to bind to
            // here instead of a literal.
            max={8000}
            value={maxInputLength}
            onChange={(e) => {
              setMaxInputLength(e.target.value)
              markFieldEdited('max_input_length')
            }}
            placeholder="Leave empty to use the env default"
          />
          <Button
            type="button"
            variant="link"
            className="h-auto p-0 text-sm"
            onClick={() => {
              setMaxInputLength('')
              markFieldCleared('max_input_length')
            }}
          >
            Reset to default
          </Button>
        </div>

        <div className="space-y-2">
          <h4 className="text-sm font-semibold">Detection patterns</h4>
          <ul className="space-y-2">
            {guardrailPatterns.map((pattern) => (
              <li
                key={pattern.id}
                className="flex items-center justify-between gap-2 rounded border border-border p-2"
              >
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`Enable ${pattern.label}`}
                    checked={pattern.enabled}
                    onChange={(e) => handleTogglePattern(pattern.id, e.target.checked)}
                  />
                  <div>
                    <p className="text-sm font-medium">{pattern.label}</p>
                    {pattern.source === 'custom' && pattern.pattern_text !== null && (
                      <p className="text-sm text-muted-foreground">{pattern.pattern_text}</p>
                    )}
                  </div>
                </div>
                {pattern.source === 'custom' && (
                  <Button
                    type="button"
                    variant="link"
                    className="h-auto p-0 text-sm"
                    onClick={() => handleDeletePattern(pattern.id)}
                  >
                    Delete
                  </Button>
                )}
              </li>
            ))}
          </ul>

          <div className="space-y-2 rounded border border-border p-2">
            <p className="text-sm font-medium">Add custom pattern</p>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="new-pattern-label">
                Pattern label
              </label>
              <Input
                id="new-pattern-label"
                value={newPatternLabel}
                onChange={(e) => setNewPatternLabel(e.target.value)}
                placeholder="e.g. Block competitor mentions"
              />
              <label className="text-sm font-medium" htmlFor="new-pattern-phrase">
                Pattern phrase
              </label>
              <Input
                id="new-pattern-phrase"
                value={newPatternPhrase}
                onChange={(e) => setNewPatternPhrase(e.target.value)}
                placeholder="the literal phrase to detect"
              />
              <Button
                type="button"
                onClick={handleAddPattern}
                disabled={newPatternLabel.trim() === '' || newPatternPhrase.trim() === ''}
              >
                Add pattern
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-border p-4" aria-label="Observability">
        <h3 className="text-lg font-semibold">Observability</h3>
        <p className="text-sm text-muted-foreground">
          LLM request tracing to the self-hosted Phoenix instance, for inspecting chat agent runs
          (prompts, tool calls, latency, token counts).
        </p>

        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <input
              id="tracing-enabled"
              type="checkbox"
              checked={tracingEnabled}
              onChange={(e) => {
                setTracingEnabled(e.target.checked)
                markFieldEdited('tracing_enabled')
              }}
            />
            <div className="flex items-center gap-1.5">
              <label className="text-sm font-medium" htmlFor="tracing-enabled">
                Enable LLM tracing ({overrideLabel(get.data.tracing_enabled_is_db_override)})
              </label>
              <InfoTooltip>
                Records every chat agent run (LLM calls, tool calls, latency,
                token counts) to the self-hosted Phoenix instance for
                inspection. Useful for debugging and understanding agent
                behavior; adds no cost beyond local trace storage since
                Phoenix runs in this deployment.
              </InfoTooltip>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Unlike the other settings on this page, this change takes effect only after the
            backend is restarted — it is resolved once at process startup, not on the next
            request.
          </p>
        </div>
      </section>

      <section
        className="space-y-4 rounded-lg border border-border p-4"
        aria-label="Rate limiting"
      >
        <h3 className="text-lg font-semibold">Rate Limiting</h3>
        <p className="text-sm text-muted-foreground">
          Bounds request volume per user (chat) or per client IP (login), independent of the
          guardrails above — this protects against resource exhaustion, not unsafe content. An
          excess request is rejected with a 429 response until its bucket refills.
        </p>

        <div className="flex items-center gap-2">
          <input
            id="rate-limit-enabled"
            type="checkbox"
            checked={rateLimitEnabled}
            onChange={(e) => {
              setRateLimitEnabled(e.target.checked)
              markFieldEdited('rate_limit_enabled')
            }}
          />
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="rate-limit-enabled">
              Enable rate limiting ({overrideLabel(get.data.rate_limit_enabled_is_db_override)})
            </label>
            <InfoTooltip>
              One switch covers both the chat and login buckets below.
              Recommended on for any deployment reachable by more than a
              handful of trusted users, since chat requests drive the most
              expensive path in the system (an LLM call, and sometimes an
              embedding + search call too).
            </InfoTooltip>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="rate-limit-chat-capacity">
              Chat burst capacity ({overrideLabel(get.data.rate_limit_chat_capacity_is_db_override)})
            </label>
            <InfoTooltip>
              Maximum number of chat requests a single user can send back to
              back before being throttled, regardless of refill rate. A
              common default is 10 — enough for a normal back-and-forth
              conversation without pausing.
            </InfoTooltip>
          </div>
          <Input
            id="rate-limit-chat-capacity"
            type="number"
            // min is a soft UX hint only, same caveat as max-input-length's
            // max={8000} above -- the backend's Field(ge=1) is the real
            // enforcement; a typed/pasted 0 or negative value still reaches
            // Save and gets rejected there with a 422.
            min={1}
            value={rateLimitChatCapacity}
            onChange={(e) => {
              setRateLimitChatCapacity(e.target.value)
              markFieldEdited('rate_limit_chat_capacity')
            }}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="rate-limit-chat-refill">
              Chat refill rate (requests/minute) (
              {overrideLabel(get.data.rate_limit_chat_refill_per_minute_is_db_override)})
            </label>
            <InfoTooltip>
              How many additional chat requests a user regains per minute
              after using up their burst capacity. A common default is 10 —
              roughly one request every 6 seconds, sustained.
            </InfoTooltip>
          </div>
          <Input
            id="rate-limit-chat-refill"
            type="number"
            min={1}
            value={rateLimitChatRefillPerMinute}
            onChange={(e) => {
              setRateLimitChatRefillPerMinute(e.target.value)
              markFieldEdited('rate_limit_chat_refill_per_minute')
            }}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="rate-limit-auth-capacity">
              Login burst capacity ({overrideLabel(get.data.rate_limit_auth_capacity_is_db_override)})
            </label>
            <InfoTooltip>
              Maximum number of login/token-exchange attempts a single
              client IP can make back to back before being throttled. Keyed
              by IP, not by user, since there is no authenticated identity
              yet at this endpoint. A common default is 10.
            </InfoTooltip>
          </div>
          <Input
            id="rate-limit-auth-capacity"
            type="number"
            min={1}
            value={rateLimitAuthCapacity}
            onChange={(e) => {
              setRateLimitAuthCapacity(e.target.value)
              markFieldEdited('rate_limit_auth_capacity')
            }}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-medium" htmlFor="rate-limit-auth-refill">
              Login refill rate (attempts/minute) (
              {overrideLabel(get.data.rate_limit_auth_refill_per_minute_is_db_override)})
            </label>
            <InfoTooltip>
              How many additional login attempts a client IP regains per
              minute after using up its burst capacity. A common default is
              10. If this deployment sits behind a reverse proxy, also set
              the env-only RATE_LIMIT_TRUSTED_PROXY_COUNT (not on this page)
              or every caller behind the proxy will share one bucket.
            </InfoTooltip>
          </div>
          <Input
            id="rate-limit-auth-refill"
            type="number"
            min={1}
            value={rateLimitAuthRefillPerMinute}
            onChange={(e) => {
              setRateLimitAuthRefillPerMinute(e.target.value)
              markFieldEdited('rate_limit_auth_refill_per_minute')
            }}
          />
        </div>

        <Button
          type="button"
          variant="link"
          className="h-auto p-0 text-sm"
          onClick={() => {
            setRateLimitChatCapacity(String(get.data?.rate_limit_chat_capacity ?? ''))
            setRateLimitChatRefillPerMinute(
              String(get.data?.rate_limit_chat_refill_per_minute ?? '')
            )
            setRateLimitAuthCapacity(String(get.data?.rate_limit_auth_capacity ?? ''))
            setRateLimitAuthRefillPerMinute(
              String(get.data?.rate_limit_auth_refill_per_minute ?? '')
            )
            markFieldCleared('rate_limit_chat_capacity')
            markFieldCleared('rate_limit_chat_refill_per_minute')
            markFieldCleared('rate_limit_auth_capacity')
            markFieldCleared('rate_limit_auth_refill_per_minute')
          }}
        >
          Reset capacity/refill to default
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
