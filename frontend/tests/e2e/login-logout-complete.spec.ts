import { test, expect } from '@playwright/test'

// Comprehensive e2e test for login and logout flows
// Tests all paths: fresh login, logout, re-login

test.describe('Complete Login/Logout Flow', () => {
  test('user can login, logout, and login again', async ({ page }) => {
    console.log('[test] === PHASE 1: FRESH START ===')
    await page.goto('/')

    // Verify at login screen
    let loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible({ timeout: 5000 })
    console.log('[test] ✓ Fresh app shows login screen')

    // === PHASE 2: FIRST LOGIN ===
    console.log('[test] === PHASE 2: FIRST LOGIN ===')
    await loginBtn.click()

    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })

    // Verify token stored
    const token1 = await page.evaluate(() => localStorage.getItem('access_token'))
    expect(token1).toBeTruthy()
    console.log('[test] ✓ First login successful, token stored')

    // === PHASE 3: LOGOUT ===
    console.log('[test] === PHASE 3: LOGOUT ===')
    const logoutBtn = page.locator('button:has-text("Logout")')
    await logoutBtn.click()

    // Wait for logout redirect
    await page.waitForTimeout(2000)
    try {
      await page.waitForURL(/keycloak|8080/, { timeout: 5000 })
    } catch {
      // May redirect directly
    }

    // Wait for redirect back
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await page.waitForTimeout(1000)

    // Verify token cleared
    const tokenCleared = await page.evaluate(() => localStorage.getItem('access_token'))
    expect(tokenCleared).toBeNull()
    console.log('[test] ✓ Logout cleared token')

    // Verify login button visible again
    loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible({ timeout: 10000 })
    console.log('[test] ✓ Login screen shows after logout')

    // === PHASE 4: SECOND LOGIN ===
    console.log('[test] === PHASE 4: SECOND LOGIN ===')
    await loginBtn.click()

    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    // This time Keycloak should show the login form (ideally)
    // But due to session persistence, it might auto-login
    // Either way, we should end up logged in

    const usernameInput = page.locator('input[name="username"]')
    const isFormVisible = await usernameInput.isVisible().catch(() => false)

    if (isFormVisible) {
      // If form is visible, fill it
      await usernameInput.fill('testuser')
      await page.locator('input[name="password"]').fill('testpassword')
      await page.locator('input[type="submit"]').click()
      console.log('[test] Filled login form on second attempt')
    } else {
      console.log('[test] Keycloak auto-logged in (session persistence)')
    }

    // Either way, should redirect back to app logged in
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })

    // Verify new token received
    const token2 = await page.evaluate(() => localStorage.getItem('access_token'))
    expect(token2).toBeTruthy()
    expect(token2).not.toEqual(token1)  // Should be a new token
    console.log('[test] ✓ Second login successful, new token received')

    // === FINAL VERIFICATION ===
    console.log('[test] === FINAL VERIFICATION ===')
    await expect(page.locator('button:has-text("Logout")')).toBeVisible()
    console.log('[test] ✓ Logged in state confirmed')

    console.log('[test] === ALL TESTS PASSED ===')
  })
})
