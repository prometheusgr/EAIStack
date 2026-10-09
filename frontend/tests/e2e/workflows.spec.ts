import { test, expect } from '@playwright/test'

// Validates issue #83: an admin can create, draft and publish a workflow
// from the Workflows screen against the real backend, and every step lands
// in the real audit trail visible on the Audit Log screen.
//
// Uses a freshly named workflow per run rather than editing `chat`: the
// seeded admin's database is shared by every spec in this suite (AGENTS.md's
// "start from a clean, known state" convention), and publishing a different
// `chat` prompt would change what every chat-based spec runs against. A new
// workflow left behind only adds an entry to chat's workflow picker (issue
// #85); nothing else selects it.
//
// Content-independent (no LLM call), so it runs under CI's fake provider.
// Runs pre-authenticated via storageState (see playwright.config.ts).

async function openWorkflows(page: import('@playwright/test').Page) {
  await page.locator('button:has-text("Workflows")').click()
  await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible({ timeout: 10000 })
}

test.describe('Admin workflow store (issue #83)', () => {
  test('the shipped built-ins are listed with an active version', async ({ page }) => {
    await page.goto('/')
    await openWorkflows(page)

    await expect(page.getByRole('button', { name: /^chat/ })).toContainText(/v\d+ · /)
  })

  test('an admin creates a workflow, publishes it, and sees it in the audit log', async ({
    page,
  }) => {
    const name = `e2e_${Date.now()}`
    await page.goto('/')
    await openWorkflows(page)

    await page.getByRole('button', { name: 'New workflow' }).click()
    const editor = page.getByLabel('Workflow YAML')
    await editor.fill(
      [
        `name: ${name}`,
        'version: 1',
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

    // A broken edit is refused with the field named, and nothing is saved.
    await editor.fill(`name: ${name}\nversion: 1\nentry: nowhere\nsteps:\n  respond:\n    type: agent\n    prompt: x\n`)
    await page.getByLabel('Change note').fill('broken edit')
    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page.getByRole('alert')).toContainText('entry', { timeout: 10000 })

    await page.getByRole('button', { name: 'Publish v1' }).click()
    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toContainText(`Publish v1 of ${name}?`)
    await dialog.getByRole('button', { name: 'Publish' }).click()
    await expect(page.getByRole('status')).toContainText(`Published v1 of ${name}`, {
      timeout: 10000,
    })
    await expect(page.getByRole('row', { name: /v1/ }).first()).toContainText('Active')

    await page.locator('button:has-text("Audit Log")').click()
    await expect(page.getByRole('heading', { name: 'Audit Log' })).toBeVisible({ timeout: 10000 })
    const publishedRow = page
      .getByRole('row', { name: new RegExp(`workflow\\.published.*${name}`) })
      .first()
    await expect(publishedRow).toBeVisible({ timeout: 10000 })
    await expect(
      page.getByRole('row', { name: new RegExp(`workflow\\.created.*${name}`) }).first()
    ).toBeVisible()
  })
})
