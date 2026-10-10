import { test, expect } from '@playwright/test'

// Validates issue #84 slice A: an admin opens a draft test chat for an
// unpublished workflow version from the Workflows screen, sends a message,
// and gets a reply labelled as a draft run - without publishing anything.
//
// Uses a freshly named workflow per run (same reason as workflows.spec.ts):
// testing a `chat` draft would leave a draft behind in the workflow every
// chat-based spec runs. Its version is never published, so it never appears
// in chat's workflow picker either.
//
// Content-independent: it asserts on the draft-run label, never on what
// the model said, so it runs under CI's fake provider.
// Runs pre-authenticated via storageState (see playwright.config.ts).

test.describe('Draft test chat (issue #84)', () => {
  test('an admin test-runs an unpublished draft and the reply is labelled a draft run', async ({
    page,
  }) => {
    const name = `e2e_draft_${Date.now()}`
    await page.goto('/')
    await page.locator('button:has-text("Workflows")').click()
    await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible({ timeout: 10000 })

    await page.getByRole('button', { name: 'New workflow' }).click()
    await page.getByLabel('Workflow YAML').fill(
      [
        `name: ${name}`,
        'version: 1',
        'entry: respond',
        'steps:',
        '  respond:',
        '    type: agent',
        '    prompt: You are a draft workflow under test.',
        '',
      ].join('\n')
    )
    await page.getByLabel('Change note').fill('draft for the e2e test chat')
    await page.getByRole('button', { name: 'Create workflow' }).click()
    await expect(page.getByRole('status')).toContainText(`Created ${name}`, { timeout: 10000 })

    await page.getByRole('button', { name: 'Test v1' }).click()
    const testRun = page.getByRole('region', { name: 'Draft test run' })
    await expect(
      testRun.getByRole('heading', { name: `Draft test run: ${name} v1` })
    ).toBeVisible()

    await testRun.getByLabel('Test message').fill('Hello from the e2e suite')
    await testRun.getByRole('button', { name: 'Send' }).click()
    await expect(testRun.getByText('Draft run · v1')).toBeVisible({ timeout: 30000 })

    // Running the draft did not publish it: v1 is still offered for publishing.
    await expect(page.getByRole('button', { name: 'Publish v1' })).toBeVisible()
    await expect(page.getByRole('button', { name: new RegExp(`^${name}`) })).toContainText(
      'unpublished'
    )
  })
})
