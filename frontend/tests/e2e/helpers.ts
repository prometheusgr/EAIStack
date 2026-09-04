import { expect, type Page } from '@playwright/test'

// Shared across every spec in this directory that needs a real, logged-in
// session against the real Keycloak flow (seeded testuser/testpassword from
// infra/keycloak/realm-import.json) -- see AGENTS.md's "End-to-End (E2E)
// Tests" conventions. Previously each spec defined its own near-identical
// copy of this sequence; one spec's copy had already drifted (missing the
// "New chat" reset step the others had), which is exactly the maintenance
// cost of duplicating a shared flow across files -- a selector or flow
// change now only needs to be made here.

/** Logs in as the seeded testuser and waits for the app to load. Does not
 * touch chat state -- use loginAndStartNewChat for specs that drive the
 * chat UI, since accumulated thread history from prior runs can otherwise
 * grow the page tall enough for the footer to intercept clicks, or collide
 * with getByText assertions meant to match only the current run's turn.
 *
 * Asserts the authenticated shell actually rendered (the Logout button),
 * not just that Keycloak redirected back to '/' -- a rejected token
 * exchange (e.g. a POST /api/auth/token rate-limit trip, see issue #53)
 * also redirects back to '/' and would otherwise pass a bare
 * waitForURL('/') check while leaving the page on the logged-out screen
 * (AuthContext.tsx sets authError and isAuthenticated stays false; see
 * App.tsx's data-testid="auth-error-banner"). Without this assertion, a
 * throttled login lets the calling test silently proceed against an
 * unauthenticated page and fail later for a confusing, unrelated reason
 * (e.g. "Login" button not found where a chat input was expected).
 */
export async function login(page: Page): Promise<void> {
  await page.goto('/')
  await page.locator('button:has-text("Login")').click()
  await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
  await page.locator('input[name="username"]').fill('testuser')
  await page.locator('input[name="password"]').fill('testpassword')
  await page.locator('input[type="submit"]').click()
  await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
  await expect(page.locator('button:has-text("Logout")')).toBeVisible({ timeout: 10000 })
}

/** Navigates to the chat screen and starts a fresh thread, returning the
 * message input locator. Assumes the page is already authenticated (either
 * via a prior login() call in the same test, or via the pre-authenticated
 * 'chromium' project's storageState -- see playwright.config.ts and
 * auth.setup.ts) -- does not itself check for or perform a login. Use this
 * for any spec that sends chat messages, so each test starts from a clean,
 * known state rather than assuming an empty page (see AGENTS.md's e2e
 * conventions).
 */
export async function startNewChat(page: Page) {
  await page.goto('/')
  const chatInput = page.locator('input[placeholder="Type your message..."]')
  await expect(chatInput).toBeVisible({ timeout: 10000 })
  await page.locator('button:has-text("New chat")').click()

  return chatInput
}

/** Logs in, then starts a fresh chat thread and returns the message input
 * locator. Use this only for specs that must perform a real, fresh login
 * themselves (see AUTH_FILE'd specs above, which should use startNewChat
 * instead since they're already authenticated via storageState).
 */
export async function loginAndStartNewChat(page: Page) {
  await login(page)
  return startNewChat(page)
}
