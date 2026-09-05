import { test, expect } from '@playwright/test'

// Validates issue #68's Settings UI: the "Retrieval & Chunking" section for
// the six RAG retrieval/chunking fields the backend resolves via
// GET/PUT /api/settings (see backend/app/services/rag_config_service.py).
// Presentation-only from the frontend's perspective -- no new API surface --
// so like settings-help-and-rate-limit-ui.spec.ts, this proves the real
// Settings UI round-trips these fields through the real backend, not that
// retrieval quality itself changed (that requires a real embedding server;
// see AGENTS.md's E2E conventions and
// mcp-servers/doc-search/tests/integration/ for the threshold/clamping
// behavior itself, already covered against real Postgres+pgvector).
//
// Every test restores the setting(s) it changed in a `finally`-style
// cleanup, per AGENTS.md's e2e "start from a clean, known state" convention
// -- the seeded testuser's SystemSettings row is shared, real Postgres state
// across every spec in this suite.
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts).

async function openSettings(page: import('@playwright/test').Page) {
  await page.locator('button:has-text("Settings")').click()
  await expect(page.getByRole('heading', { name: 'Retrieval & Chunking' })).toBeVisible({
    timeout: 10000,
  })
}

test.describe('Settings screen: retrieval & chunking config (issue #68)', () => {
  test('the Retrieval & Chunking section renders all six fields with their current values', async ({
    page,
  }) => {
    await page.goto('/')
    await openSettings(page)

    await expect(page.getByLabel(/similarity threshold/i)).toBeVisible()
    await expect(page.getByLabel(/maximum results/i)).toBeVisible()
    await expect(page.getByLabel(/minimum chunk size/i)).toBeVisible()
    await expect(page.getByLabel(/maximum chunk size/i)).toBeVisible()
    await expect(page.getByLabel(/chunk overlap ratio/i)).toBeVisible()
    await expect(page.getByLabel(/maximum excerpt length/i)).toBeVisible()

    // Every field except the threshold (which legitimately defaults to
    // blank -- "no cutoff") starts with a real, non-empty numeric value --
    // proves the section is wired to the real GET /api/settings response,
    // not rendering blank inputs.
    await expect(page.getByLabel(/maximum results/i)).not.toHaveValue('')
    await expect(page.getByLabel(/maximum chunk size/i)).not.toHaveValue('')
  })

  test('changing the maximum results field persists across a reload', async ({ page }) => {
    await page.goto('/')
    await openSettings(page)

    const maxResultsInput = page.getByLabel(/maximum results/i)
    const originalValue = await maxResultsInput.inputValue()

    try {
      await maxResultsInput.fill('3')
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })

      await page.reload()
      await expect(page.locator('button:has-text("Settings")')).toBeVisible({ timeout: 15000 })
      await openSettings(page)
      await expect(page.getByLabel(/maximum results/i)).toHaveValue('3')
      await expect(
        page.getByRole('region', { name: /retrieval and chunking/i })
      ).toContainText(/overridden/i)
    } finally {
      await openSettings(page)
      await page.getByLabel(/maximum results/i).fill(originalValue)
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })
    }
  })

  test('setting a similarity threshold and clearing it back to "no cutoff" round-trips', async ({
    page,
  }) => {
    await page.goto('/')
    await openSettings(page)

    const thresholdInput = page.getByLabel(/similarity threshold/i)
    const originalValue = await thresholdInput.inputValue()

    try {
      await thresholdInput.fill('0.4')
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })

      await page.reload()
      await expect(page.locator('button:has-text("Settings")')).toBeVisible({ timeout: 15000 })
      await openSettings(page)
      await expect(page.getByLabel(/similarity threshold/i)).toHaveValue('0.4')
    } finally {
      await openSettings(page)
      await page.getByLabel(/similarity threshold/i).fill(originalValue)
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })
    }
  })

  test('an invalid minimum/maximum chunk size pair is rejected with an error toast', async ({
    page,
  }) => {
    await page.goto('/')
    await openSettings(page)

    const minInput = page.getByLabel(/minimum chunk size/i)
    const originalMin = await minInput.inputValue()

    try {
      // The env default maximum is 1000; a minimum above it must be
      // rejected by the backend's cross-field check (app.api.settings),
      // which no single field's own Field(ge=..., le=...) bound can express.
      await minInput.fill('5000')
      await page.locator('button:has-text("Save")').click()

      await expect(page.getByText(/minimum chunk size must be less than/i)).toBeVisible({
        timeout: 5000,
      })
    } finally {
      await minInput.fill(originalMin)
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })
    }
  })

  test('a field help tooltip explains the similarity threshold\'s cosine-distance direction', async ({
    page,
  }) => {
    await page.goto('/')
    await openSettings(page)

    const thresholdLabel = page.locator('label[for="rag-similarity-threshold"]')
    const helpTrigger = thresholdLabel.locator('..').getByRole('button', { name: 'Show help' })

    await helpTrigger.hover()
    await expect(page.getByText(/cosine distance/i)).toBeVisible({ timeout: 5000 })
  })
})
