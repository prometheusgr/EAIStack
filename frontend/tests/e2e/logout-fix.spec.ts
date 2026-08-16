import { test, expect } from '@playwright/test'

test.describe('Logout Fix - Verify Session Clearing', () => {
  test('logout actually logs out - can login again', async ({ page, context }) => {
    console.log('[test] === FIRST LOGIN ===')
    await page.goto('/')

    // Check we're at login screen
    let loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible({ timeout: 5000 })
    console.log('[test] ✓ At login screen')

    // Click login
    await loginBtn.click()
    console.log('[test] Clicked login button')

    // Wait for Keycloak and fill form
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    console.log('[test] ✓ At Keycloak')

    // Add more specific selector for submit button
    const submitBtn = page.locator('button[type="submit"], button[class*="submit"], input[type="submit"]').first()
    await expect(submitBtn).toBeVisible({ timeout: 5000 })

    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    console.log('[test] ✓ Filled credentials')

    await submitBtn.click()
    console.log('[test] ✓ Clicked submit')

    // Wait for redirect back
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })
    console.log('[test] ✓ FIRST LOGIN SUCCESSFUL')

    // Get localStorage before logout
    const storageBeforeLogout = await page.evaluate(() => ({
      access_token: localStorage.getItem('access_token'),
      all_keys: Object.keys(localStorage),
    }))
    console.log('[test] Storage before logout:', storageBeforeLogout)

    console.log('[test] === FIRST LOGOUT ===')
    const logoutBtn = page.locator('button:has-text("Logout")')
    await expect(logoutBtn).toBeVisible()
    await logoutBtn.click()
    console.log('[test] Clicked logout')

    // Wait for redirect after logout
    await page.waitForTimeout(3000)

    // Check URL - should be back at app
    console.log('[test] Current URL:', page.url())

    // Wait for page to settle
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    const urlAfterLogout = page.url()
    console.log('[test] ✓ Redirected back to app, URL:', urlAfterLogout)

    // Wait for React to update
    await page.waitForTimeout(2000)

    // Check storage after logout
    const storageAfterLogout = await page.evaluate(() => ({
      access_token: localStorage.getItem('access_token'),
      all_keys: Object.keys(localStorage),
    }))
    console.log('[test] Storage after logout:', storageAfterLogout)

    // Must be null
    if (storageAfterLogout.access_token !== null) {
      console.error('[test] ✗ PROBLEM: Token still in storage after logout!')
    } else {
      console.log('[test] ✓ Token cleared from storage')
    }

    // Check if logout button is gone (should see login button)
    const logoutBtnAfter = page.locator('button:has-text("Logout")')
    const logoutVisible = await logoutBtnAfter.isVisible().catch(() => false)
    console.log('[test] Logout button visible after logout?', logoutVisible)

    // Should see login button
    const loginBtnAfter = page.locator('button:has-text("Login")')
    try {
      await expect(loginBtnAfter).toBeVisible({ timeout: 5000 })
      console.log('[test] ✓ Login button visible after logout')
    } catch (e) {
      console.error('[test] ✗ PROBLEM: Login button NOT visible after logout')
      console.error('[test] Page content:', await page.locator('body').textContent())
      throw e
    }

    console.log('[test] === SECOND LOGIN ===')

    // Start listening to console messages
    page.on('console', msg => {
      if (msg.text().includes('[Auth]')) {
        console.log('[browser]', msg.text())
      }
    })

    // Check page content
    const pageContent = await page.locator('body').textContent()
    console.log('[test] Page content before second login:', pageContent?.substring(0, 200))

    // Check localStorage BEFORE clicking login
    const storageBeforeSecondLogin = await page.evaluate(() => localStorage.getItem('access_token'))
    console.log('[test] Access token in storage before second login attempt?', !!storageBeforeSecondLogin)
    if (storageBeforeSecondLogin) {
      console.error('[test] ✗ BUG: Token still in storage!')
    }

    // Try to login again
    const loginBtnAfter2 = page.locator('button:has-text("Login")')
    console.log('[test] Login button visible?', await loginBtnAfter2.isVisible())
    console.log('[test] Login button count:', await page.locator('button:has-text("Login")').count())

    // Set up a promise to detect if we navigate away
    let navigatedAway = false
    const navigationPromise = page.waitForNavigation({ timeout: 5000 }).then(() => {
      navigatedAway = true
      console.log('[test] PAGE NAVIGATED')
    }).catch(() => {
      console.log('[test] No navigation after click')
    })

    console.log('[test] About to click login button')
    await loginBtnAfter2.click()
    console.log('[test] Clicked login button again')

    // Wait a bit for navigation to start
    await page.waitForTimeout(1000)
    console.log('[test] navigatedAway after click?', navigatedAway)

    // Wait for navigation
    await page.waitForTimeout(2000)
    console.log('[test] Current URL after click:', page.url())

    // Check if we actually navigated
    const bodyContent = await page.locator('body').textContent()
    console.log('[test] Page content after login click:', bodyContent?.substring(0, 200))

    // Should reach Keycloak again
    try {
      await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
      console.log('[test] ✓ Reached Keycloak login form')
    } catch (e) {
      console.error('[test] ✗ PROBLEM: Did not reach Keycloak after logout+login')
      console.error('[test] Current URL:', page.url())
      throw e
    }

    // Fill form again
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    console.log('[test] ✓ Filled credentials again')

    // Click submit
    const submitBtn2 = page.locator('button[type="submit"], button[class*="submit"], input[type="submit"]').first()
    await submitBtn2.click()
    console.log('[test] ✓ Clicked submit again')

    // Should redirect back again
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })
    console.log('[test] ✓ SECOND LOGIN SUCCESSFUL')

    console.log('[test] === TEST PASSED - LOGOUT WORKING CORRECTLY ===')
  })
})
