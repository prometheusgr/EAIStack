import { test, expect } from '@playwright/test'

/**
 * E2E Test: Verify No Infinite Redirect Loop
 *
 * This test validates the fix for the infinite redirect loop issue.
 * It ensures that:
 * 1. Page loads without redirect
 * 2. Login button appears
 * 3. Only ONE redirect happens when user clicks login
 */

test.describe('No Infinite Redirect Loop', () => {
  test('should load page without redirecting to Keycloak', async ({ page }) => {
    // CRITICAL: Page should load and show login button
    // If this redirects, the fix is not working

    const redirects: string[] = []

    // Track all redirects
    page.on('framenavigated', (frame) => {
      const url = frame.url()
      redirects.push(url)
      console.log('[E2E] Navigation to:', url)
    })

    // Navigate to home
    console.log('[E2E] Navigating to http://localhost:3000')
    await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded' })

    // Wait a moment for any auto-redirects
    await page.waitForTimeout(2000)

    // Get final URL
    const finalUrl = page.url()
    console.log('[E2E] Final URL after 2 seconds:', finalUrl)

    // ASSERT: Should still be on localhost:3000 (not redirected to Keycloak)
    expect(finalUrl).toContain('localhost:3000')
    expect(finalUrl).not.toContain('8080') // Should not contain Keycloak port

    // ASSERT: Login button should be visible (user not authenticated)
    const loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible({ timeout: 5000 })

    console.log('[E2E] ✓ No redirect loop - login button visible')
  })

  test('should only redirect to Keycloak when user clicks login', async ({ page }) => {
    // Load page
    await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1000)

    const beforeLoginUrl = page.url()
    console.log('[E2E] Before login URL:', beforeLoginUrl)
    expect(beforeLoginUrl).not.toContain('8080')

    // Wait for login button
    const loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible({ timeout: 5000 })

    // Click login - NOW should redirect to Keycloak
    console.log('[E2E] Clicking login button...')
    await loginBtn.click()

    // Should redirect to Keycloak
    console.log('[E2E] Waiting for Keycloak redirect...')
    await page.waitForURL(/8080.*auth/, { timeout: 10000 })

    const afterLoginUrl = page.url()
    console.log('[E2E] After login click URL:', afterLoginUrl)

    // ASSERT: Only redirected after clicking login button (not on page load)
    expect(afterLoginUrl).toContain('8080')
    expect(afterLoginUrl).toContain('client_id=eaistack-web')

    console.log('[E2E] ✓ Redirect only happens after login click')
  })

  test('should not have error=login_required in initial page load', async ({ page }) => {
    // Monitor console for auth errors
    const consoleMessages: string[] = []
    page.on('console', (msg) => {
      consoleMessages.push(msg.text())
      if (msg.text().includes('[Auth]')) {
        console.log('[E2E]', msg.text())
      }
    })

    // Load page
    await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)

    // Check URL
    const url = page.url()
    console.log('[E2E] Final URL:', url)

    // ASSERT: Should NOT have error parameter
    expect(url).not.toContain('error=login_required')
    expect(url).not.toContain('error=')

    // Check console for error messages
    const hasError = consoleMessages.some((msg) => msg.includes('error=login_required'))
    expect(hasError).toBe(false)

    console.log('[E2E] ✓ No error=login_required in page load')
  })

  test('should show login button, not infinite loop', async ({ page }) => {
    await page.goto('http://localhost:3000')

    // Give page time to load
    await page.waitForTimeout(3000)

    // Check for login button
    const loginBtn = page.locator('button:has-text("Login")')
    const isVisible = await loginBtn.isVisible()

    if (!isVisible) {
      // If login button not visible, check current URL
      const url = page.url()
      console.log('[E2E] ERROR: Login button not found. Current URL:', url)

      // Check if we're stuck in redirect loop
      if (url.includes('error=login_required')) {
        throw new Error('INFINITE LOOP DETECTED: error=login_required in URL')
      }
    }

    expect(isVisible).toBe(true)
    console.log('[E2E] ✓ Login button visible - fix is working')
  })
})
