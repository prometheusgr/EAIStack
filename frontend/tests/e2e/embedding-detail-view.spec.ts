import { test, expect } from '@playwright/test'

// Validates the embeddings list -> detail flow: clicking a document's title
// opens its full content for review, and "Back" returns to the list. Unit
// tests (EmbeddingsList.test.tsx, EmbeddingDetail.test.tsx) already cover
// this with a mocked service layer; this proves the real click-through works
// against the real backend, per AGENTS.md's e2e-after-green process.
//
// Runs in the 'chromium' project, pre-authenticated via storageState (see
// playwright.config.ts and tests/e2e/auth.setup.ts) -- issue #53 -- so
// each test navigates to '/' directly rather than performing a real login.

// Fills a field and confirms the value actually committed, retrying the
// fill itself (not just waiting) if it didn't. Under React StrictMode's
// dev-mode double-render, a fill() issued while a re-render is in flight
// has occasionally been observed to be silently lost -- the field is left
// empty even though a later field's fill in the same sequence succeeds --
// which otherwise surfaces as a confusing 30s timeout on the (still
// disabled) Create Entry button rather than the real, empty-field cause.
async function fillAndVerify(field: import('@playwright/test').Locator, value: string) {
  for (let attempt = 0; attempt < 3; attempt++) {
    await field.fill(value)
    if ((await field.inputValue()) === value) return
  }
  await expect(field).toHaveValue(value)
}

async function createDocument(page: import('@playwright/test').Page, title: string, content: string) {
  await fillAndVerify(page.getByLabel(/title/i), title)
  await fillAndVerify(page.getByLabel(/content/i), content)

  await page.getByRole('button', { name: /create entry/i }).click()
}

test.describe('Embeddings list -> detail view', () => {
  test('clicking a document title shows its content', async ({ page }) => {
    await page.goto('/')

    await page.locator('button:has-text("Embeddings")').click()
    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible()

    // Unique per run: the seeded testuser's documents persist across e2e
    // runs (same Postgres), so a fixed title could already be in the list
    // from a previous run.
    const uniqueTitle = `e2e-detail-${Date.now()}`
    const bodyText = 'Content created by the embedding detail view e2e test.'
    await createDocument(page, uniqueTitle, bodyText)

    const titleLink = page.getByRole('button', { name: uniqueTitle })
    await expect(titleLink).toBeVisible({ timeout: 10000 })
    await titleLink.click()

    await expect(page.getByRole('heading', { name: uniqueTitle })).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(bodyText)).toBeVisible()

    // The detail view replaces the list's own "Embeddings" heading rather
    // than stacking underneath it -- a prior version of this screen left
    // the list's static heading visible above the document's own title.
    await expect(page.getByRole('heading', { name: 'Embeddings' })).not.toBeVisible()
  })

  test('Back returns to the list', async ({ page }) => {
    await page.goto('/')

    await page.locator('button:has-text("Embeddings")').click()
    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible()

    const uniqueTitle = `e2e-detail-back-${Date.now()}`
    await createDocument(page, uniqueTitle, 'Content for the Back-navigation e2e test.')

    const titleLink = page.getByRole('button', { name: uniqueTitle })
    await expect(titleLink).toBeVisible({ timeout: 10000 })
    await titleLink.click()

    await expect(page.getByRole('heading', { name: uniqueTitle })).toBeVisible({ timeout: 10000 })

    await page.getByRole('button', { name: /back/i }).click()

    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible()
    await expect(titleLink).toBeVisible()
  })

  test('deleting a document from the detail view removes it from the list', async ({ page }) => {
    await page.goto('/')

    await page.locator('button:has-text("Embeddings")').click()
    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible()

    const uniqueTitle = `e2e-detail-delete-${Date.now()}`
    await createDocument(page, uniqueTitle, 'Content for the delete-from-detail e2e test.')

    const titleLink = page.getByRole('button', { name: uniqueTitle })
    await expect(titleLink).toBeVisible({ timeout: 10000 })
    await titleLink.click()

    await expect(page.getByRole('heading', { name: uniqueTitle })).toBeVisible({ timeout: 10000 })

    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: 'Delete Document' }).click()

    // The delete returns straight to the list (no separate Back click) and
    // the deleted document must not reappear -- it previously stayed in the
    // list's in-memory state until a full page reload.
    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: uniqueTitle })).not.toBeVisible()
  })
})
