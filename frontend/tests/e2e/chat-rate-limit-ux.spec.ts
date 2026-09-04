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
// (rate_limit_chat_capacity=10, see app/core/config.py) and refills slowly,
// so tripping it requires firing many requests back-to-back -- only
// feasible at fake-provider latency, not against a real llama-server.
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts) -- issue #53.

test('a chat send throttled by the rate limiter shows a distinguishable countdown banner, distinct from a guardrail rejection', async ({
  page,
}) => {
  test.setTimeout(60000)
  const chatInput = await startNewChat(page)
  const sendButton = page.locator('button:has-text("Send")')

  let rateLimited = false
  for (let i = 0; i < 20 && !rateLimited; i++) {
    await chatInput.fill(`Rate limit probe message ${Date.now()}-${i}`)
    await sendButton.click()

    const rateLimitBanner = page.getByRole('alert', { name: 'Rate limit reached' })
    if (await rateLimitBanner.isVisible({ timeout: 500 }).catch(() => false)) {
      rateLimited = true
      break
    }

    // Wait for the fake provider's response (or a guardrail/other error) to
    // resolve before sending the next probe, so requests queue one at a
    // time against the token bucket rather than racing each other.
    await page
      .getByText(/agent is thinking/i)
      .waitFor({ state: 'hidden', timeout: 10000 })
      .catch(() => {})
  }

  expect(rateLimited).toBe(true)

  const rateLimitBanner = page.getByRole('alert', { name: 'Rate limit reached' })
  await expect(rateLimitBanner).toBeVisible()

  // Distinguishable from a guardrail rejection: different aria-label/icon,
  // never the guardrail's "couldn't be sent" copy.
  await expect(page.getByRole('alert', { name: 'Message rejected by content safety rule' })).not.toBeVisible()

  // The Send button reflects the countdown and is disabled while it runs.
  const sendButtonLabel = await sendButton.textContent()
  expect(sendButtonLabel).toMatch(/retry in \d+s/i)
  await expect(sendButton).toBeDisabled()

  // The countdown eventually elapses and Send becomes usable again.
  await expect(sendButton).toBeEnabled({ timeout: 65000 })
  await expect(sendButton).toHaveText(/^send$/i)
})
