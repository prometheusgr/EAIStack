import { test, expect, type Page } from '@playwright/test'

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
// Logs in once for the whole file (test.describe.serial + a single shared
// page), not once per test -- POST /api/auth/token is itself rate-limited
// (issue #25, default capacity 10/refill 10 per minute, keyed by client IP),
// and every e2e spec file in this suite calls it once per test via its own
// loginAsAdmin helper. Four fresh logins in this file stacked on top of
// guardrail-admin-config.spec.ts's four (same IP, same CI runner) was
// enough to trip that bucket in practice ("Too many requests" on the login
// screen), a real interaction between the two features this PR touches.
//
// The one test that changes a setting restores it in a `finally`-style
// cleanup, per AGENTS.md's e2e "start from a clean, known state" convention
// -- the seeded testuser's SystemSettings row is shared, real Postgres state
// across every spec in this suite.

async function loginAsAdmin(page: Page) {
  await page.goto('/')
  await page.locator('button:has-text("Login")').click()
  await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
  await page.locator('input[name="username"]').fill('testuser')
  await page.locator('input[name="password"]').fill('testpassword')
  await page.locator('input[type="submit"]').click()
  await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
}

async function openSettings(page: Page) {
  await page.locator('button:has-text("Settings")').click()
  // Scoped to the section heading, not a plain getByText: the "Common
  // setups" panel's prose contains "rate limiting" (lowercase), and
  // Playwright's getByText string matching is case-insensitive, so a bare
  // getByText('Rate Limiting') resolves to multiple elements.
  await expect(page.getByRole('heading', { name: 'Rate Limiting' })).toBeVisible({
    timeout: 10000,
  })
}

test.describe.serial('Settings screen: rate limit UI and help tooltips (issue #37)', () => {
  let page: Page

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage()
    await loginAsAdmin(page)
  })

  test.afterAll(async () => {
    await page.close()
  })

  test('the Rate Limiting section renders all five fields with their current values', async () => {
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

  test('changing the chat burst capacity persists across a reload', async () => {
    await openSettings(page)

    const capacityInput = page.getByLabel(/chat burst capacity/i)
    const originalValue = await capacityInput.inputValue()

    try {
      await capacityInput.fill('7')
      await page.locator('button:has-text("Save")').click()
      await expect(page.getByText('Settings saved')).toBeVisible({ timeout: 5000 })

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
      await expect(page.getByText('Settings saved')).toBeVisible({ timeout: 5000 })
    }
  })

  test('a field help tooltip is reachable by keyboard and reveals explanatory text', async () => {
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

  test('the "Common setups" reference panel is visible on the Settings screen', async () => {
    await openSettings(page)

    await expect(page.getByText('Common setups')).toBeVisible()
    await expect(page.getByText(/privacy-sensitive/i)).toBeVisible()
    await expect(page.getByText(/general-purpose/i)).toBeVisible()
  })
})
