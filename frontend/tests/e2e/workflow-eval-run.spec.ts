import { test, expect } from '@playwright/test'

// Validates issue #84 slice B: an admin creates a workflow whose YAML
// declares a test case, runs its evals from the Workflows screen, and sees
// the case's pass rate and the run's verdict - without publishing anything.
//
// Uses a freshly named workflow per run (same reason as workflows.spec.ts).
//
// Content-independent: the test case makes only a structural check (which
// branch a route step took). Under CI's fake provider the classifier's
// reply names no branch, so the route deterministically falls back to its
// first branch, `alpha`; a real model is told to answer `alpha`. Either way
// the assertion is about how the workflow ran, never what the model said.
// Runs pre-authenticated via storageState (see playwright.config.ts).

test.describe('Workflow eval runs (issue #84)', () => {
  test('an admin runs a version’s test cases and sees each case’s pass rate and the verdict', async ({
    page,
  }) => {
    const name = `e2e_eval_${Date.now()}`
    await page.goto('/')
    await page.locator('button:has-text("Workflows")').click()
    await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible({ timeout: 10000 })

    await page.getByRole('button', { name: 'New workflow' }).click()
    await page.getByLabel('Workflow YAML').fill(
      [
        `name: ${name}`,
        'version: 1',
        'entry: classify',
        'steps:',
        '  classify:',
        '    type: route',
        '    prompt: Always answer with exactly one word, alpha.',
        '    branches:',
        '      alpha: answer_alpha',
        '      beta: answer_beta',
        '  answer_alpha:',
        '    type: agent',
        '    prompt: You are the alpha specialist.',
        '  answer_beta:',
        '    type: agent',
        '    prompt: You are the beta specialist.',
        'tests:',
        '  - name: routes_to_alpha',
        '    input: Which specialist should answer this?',
        '    runs: 2',
        '    expect:',
        '      route: {step: classify, branch: alpha}',
        '',
      ].join('\n')
    )
    await page.getByLabel('Change note').fill('workflow with a test case for the e2e eval run')
    await page.getByRole('button', { name: 'Create workflow' }).click()
    await expect(page.getByRole('status')).toContainText(`Created ${name}`, { timeout: 10000 })

    await page.getByRole('button', { name: 'Run evals on v1' }).click()
    const evalPanel = page.getByRole('region', { name: 'Eval run' })
    await expect(evalPanel.getByRole('heading', { name: `Eval run: ${name} v1` })).toBeVisible()
    await evalPanel.getByRole('button', { name: 'Start eval run' }).click()

    await expect(evalPanel.getByText('Eval run passed')).toBeVisible({ timeout: 60000 })
    const caseRow = evalPanel.getByRole('row', { name: /routes_to_alpha/ })
    await expect(caseRow).toContainText('2 of 2 runs passed')
    await expect(caseRow).toContainText('Passed')

    // Running evals did not publish anything.
    await expect(page.getByRole('button', { name: 'Publish v1' })).toBeVisible()
    await evalPanel.getByRole('button', { name: 'Close' }).click()
    await expect(evalPanel).toHaveCount(0)
  })
})
