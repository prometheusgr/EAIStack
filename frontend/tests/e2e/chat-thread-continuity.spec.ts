import { test, expect } from '@playwright/test'
import { startNewChat } from './helpers'

// A follow-up message continues the same conversation instead of silently
// starting a new one. The frontend used to send `threadId` while the backend
// reads `thread_id`; the field was dropped, so every message created a new
// thread and the model never saw earlier turns. Content-independent (no
// assertion on what the model says), so it runs under CI's fake provider.
//
// Runs pre-authenticated via storageState (see playwright.config.ts).

const conversationPicker = (page: import('@playwright/test').Page) =>
  page.getByLabel('Select conversation')

async function send(page: import('@playwright/test').Page, text: string) {
  const turnsBefore = await page.locator('.message-agent').count()
  await page.locator('input[placeholder="Type your message..."]').fill(text)
  await page.locator('button:has-text("Send")').click()
  await expect(page.locator('.message-agent')).toHaveCount(turnsBefore + 1, {
    timeout: 30000,
  })
}

test.describe('Chat thread continuity', () => {
  test('a follow-up message stays in the same conversation', async ({ page }) => {
    await startNewChat(page)

    await send(page, `continuity check ${Date.now()} - first`)
    const threadAfterFirst = await conversationPicker(page).inputValue()
    const conversationsAfterFirst = await conversationPicker(page).locator('option').count()

    await send(page, 'and a follow-up in the same conversation')

    expect(threadAfterFirst).not.toBe('')
    await expect(conversationPicker(page)).toHaveValue(threadAfterFirst)
    await expect(conversationPicker(page).locator('option')).toHaveCount(conversationsAfterFirst)
  })
})
