import { test, expect } from '@playwright/test'
import { login } from './helpers'

// Validates the embeddings list -> detail flow: clicking a document's title
// opens its full content for review, and "Back" returns to the list. Unit
// tests (EmbeddingsList.test.tsx, EmbeddingDetail.test.tsx) already cover
// this with a mocked service layer; this proves the real click-through works
// against the real backend, per AGENTS.md's e2e-after-green process.

test.describe('Embeddings list -> detail view', () => {
  test('clicking a document title shows its content, and Back returns to the list', async ({
    page,
  }) => {
    await login(page)

    await page.locator('button:has-text("Embeddings")').click()
    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible()

    // Unique per run: the seeded testuser's documents persist across e2e
    // runs (same Postgres), so a fixed title could already be in the list
    // from a previous run.
    const uniqueTitle = `e2e-detail-${Date.now()}`
    const bodyText = 'Content created by the embedding detail view e2e test.'

    await page.getByLabel(/title/i).fill(uniqueTitle)
    await page.getByLabel(/content/i).fill(bodyText)
    await page.getByRole('button', { name: /create entry/i }).click()

    const titleLink = page.getByRole('button', { name: uniqueTitle })
    await expect(titleLink).toBeVisible({ timeout: 10000 })

    await titleLink.click()

    await expect(page.getByRole('heading', { name: uniqueTitle })).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(bodyText)).toBeVisible()

    await page.getByRole('button', { name: /back/i }).click()

    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible()
    await expect(titleLink).toBeVisible()
  })
})
