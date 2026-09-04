import { test, expect } from '@playwright/test'
import { startNewChat } from './helpers'

// Validates issue #47: a chat send that is rejected for being rate-limited
// (429, see backend/app/services/rate_limiter_service.py) must be visually
// distinguishable from a guardrail rejection (400) or a generic failure --
// and must show a live countdown sourced from the backend's Retry-After
// header, disabling Send until it elapses. See ChatWindow.tsx's
// classifySendError/useRetryCountdown.
//
// Runs against the fake LLM provider (default docker-compose profile, same
// as CI) deliberately: the default per-user chat bucket is small
// (rate_limit_chat_capacity=10, refilling at rate_limit_chat_refill_per_minute=10
// -- see app/core/config.py) and the bucket starts full, so 11 requests
// fired back-to-back trip it regardless of provider speed. Driving all 11
// through the chat UI's own send-and-wait-for-response cycle would let the
// slow, continuous refill (~1 token/6s) keep pace with consumption once
// each round trip in a loaded CI runner takes longer than that -- which is
// exactly what made an earlier version of this test flaky in CI. Firing the
// burst directly via page.request (bypassing the UI's per-message render
// cycle) guarantees the 11 requests land within a small fraction of the
// 6-second refill window, then the UI is exercised once for real to observe
// the resulting banner/countdown state a user would actually see.
//
// The bucket is per-user (testuser), shared with every other e2e spec in
// this suite -- and the rate limit check runs BEFORE the guardrail check on
// every /api/agents/chat request (see agents.py's chat() docstring), so a
// guardrail-rejection test's send also consumes a token. Playwright's single
// worker (playwright.config.ts) runs specs sequentially, but this test must
// still hand the bucket back full before finishing, or a guardrail spec
// running immediately after could get an unexpected 429 instead of the
// guardrail rejection it's testing for -- exactly what happened when an
// earlier version of this test left the bucket empty. Waiting a full
// capacity/refill cycle (60s here) guarantees a clean handoff.
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts) -- issue #53.

test('a chat send throttled by the rate limiter shows a distinguishable countdown banner, distinct from a guardrail rejection', async ({
  page,
}) => {
  test.setTimeout(120000)
  await startNewChat(page)

  const accessToken = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(accessToken).toBeTruthy()

  // Exhaust the bucket (capacity 10, starts full) with a burst of concurrent
  // direct API calls, independent of the UI.
  const burstSize = 10
  await Promise.all(
    Array.from({ length: burstSize }, (_, i) =>
      page.request.post('/api/agents/chat', {
        headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
        data: { message: `Rate limit burst probe ${Date.now()}-${i}` },
      })
    )
  )

  // The 11th request, sent through the real chat UI, should now be denied.
  const chatInput = page.locator('input[placeholder="Type your message..."]')
  const sendButton = page.locator('button:has-text("Send")')
  await chatInput.fill(`Rate limit probe over the limit ${Date.now()}`)
  await sendButton.click()

  const rateLimitBanner = page.getByRole('alert', { name: 'Rate limit reached' })
  await expect(rateLimitBanner).toBeVisible({ timeout: 5000 })

  // Distinguishable from a guardrail rejection: different aria-label/icon,
  // never the guardrail's "couldn't be sent" copy.
  await expect(page.getByRole('alert', { name: 'Message rejected by content safety rule' })).not.toBeVisible()

  // The Send button reflects the countdown and is disabled while it runs.
  const sendButtonLabel = await sendButton.textContent()
  expect(sendButtonLabel).toMatch(/retry in \d+s/i)
  await expect(sendButton).toBeDisabled()

  // The countdown eventually elapses and Send becomes usable again.
  await expect(sendButton).toBeEnabled({ timeout: 20000 })
  await expect(sendButton).toHaveText(/^send$/i)

  // Hand the bucket back full for whichever spec runs next (see file-level
  // comment above). 11 tokens were consumed (the 10-request burst plus the
  // UI send that tripped the limit); a fixed 60s wait covers a full
  // capacity/refill cycle at rate_limit_chat_refill_per_minute=10 with
  // margin, regardless of how much already regenerated during the
  // toBeEnabled wait above.
  await page.waitForTimeout(60000)
})
