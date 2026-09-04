import { test, expect } from '@playwright/test'

// Validates issue #40: an admin has a "User Management" entry point in the
// main nav instead of having to independently know Keycloak exists and find
// its admin console. Scope is deliberately a deep link only (see
// docs/USER_MANAGEMENT.md's "Why there's no in-app user editor") -- this
// spec confirms the link is visible to an admin and points at the right
// realm's admin console, not that an in-app editor works (there isn't one).
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts) -- issue #53 -- so this
// test navigates to '/' directly rather than performing a real login. This
// flow never touches the LLM, so it runs against CI's default fake-provider
// stack like any other spec (see AGENTS.md's e2e "CI coverage" section for
// the one spec that needs the opposite treatment).

test.describe('Admin User Management deep link (issue #40)', () => {
  test('an admin sees a User Management link that opens the Keycloak admin console for this realm', async ({
    page,
    context,
  }) => {
    await page.goto('/')

    const userManagementLink = page.getByRole('link', { name: 'User Management' })
    await expect(userManagementLink).toBeVisible({ timeout: 10000 })
    await expect(userManagementLink).toHaveAttribute('target', '_blank')

    const [newPage] = await Promise.all([
      context.waitForEvent('page'),
      userManagementLink.click(),
    ])
    await newPage.waitForLoadState('domcontentloaded')

    expect(newPage.url()).toContain('/admin/master/console')
    expect(newPage.url()).toContain('/eaistack/users')
  })
})
