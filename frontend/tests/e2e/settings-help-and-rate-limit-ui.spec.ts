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
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts) -- issue #53's real fix
// for the per-test-login/shared-rate-limit-bucket collision this comment
// used to describe: each test now navigates to '/' directly instead of
// performing its own real login, so this file's tests no longer consume any
// of POST /api/auth/token's rate-limit budget at all.

async function openSettings(page: import('@playwright/test').Page) {
  await page.locator('button:has-text("Settings")').click()
  // Scoped to the section heading, not a plain getByText: the "Common
  // setups" panel's prose contains "rate limiting" (lowercase), and
  // Playwright's getByText string matching is case-insensitive, so a bare
  // getByText('Rate Limiting') resolves to multiple elements.
  await expect(page.getByRole('heading', { name: 'Rate Limiting' })).toBeVisible({
    timeout: 10000,
  })
}

test.describe('Settings screen: rate limit UI and help tooltips (issue #37)', () => {
  test('the Rate Limiting section renders all five fields with their current values', async ({
    page,
  }) => {
    await page.goto('/')
    await openSettings(page)

    await expect(page.getByLabel(/enable rate limiting/i)).toBeVisible()
    await expect(page.getByLabel(/chat burst capacity/i)).toBeVisible()
    await expect(page.getByLabel(/chat refill rate/i)).toBeVisible()
    await expect(page.getByLabel(/login burst capacity/i)).toBeVisible()
    await expect(page.getByLabel(/login refill rate/i)).toBeVisible()

    // Every field starts with a real, non-empty numeric value (the resolved
    // env default or DB override) -- proves the section is wired to the
    // real GET /api/settings response, not rendering blank inputs.
    await expect(page.getByLabel(/chat burst capacity/i)).not.toHaveValue('')
  })

  test('changing the chat burst capacity persists across a reload', async ({ page }) => {
    await page.goto('/')
    await openSettings(page)

    const capacityInput = page.getByLabel(/chat burst capacity/i)
    const originalValue = await capacityInput.inputValue()

    try {
      await capacityInput.fill('7')
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })

      await page.reload()
      // Re-authenticating from localStorage on reload isn't instant -- wait
      // for the authenticated shell to render (see auth.spec.ts's "login
      // persists across page refresh") before clicking "Settings", or the
      // click can fire before the app has re-rendered post-reload.
      await expect(page.locator('button:has-text("Settings")')).toBeVisible({ timeout: 15000 })
      await openSettings(page)
      await expect(page.getByLabel(/chat burst capacity/i)).toHaveValue('7')
    } finally {
      await openSettings(page)
      await page.getByLabel(/chat burst capacity/i).fill(originalValue)
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved').last()).toBeVisible({ timeout: 5000 })
    }
  })

  test('a field help tooltip is reachable by keyboard and reveals explanatory text', async ({
    page,
  }) => {
    await page.goto('/')
    await openSettings(page)

    // Every tooltip trigger shares the accessible name "Show help" (see
    // Settings.tsx and docs/SECURITY.md's "Settings Screen Help Text"
    // section for why); scope to the one next to the chat capacity field via
    // its <label for="rate-limit-chat-capacity">, not a plain getByText --
    // the "Common setups" panel's prose also contains "chat burst capacity"
    // (lowercase), and getByText's case-insensitive matching would otherwise
    // resolve to more than one element.
    const capacityLabel = page.locator('label[for="rate-limit-chat-capacity"]')
    const helpTrigger = capacityLabel.locator('..').getByRole('button', { name: 'Show help' })

    // A real Tab keypress landing on the trigger, not element.focus() --
    // Playwright's .focus() sets DOM focus without dispatching the
    // keyboard-originated focus event Radix's open-on-focus handling picks
    // up reliably, which was flaky in practice (toBeFocused() passed but
    // the tooltip never opened). In DOM order the trigger comes right after
    // its field's <label> (see Settings.tsx), i.e. right before the "Enable
    // rate limiting" checkbox's own label+tooltip pair that precedes this
    // field -- focus the checkbox first, then Tab forward twice: once past
    // its own tooltip trigger, once onto this field's.
    await page.getByLabel(/enable rate limiting/i).focus()
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await expect(helpTrigger).toBeFocused()
    await expect(page.getByText(/maximum number of chat requests/i)).toBeVisible({
      timeout: 5000,
    })
  })

  test('the "Common setups" reference panel is visible on the Settings screen', async ({
    page,
  }) => {
    await page.goto('/')
    await openSettings(page)

    await expect(page.getByText('Common setups')).toBeVisible()
    await expect(page.getByText(/privacy-sensitive/i)).toBeVisible()
    await expect(page.getByText(/general-purpose/i)).toBeVisible()
  })
})
