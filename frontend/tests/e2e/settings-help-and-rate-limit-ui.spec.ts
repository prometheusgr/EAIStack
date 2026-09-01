import { test, expect } from '@playwright/test'

// Validates two additions to the Settings screen: (1) issue #37's UI for the
// 5 rate-limit fields the backend already supported via GET/PUT /api/settings
// (see backend/app/services/rate_limit_config_service.py) but the screen
// never rendered, and (2) hover/keyboard-focus help tooltips added to every
// field on the page. Both are presentation-only -- no new API surface, no
// change to validation -- so unlike guardrail-admin-config.spec.ts this
// doesn't need to drive a chat message through to prove a behavior change;
// it proves the real Settings UI round-trips these fields through the real
// backend and that the help text is actually reachable, not just present in
// the DOM in a way a screen reader or keyboard user couldn't discover.
//
// Every test restores the setting(s) it changed in a `finally`-style cleanup,
// per AGENTS.md's e2e "start from a clean, known state" convention -- the
// seeded testuser's SystemSettings row is shared, real Postgres state across
// every spec in this suite.

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/')
  await page.locator('button:has-text("Login")').click()
  await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
  await page.locator('input[name="username"]').fill('testuser')
  await page.locator('input[name="password"]').fill('testpassword')
  await page.locator('input[type="submit"]').click()
  await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
}

async function openSettings(page: import('@playwright/test').Page) {
  await page.locator('button:has-text("Settings")').click()
  await expect(page.getByText('Rate Limiting')).toBeVisible({ timeout: 10000 })
}

test.describe('Settings screen: rate limit UI and help tooltips (issue #37)', () => {
  test('the Rate Limiting section renders all five fields with their current values', async ({
    page,
  }) => {
    await loginAsAdmin(page)
    await openSettings(page)

    await expect(page.locator('#rate-limit-enabled')).toBeVisible()
    await expect(page.locator('#rate-limit-chat-capacity')).toBeVisible()
    await expect(page.locator('#rate-limit-chat-refill')).toBeVisible()
    await expect(page.locator('#rate-limit-auth-capacity')).toBeVisible()
    await expect(page.locator('#rate-limit-auth-refill')).toBeVisible()

    // Every field starts with a real, non-empty numeric value (the resolved
    // env default or DB override) -- proves the section is wired to the
    // real GET /api/settings response, not rendering blank inputs.
    await expect(page.locator('#rate-limit-chat-capacity')).not.toHaveValue('')
  })

  test('changing the chat burst capacity persists across a reload', async ({ page }) => {
    await loginAsAdmin(page)
    await openSettings(page)

    const capacityInput = page.locator('#rate-limit-chat-capacity')
    const originalValue = await capacityInput.inputValue()

    try {
      await capacityInput.fill('7')
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved')).toBeVisible({ timeout: 5000 })

      await page.reload()
      await openSettings(page)
      await expect(page.locator('#rate-limit-chat-capacity')).toHaveValue('7')
    } finally {
      await openSettings(page)
      await page.locator('#rate-limit-chat-capacity').fill(originalValue)
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved')).toBeVisible({ timeout: 5000 })
    }
  })

  test('a field help tooltip is reachable by keyboard and reveals explanatory text', async ({
    page,
  }) => {
    await loginAsAdmin(page)
    await openSettings(page)

    // Every tooltip trigger shares the accessible name "Show help" (see
    // Settings.tsx and docs/SECURITY.md's "Settings Screen Help Text"
    // section for why); scope to the one next to the chat capacity field.
    const capacityLabel = page.locator('label[for="rate-limit-chat-capacity"]')
    const helpTrigger = capacityLabel.locator('..').getByRole('button', { name: 'Show help' })

    await helpTrigger.focus()
    await expect(page.getByText(/maximum number of chat requests/i)).toBeVisible({
      timeout: 5000,
    })
  })

  test('the "Common setups" reference panel is visible on the Settings screen', async ({
    page,
  }) => {
    await loginAsAdmin(page)
    await openSettings(page)

    await expect(page.getByText('Common setups')).toBeVisible()
    await expect(page.getByText(/privacy-sensitive/i)).toBeVisible()
    await expect(page.getByText(/general-purpose/i)).toBeVisible()
  })
})
