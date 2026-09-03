import { test, expect } from '@playwright/test'

// requires-profile-llm
//
// The marker comment above is a structural signal, not decoration: it is
// what tools/check_e2e_ci_coverage.py greps for to verify this spec is
// excluded from .github/workflows/ci.yml's e2e-tests step (via
// --grep-invert) — see AGENTS.md's "End-to-End (E2E) Tests" section for
// the full pattern this exists to prevent (a spec asserting on real
// LLM/embedding content that CI silently can never pass, regardless of
// code correctness, because CI runs LLM_PROVIDER=fake). Any new e2e spec
// that asserts on real model *content* (not just that a response
// rendered) must carry this same marker and be added to CI's
// --grep-invert pattern in the same PR, or the linter fails the build.
//
// Validates issue #7's retrieval changes (asymmetric embedding prefixes,
// structure-aware chunking, hybrid vector+full-text search) through the
// real chat UI, real backend, real doc-search MCP server, and a real
// embedding server -- not the "fake" provider unit/integration tests run
// against. Requires `docker-compose up --profile llm` with a real
// embedding GGUF model in ./models/ (see docs/LLM_SETUP.md); with only the
// default profile running, EMBEDDING_PROVIDER=fake produces semantically
// meaningless vectors and the chat agent has no real basis to ground an
// answer in the seeded document, so this spec would fail for the wrong
// reason rather than the right one.
//
// This is the "does retrieval actually work end to end" check per
// AGENTS.md's e2e-after-green process: unit/integration tests already
// cover the prefix/chunking/hybrid-search logic in isolation (mocked HTTP
// boundary or the fake provider); nothing before this drove a real chat
// question through the real embedding + chunking + ranking pipeline.
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts) -- issue #53 -- so
// this test navigates to '/' directly rather than performing a real login.

test.describe('Knowledge base search grounding', () => {
  test('chat answers are grounded in a document only present in the knowledge base', async ({
    page,
  }) => {
    // This test's own assertions below wait up to 60s for a real,
    // CPU-only-inference LLM response -- longer than Playwright's global
    // 30s per-test default (playwright.config.ts), so without raising it
    // here the test can only pass when the model happens to respond
    // unusually fast. Same fix shape as
    // output-guardrail-redaction-indicator.spec.ts's test.setTimeout.
    test.setTimeout(90000)

    await page.goto('/')

    // A fact distinctive enough that the LLM cannot already know it and
    // could only answer correctly by actually retrieving this document -
    // unique per run since the seeded testuser's knowledge base persists
    // across e2e runs (same Postgres).
    const runId = Date.now()
    const secretCode = `ZXQ-${runId}`
    const title = `Onboarding Portal Access ${runId}`
    const content = `The one-time access code for the new employee onboarding portal is ${secretCode}. This code is issued only to HR staff and must never be shared outside the HR team.`

    await page.locator('button:has-text("Embeddings")').click()
    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible()

    // "Paste Text" is KnowledgeBaseUpload's default tab.
    await page.locator('#kb-title').fill(title)
    await page.locator('#kb-content').fill(content)
    await page.getByRole('button', { name: 'Create Entry' }).click()

    await expect(page.getByText(title)).toBeVisible({ timeout: 10000 })

    await page.locator('button:has-text("Chat")').click()
    const chatInput = page.locator('input[placeholder="Type your message..."]')
    await expect(chatInput).toBeVisible({ timeout: 10000 })

    // Fresh thread per run, same reasoning as guardrails.spec.ts's login
    // helper: keeps this test's message count small and predictable
    // against a growing seeded conversation history.
    await page.locator('button:has-text("New chat")').click()

    const question = `What is the one-time access code for the new employee onboarding portal? (test run ${runId})`
    await chatInput.fill(question)
    await page.locator('button:has-text("Send")').click()

    await expect(page.getByText(question)).toBeVisible({ timeout: 5000 })

    // A generous timeout: this round trip is two real LLM calls (the
    // tool-call turn and the grounded-answer turn) plus a real MCP tool
    // call to doc-search plus a real embedding-server call, not a mocked
    // response -- on CPU-only inference each LLM call alone has been
    // observed to take 10-13s once the seeded testuser's prior conversation
    // history grows the prompt past a few hundred tokens.
    await expect(page.getByText(secretCode)).toBeVisible({ timeout: 60000 })

    // Issue #19: the response also names which document grounded it. Same
    // "requires a real model" constraint as the assertion above -- the
    // fake LLM provider (see backend/app/core/llm_client.py's FakeChatModel)
    // never emits a tool call at all, so ChatResponse.sources is always []
    // under CI's default profile regardless of app correctness.
    await expect(page.getByText('Sources:')).toBeVisible()
    await expect(page.getByRole('button', { name: title })).toBeVisible()

    // The source citation is a hotlink, not just inert text: clicking it
    // opens the actual cited document so the user can validate the answer
    // against its real content, rather than trusting the LLM's prose alone.
    await page.getByRole('button', { name: title }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText(secretCode).last()).toBeVisible()
  })
})
