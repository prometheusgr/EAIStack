import { test, expect, type Page } from '@playwright/test'
import { startNewChat } from './helpers'

// Validates issue #85: a workflow an admin publishes on the Workflows screen
// shows up in chat's workflow picker, a new conversation started with it is
// answered by it, and the conversation then shows the workflow it is bound
// to instead of a picker (the binding is fixed on the server).
//
// Uses a freshly named workflow per run rather than republishing a built-in,
// so no other spec's chat runs against a changed workflow (AGENTS.md's
// "start from a clean, known state" convention). Content-independent (no
// assertion on what the model says), so it runs under CI's fake provider.
// Runs pre-authenticated via storageState (see playwright.config.ts).

async function createAndPublishWorkflow(page: Page, name: string) {
  await page.goto('/')
  await page.locator('button:has-text("Workflows")').click()
  await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible({ timeout: 10000 })

  await page.getByRole('button', { name: 'New workflow' }).click()
  await page.getByLabel('Workflow YAML').fill(
    [
      `name: ${name}`,
      'version: 1',
      'description: A workflow published by the e2e suite.',
      'entry: respond',
      'steps:',
      '  respond:',
      '    type: agent',
      '    prompt: You are a test workflow.',
      '',
    ].join('\n')
  )
  await page.getByLabel('Change note').fill('created by the e2e suite')
  await page.getByRole('button', { name: 'Create workflow' }).click()
  await expect(page.getByRole('status')).toContainText(`Created ${name}`, { timeout: 10000 })

  await page.getByRole('button', { name: 'Publish v1' }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Publish' }).click()
  await expect(page.getByRole('status')).toContainText(`Published v1 of ${name}`, {
    timeout: 10000,
  })
}

test.describe('Workflow selection in chat (issue #85)', () => {
  test('a published workflow can be picked for a new conversation, which stays bound to it', async ({
    page,
  }) => {
    const name = `e2e_pick_${Date.now()}`
    await createAndPublishWorkflow(page, name)

    const chatInput = await startNewChat(page)
    const picker = page.getByLabel('Workflow', { exact: true })
    await expect(picker.locator(`option[value="${name}"]`)).toHaveCount(1, { timeout: 10000 })
    await picker.selectOption(name)
    await expect(page.getByText('A workflow published by the e2e suite.')).toBeVisible()

    await chatInput.fill(`workflow selection check ${Date.now()}`)
    await page.locator('button:has-text("Send")').click()
    await expect(page.locator('.message-agent')).toHaveCount(1, { timeout: 30000 })

    await expect(page.getByText(`Workflow: ${name}`)).toBeVisible()
    await expect(picker).toHaveCount(0)
    await expect(page.getByLabel('Select conversation').locator('option:checked')).toContainText(
      name
    )
  })
})
