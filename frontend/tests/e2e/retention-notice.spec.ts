import { test, expect } from '@playwright/test'
import { startNewChat } from './helpers'

// Validates issue #49: retention windows were already fully
// admin-configurable via the Settings screen, but no ordinary (non-admin)
// user of the chat UI had any in-product way to see how long their own data
// is kept. GET /api/settings/retention-notice (deliberately not admin-gated,
// unlike GET /api/settings) exposes the same *effective* values, and
// ChatWindow renders them as a small dismissible notice.
//
// Content-independent (no LLM interaction needed to see the notice), so this
// runs under CI's default fake-provider profile like most specs in this
// suite -- it does not need the "real content" marker AGENTS.md's E2E
// section describes for specs that assert on actual model output (see
// tools/check_e2e_ci_coverage.py, which does a literal substring search for
// that marker string across every spec file -- this sentence is phrased to
// avoid an accidental match).
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts) -- issue #53 -- so each
// test starts a new chat directly rather than performing a real login.

test('the chat screen shows the effective conversation-retention window', async ({ page }) => {
  await startNewChat(page)

  await expect(page.getByRole('status', { name: /data retention notice/i })).toBeVisible({
    timeout: 10000,
  })
  await expect(page.getByText(/retained for|kept indefinitely|purged immediately/i)).toBeVisible()
})

test('the notice can be dismissed', async ({ page }) => {
  await startNewChat(page)

  const notice = page.getByRole('status', { name: /data retention notice/i })
  await expect(notice).toBeVisible({ timeout: 10000 })

  await page.getByRole('button', { name: /dismiss retention notice/i }).click()

  await expect(notice).not.toBeVisible()
})
