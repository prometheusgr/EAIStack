// Clears LLM/embedding provider and tracing overrides left in SystemSettings
// by a *previous* local session (e.g. a manual `docker-compose up --profile
// llm` run, or poking the Settings screen by hand) before this suite starts.
// Postgres is a named volume that survives `docker-compose down`/`up` and
// even a full `docker-compose build`, so a DB-persisted admin override from
// an earlier session silently outlives it -- unlike the *env* var
// (LLM_PROVIDER=fake), which always resets to whatever the current compose
// invocation sets. resolve_llm_config resolves the DB override *before* the
// env default, so a stale llm_provider="llama-cpp" row makes every chat
// request in this "fake provider" suite actually run real, CPU-bound
// inference -- multiple seconds per call instead of instant -- which reads
// as flaky timeouts in unrelated specs (rate-limit bursts, guardrail
// send-and-wait assertions) with no obvious connection to its real cause.
// Scoped to exactly the fields known to cause this: other admin-configurable
// fields (rate-limit capacity, guardrail toggles, retention windows) are
// each reset by their own owning spec already and are deliberately left
// alone here.
async function resetStaleAdminOverrides(): Promise<void> {
  const tokenResponse = await fetch(
    'http://localhost:8080/realms/eaistack/protocol/openid-connect/token',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'password',
        // eaistack-api (not eaistack-web): the web client has
        // directAccessGrantsEnabled=false (see infra/keycloak/realm-import.json)
        // -- this password-grant shortcut only works against the confidential
        // API client, which exists purely for this kind of script/service
        // use, never for the browser-facing login flow itself.
        client_id: 'eaistack-api',
        client_secret: 'eaistack-api-secret',
        username: 'testuser',
        password: 'testpassword',
      }),
    }
  )
  if (!tokenResponse.ok) {
    // Non-fatal: if Keycloak's direct-grant path is ever disabled or the
    // seeded credentials change, this reset step should degrade to a no-op
    // rather than blocking the entire suite over a best-effort cleanup step.
    console.warn('[global-setup] Could not obtain a token to reset stale admin overrides; skipping.')
    return
  }
  const { access_token: accessToken } = await tokenResponse.json()
  const authHeaders = {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  }

  // PUT /api/settings is a full-replace, not a merge: SystemSettingsRepository
  // .upsert() writes every one of its ~20 columns on every call, and any
  // field omitted from the request body defaults to null (UpdateSettingsRequest's
  // own docstring: "omitting one clears it rather than leaving the previous
  // value in place"). Settings.tsx's own save button avoids this trap by
  // always round-tripping the *entire* currently-loaded settings object and
  // only changing the field the admin actually edited -- this GET-then-PUT
  // does the same, so a real override left by another spec (rate-limit
  // capacity, a guardrail toggle, retention_notice_enabled, etc.) survives
  // untouched, and only the four fields this function actually targets are
  // forced back to their env defaults.
  const currentSettingsResponse = await fetch('http://localhost:8001/api/settings', {
    headers: authHeaders,
  })
  if (!currentSettingsResponse.ok) {
    console.warn(
      `[global-setup] Failed to read current settings (${currentSettingsResponse.status}); skipping admin override reset.`
    )
    return
  }
  const current = await currentSettingsResponse.json()

  // Each field is carried forward as its current resolved value only when a
  // DB override is actually in effect (*_is_db_override); otherwise sending
  // null, not the resolved value, so a field that already has no override
  // stays that way rather than being pinned to today's env default as a new
  // explicit DB row.
  const settingsResponse = await fetch('http://localhost:8001/api/settings', {
    method: 'PUT',
    headers: authHeaders,
    body: JSON.stringify({
      llm_provider: null,
      llm_url: null,
      llm_model: null,
      tracing_enabled: null,
      embedding_provider: current.embedding_provider_is_db_override ? current.embedding_provider : null,
      embedding_url: current.embedding_url_is_db_override ? current.embedding_url : null,
      embedding_model: current.embedding_model_is_db_override ? current.embedding_model : null,
      conversation_retention_hours: current.conversation_retention_hours_is_db_override
        ? current.conversation_retention_hours
        : null,
      cleanup_on_logout: current.cleanup_on_logout_is_db_override ? current.cleanup_on_logout : null,
      knowledge_base_purge_days: current.knowledge_base_purge_days_is_db_override
        ? current.knowledge_base_purge_days
        : null,
      api_key_purge_days: current.api_key_purge_days_is_db_override ? current.api_key_purge_days : null,
      max_input_length: current.max_input_length_is_db_override ? current.max_input_length : null,
      guardrails_input_enabled: current.guardrails_input_enabled_is_db_override
        ? current.guardrails_input_enabled
        : null,
      guardrails_output_enabled: current.guardrails_output_enabled_is_db_override
        ? current.guardrails_output_enabled
        : null,
      rate_limit_enabled: current.rate_limit_enabled_is_db_override ? current.rate_limit_enabled : null,
      rate_limit_chat_capacity: current.rate_limit_chat_capacity_is_db_override
        ? current.rate_limit_chat_capacity
        : null,
      rate_limit_chat_refill_per_minute: current.rate_limit_chat_refill_per_minute_is_db_override
        ? current.rate_limit_chat_refill_per_minute
        : null,
      rate_limit_auth_capacity: current.rate_limit_auth_capacity_is_db_override
        ? current.rate_limit_auth_capacity
        : null,
      rate_limit_auth_refill_per_minute: current.rate_limit_auth_refill_per_minute_is_db_override
        ? current.rate_limit_auth_refill_per_minute
        : null,
      audit_log_ui_enabled: current.audit_log_ui_enabled_is_db_override ? current.audit_log_ui_enabled : null,
      retention_notice_enabled: current.retention_notice_enabled_is_db_override
        ? current.retention_notice_enabled
        : null,
    }),
  })
  if (!settingsResponse.ok) {
    console.warn(
      `[global-setup] Failed to reset stale admin overrides (${settingsResponse.status}); continuing anyway.`
    )
    return
  }
  console.log('[global-setup] ✓ Reset LLM/tracing admin overrides to env defaults')
}

async function waitForService(name: string, url: string, attempts = 30): Promise<boolean> {
  for (let i = 0; i < attempts; i++) {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 2000)
      const response = await fetch(url, { signal: controller.signal })
      clearTimeout(timeoutId)
      if (response.ok) {
        console.log(`[global-setup] ✓ ${name} available`)
        return true
      }
    } catch {
      // Not ready yet; fall through to retry below.
    }
    if (i < attempts - 1) {
      process.stdout.write('.')
      await new Promise((r) => setTimeout(r, 1000))
    }
  }
  return false
}

async function globalSetup() {
  console.log('[global-setup] Starting E2E tests...')
  console.log('[global-setup] Make sure docker-compose up is running with services ready')
  console.log('[global-setup] Required: Keycloak (http://localhost:8080), Backend (http://localhost:8001)')

  // Keycloak is checked first since it's most critical for auth tests.
  const keycloakReady = await waitForService('Keycloak', 'http://localhost:8080/realms/eaistack')
  if (!keycloakReady) {
    console.error('\n[global-setup] ✗ Keycloak not ready after 30 seconds')
    console.error('[global-setup] Make sure docker-compose is running: docker-compose up')
    throw new Error('Keycloak must be running for E2E tests')
  }

  const backendReady = await waitForService('Backend', 'http://localhost:8001/health')
  if (!backendReady) {
    console.error('\n[global-setup] ✗ Backend not ready after 30 seconds')
    console.error('[global-setup] Make sure docker-compose is running: docker-compose up')
    throw new Error('Backend must be running for E2E tests')
  }

  await resetStaleAdminOverrides()

  console.log('\n[global-setup] Ready to start tests!')
}

export default globalSetup
