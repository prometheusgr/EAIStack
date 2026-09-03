import { test, expect } from '@playwright/test'

// Validates issue #45: the audit trail (backend/app/api/settings.py's
// GET /api/settings/audit, already fully implemented and populated by every
// settings mutation) is readable in-product by an admin, not just via direct
// database access. This exercises the real Settings UI + Audit Log UI
// against the real backend: make a settings change, confirm it produces a
// real audit entry the admin can see on the new Audit Log screen.
//
// Every test restores the setting it changed in a `finally`-style cleanup so
// runs don't leak state into guardrail-admin-config.spec.ts or subsequent
// runs of this file -- the seeded testuser's SystemSettings row is shared,
// real Postgres state across every spec in this suite (see AGENTS.md's e2e
// "start from a clean, known state" convention).
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts) -- issue #53 -- so
// each test navigates to '/' directly rather than performing a real login.

async function openSettings(page: import('@playwright/test').Page) {
  await page.locator('button:has-text("Settings")').click()
  await expect(page.getByRole('heading', { name: 'Guardrails' })).toBeVisible({ timeout: 10000 })
}

async function openAuditLog(page: import('@playwright/test').Page) {
  await page.locator('button:has-text("Audit Log")').click()
  await expect(page.getByRole('heading', { name: 'Audit Log' })).toBeVisible({ timeout: 10000 })
}

test.describe('Admin audit log viewer (issue #45)', () => {
  test('the Audit Log nav entry is visible to an admin', async ({ page }) => {
    await page.goto('/')

    await expect(page.locator('button:has-text("Audit Log")')).toBeVisible()
  })

  test('a real settings change produces an entry visible on the Audit Log screen', async ({
    page,
  }) => {
    await page.goto('/')
    await openSettings(page)

    const inputToggle = page.locator('#guardrails-input-enabled')
    await expect(inputToggle).toBeChecked()
    await inputToggle.uncheck()
    await page.locator('button:has-text("Save")').click()
    await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })

    try {
      await openAuditLog(page)

      const latestEntryRow = page.getByRole('row', { name: /guardrail\.config_update/ }).first()
      await expect(latestEntryRow).toBeVisible({ timeout: 10000 })
      await expect(latestEntryRow).toContainText('guardrails_input_enabled')
    } finally {
      await openSettings(page)
      await page.locator('#guardrails-input-enabled').check()
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })
    }
  })
})
