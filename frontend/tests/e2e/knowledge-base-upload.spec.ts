import { test, expect } from '@playwright/test'
import { writeFileSync, mkdtempSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

// Validates issue #13's file-upload flow through the real UI, backend, and
// MinIO -- not a mocked service layer. Unit tests already cover the upload
// endpoint's logic (content-type/size validation, text extraction,
// MinIO storage) with a fake DocumentStore; this is the "does it actually
// work end to end" check per AGENTS.md's e2e-after-green process.

async function login(page: import('@playwright/test').Page) {
  await page.goto('/')
  await page.locator('button:has-text("Login")').click()
  await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
  await page.locator('input[name="username"]').fill('testuser')
  await page.locator('input[name="password"]').fill('testpassword')
  await page.locator('input[type="submit"]').click()
  await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
}

test.describe('Knowledge base file upload', () => {
  test('uploading a .txt file creates a document visible in the list', async ({ page }) => {
    await login(page)

    await page.locator('button:has-text("Embeddings")').click()
    await expect(page.getByRole('heading', { name: 'Embeddings' })).toBeVisible()

    await page.getByRole('tab', { name: /upload file/i }).click()

    // Unique per run: the seeded testuser's documents persist across e2e
    // runs (same Postgres/MinIO), so a fixed filename could already be in
    // the list from a previous run.
    const uniqueName = `e2e-upload-${Date.now()}.txt`
    const dir = mkdtempSync(join(tmpdir(), 'eaistack-e2e-'))
    const filePath = join(dir, uniqueName)
    writeFileSync(filePath, 'Uploaded via Playwright e2e test.')

    await page.getByLabel(/choose file/i).setInputFiles(filePath)
    await page.getByRole('button', { name: /^upload$/i }).click()

    await expect(page.getByText(uniqueName)).toBeVisible({ timeout: 10000 })
  })

  test('uploading an unsupported file type shows an error and does not add a row', async ({
    page,
  }) => {
    await login(page)

    await page.locator('button:has-text("Embeddings")').click()
    await page.getByRole('tab', { name: /upload file/i }).click()

    const uniqueName = `e2e-rejected-${Date.now()}.bin`
    const dir = mkdtempSync(join(tmpdir(), 'eaistack-e2e-'))
    const filePath = join(dir, uniqueName)
    writeFileSync(filePath, Buffer.from([0x00, 0x01, 0x02, 0x03]))

    await page.getByLabel(/choose file/i).setInputFiles(filePath)
    await page.getByRole('button', { name: /^upload$/i }).click()

    await expect(page.getByText(/unsupported file type/i)).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(uniqueName)).not.toBeVisible()
  })
})
