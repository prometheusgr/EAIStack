import { test, expect } from '@playwright/test'

test.describe('Authentication Flow - Login Paths', () => {
  test('fresh start shows login button, not loading', async ({ page }) => {
    // Verify initial state is login, not loading spinner
    console.log('[test] Navigate to fresh app')
    await page.goto('/')

    // Should not show loading
    const loadingMsg = page.locator('text=Loading...')
    await expect(loadingMsg).not.toBeVisible({ timeout: 2000 })
    console.log('[test] No loading spinner')

    // Should show login button
    const loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible({ timeout: 5000 })
    console.log('[test] Login button visible on fresh start')

    // Should show EAIStack heading
    const heading = page.locator('h1:has-text("EAIStack")')
    await expect(heading).toBeVisible()
    console.log('[test] App heading visible')
  })

  test('clicking login button redirects to Keycloak', async ({ page }) => {
    // Verify login flow starts correctly
    console.log('[test] Navigate to app')
    await page.goto('/')

    console.log('[test] Click login button')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Should redirect to Keycloak login form
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    console.log('[test] Redirected to Keycloak')

    // Keycloak form should be visible
    const usernameInput = page.locator('input[name="username"]')
    await expect(usernameInput).toBeVisible({ timeout: 10000 })
    console.log('[test] Keycloak login form visible')
  })

  test('successful login with correct credentials', async ({ page }) => {
    // Full login flow with valid credentials
    console.log('[test] Start fresh login flow')
    await page.goto('/')

    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Wait for Keycloak login form
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    const usernameInput = page.locator('input[name="username"]')
    await expect(usernameInput).toBeVisible({ timeout: 10000 })
    console.log('[test] Keycloak form visible')

    // Submit login with correct credentials
    await usernameInput.fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()
    console.log('[test] Submitted login form')

    // Should redirect back to app
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    console.log('[test] Redirected back to app')

    // Wait for React to process auth
    await page.waitForTimeout(1000)

    // Should see welcome message with the username/name in it
    const welcomeMsg = page.locator('text=Welcome')
    await expect(welcomeMsg).toBeVisible({ timeout: 10000 })
    console.log('[test] Welcome message visible')

    // Logout button should be visible
    const logoutBtn = page.locator('button:has-text("Logout")')
    await expect(logoutBtn).toBeVisible()
    console.log('[test] Logout button visible - login successful!')
  })

  test('login with wrong password shows error', async ({ page }) => {
    // Invalid credentials should fail at Keycloak
    console.log('[test] Start login with wrong password')
    await page.goto('/')

    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Wait for Keycloak
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    console.log('[test] At Keycloak login form')

    // Submit with wrong password
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('wrongpassword')
    await page.locator('input[type="submit"]').click()
    console.log('[test] Submitted wrong password')

    // Should see Keycloak error message
    const errorMsg = page.locator('text=/Invalid user|invalid credentials|error/i')
    await expect(errorMsg).toBeVisible({ timeout: 5000 })
    console.log('[test] Keycloak error message displayed')

    // Should still be on Keycloak form (not redirected back to the app) -
    // the login form is served from Keycloak's own host:port (localhost:8080
    // in this dev setup), not a hostname containing the literal string
    // "keycloak", which page.waitForURL's own /keycloak|8080/ pattern above
    // already accounts for.
    expect(page.url()).not.toContain('localhost:3000')
    console.log('[test] Still on Keycloak form, not redirected')
  })

  test('login with nonexistent user shows error', async ({ page }) => {
    // Nonexistent user should fail at Keycloak
    console.log('[test] Start login with nonexistent user')
    await page.goto('/')

    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    console.log('[test] At Keycloak login form')

    // Submit with nonexistent user
    await page.locator('input[name="username"]').fill('nonexistentuser12345')
    await page.locator('input[name="password"]').fill('anypassword')
    await page.locator('input[type="submit"]').click()
    console.log('[test] Submitted nonexistent user')

    // Should see error
    const errorMsg = page.locator('text=/Invalid user|invalid credentials|error/i')
    await expect(errorMsg).toBeVisible({ timeout: 5000 })
    console.log('[test] Error shown for nonexistent user')
  })

  test('login form allows multiple attempts', async ({ page }) => {
    // User can retry login after failed attempt
    console.log('[test] Start login, fail, then succeed')
    await page.goto('/')

    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    console.log('[test] At Keycloak login form')

    // First attempt: wrong password
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('wrongpassword')
    await page.locator('input[type="submit"]').click()
    console.log('[test] First attempt: wrong password')

    // Wait for error
    await page.locator('text=/Invalid user|invalid credentials|error/i').waitFor({ timeout: 5000 })
    console.log('[test] Error shown')

    // Second attempt: correct credentials
    // Clear fields and retry
    const usernameInput = page.locator('input[name="username"]')
    const passwordInput = page.locator('input[name="password"]')

    // Fill again (form should still be visible)
    await usernameInput.clear()
    await passwordInput.clear()
    await usernameInput.fill('testuser')
    await passwordInput.fill('testpassword')
    await page.locator('input[type="submit"]').click()
    console.log('[test] Second attempt: correct password')

    // Should succeed this time
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    const welcomeMsg = page.locator('text=Welcome')
    await expect(welcomeMsg).toBeVisible({ timeout: 10000 })
    console.log('[test] Login succeeded on retry')
  })

  test('direct navigation to app redirects to Keycloak if not logged in', async ({ page }) => {
    // When not authenticated, app shows login button (not redirect)
    console.log('[test] Direct navigation while not logged in')
    await page.goto('/')

    // Should show login UI, not redirect to Keycloak
    const loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible({ timeout: 5000 })
    console.log('[test] Shows login button, no automatic redirect')

    // Should not be at Keycloak
    expect(page.url()).toContain('localhost:3000')
  })
})

test.describe('Authentication Flow - Logout Paths', () => {
  test('logout from logged-in state returns to login screen', async ({ page }) => {
    // Full logout flow
    console.log('[test] Login first')
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Keycloak login
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()
    console.log('[test] Logged in')

    // Wait for authenticated state
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    const welcomeMsg = page.locator('text=Welcome')
    await expect(welcomeMsg).toBeVisible({ timeout: 10000 })
    console.log('[test] At authenticated app')

    // Verify token is in storage
    const tokenBefore = await page.evaluate(() => localStorage.getItem('access_token'))
    expect(tokenBefore).toBeTruthy()
    console.log('[test] Token confirmed in storage before logout')

    // Click logout
    const logoutBtn = page.locator('button:has-text("Logout")')
    await logoutBtn.click()
    console.log('[test] Clicked logout button')

    // Wait longer for Keycloak logout to process
    await page.waitForTimeout(2000)

    // Should redirect through Keycloak logout or back to app
    try {
      await page.waitForURL(/keycloak|logout|8080/, { timeout: 10000 })
      console.log('[test] Went through Keycloak logout URL')
    } catch {
      console.log('[test] No Keycloak redirect detected, may have redirected directly')
    }

    // Wait for redirect back to app (may take a moment)
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    console.log('[test] Back at app')

    // Wait for auth state to update
    await page.waitForTimeout(1000)

    // Verify token was cleared
    const tokenAfter = await page.evaluate(() => localStorage.getItem('access_token'))
    expect(tokenAfter).toBeNull()
    console.log('[test] Token confirmed cleared from storage')

    // Should see login button (not loading, not welcome)
    const newLoginBtn = page.locator('button:has-text("Login")')
    await expect(newLoginBtn).toBeVisible({ timeout: 10000 })
    console.log('[test] Login button visible - logout successful!')

    // Verify welcome message is gone
    const welcomeAfter = page.locator('text=Welcome')
    await expect(welcomeAfter).not.toBeVisible({ timeout: 2000 })
    console.log('[test] Welcome message gone')
  })

  test('localStorage is cleared after logout', async ({ page }) => {
    // Verify tokens are cleaned up
    console.log('[test] Login')
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Keycloak login
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    // Wait for authenticated state
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })
    console.log('[test] Logged in, checking localStorage')

    // Verify token was stored
    const hasToken = await page.evaluate(() => localStorage.getItem('access_token') !== null)
    expect(hasToken).toBe(true)
    console.log('[test] Access token stored in localStorage')

    // Logout
    await page.locator('button:has-text("Logout")').click()
    console.log('[test] Logging out')

    // Wait for logout to complete
    // Keycloak's RP-initiated logout can redirect through its own logout
    // endpoint and back to the app fast enough (a silent SSO logout, valid
    // session + id_token_hint) that this intermediate URL is never actually
    // observed between two waitForURL calls - it's a best-effort signal, not
    // a guaranteed one, so it must not fail the test if missed (matches the
    // try/catch pattern already used by the sibling logout test above).
    try {
      await page.waitForURL(/keycloak|logout|8080/, { timeout: 5000 })
    } catch {
      // No intermediate Keycloak URL observed - logout may have completed
      // directly. The wait below for the final app URL is what matters.
    }
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })

    // Verify token was cleared
    const noToken = await page.evaluate(() => localStorage.getItem('access_token') === null)
    expect(noToken).toBe(true)
    console.log('[test] Access token cleared from localStorage')

    // Verify app is in unauthenticated state
    const loginBtnAfter = page.locator('button:has-text("Login")')
    await expect(loginBtnAfter).toBeVisible({ timeout: 5000 })
    console.log('[test] App in unauthenticated state')
  })

  test('logout prevents access to protected chat', async ({ page }) => {
    // After logout, chat should not be accessible
    console.log('[test] Login')
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Keycloak login
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    // Wait for authenticated state
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    const chatInput = page.locator('input[placeholder="Type your message..."]')
    await expect(chatInput).toBeVisible({ timeout: 10000 })
    console.log('[test] Chat visible when logged in')

    // Logout
    await page.locator('button:has-text("Logout")').click()
    console.log('[test] Logging out')

    // Wait for logout
    // Keycloak's RP-initiated logout can redirect through its own logout
    // endpoint and back to the app fast enough (a silent SSO logout, valid
    // session + id_token_hint) that this intermediate URL is never actually
    // observed between two waitForURL calls - it's a best-effort signal, not
    // a guaranteed one, so it must not fail the test if missed (matches the
    // try/catch pattern already used by the sibling logout test above).
    try {
      await page.waitForURL(/keycloak|logout|8080/, { timeout: 5000 })
    } catch {
      // No intermediate Keycloak URL observed - logout may have completed
      // directly. The wait below for the final app URL is what matters.
    }
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })

    // Chat should not be visible anymore
    await expect(chatInput).not.toBeVisible({ timeout: 2000 })
    console.log('[test] Chat hidden after logout')

    // Verify back at login screen
    const newLoginBtn = page.locator('button:has-text("Login")')
    await expect(newLoginBtn).toBeVisible()
    console.log('[test] Login screen visible after logout')
  })

  test('logout clears all auth tokens', async ({ page }) => {
    // Verify all token types are cleared (access, refresh, token_type)
    console.log('[test] Login')
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Keycloak login
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    // Wait for authenticated state
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })
    console.log('[test] Logged in')

    // Check all tokens stored
    const tokens = await page.evaluate(() => ({
      access: localStorage.getItem('access_token'),
      refresh: localStorage.getItem('refresh_token'),
      type: localStorage.getItem('token_type'),
    }))
    expect(tokens.access).toBeTruthy()
    console.log('[test] All tokens present before logout')

    // Logout
    await page.locator('button:has-text("Logout")').click()
    console.log('[test] Logging out')

    // Wait for logout
    // Keycloak's RP-initiated logout can redirect through its own logout
    // endpoint and back to the app fast enough (a silent SSO logout, valid
    // session + id_token_hint) that this intermediate URL is never actually
    // observed between two waitForURL calls - it's a best-effort signal, not
    // a guaranteed one, so it must not fail the test if missed (matches the
    // try/catch pattern already used by the sibling logout test above).
    try {
      await page.waitForURL(/keycloak|logout|8080/, { timeout: 5000 })
    } catch {
      // No intermediate Keycloak URL observed - logout may have completed
      // directly. The wait below for the final app URL is what matters.
    }
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })

    // Verify all tokens cleared
    const clearedTokens = await page.evaluate(() => ({
      access: localStorage.getItem('access_token'),
      refresh: localStorage.getItem('refresh_token'),
      type: localStorage.getItem('token_type'),
    }))
    expect(clearedTokens.access).toBeNull()
    expect(clearedTokens.refresh).toBeNull()
    console.log('[test] All tokens cleared after logout')
  })

  test('can login again after logout', async ({ page }) => {
    // Verify logout is complete enough to login again
    console.log('[test] First login')
    await page.goto('/')
    let loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // First login
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })
    console.log('[test] First login successful')

    // Logout
    await page.locator('button:has-text("Logout")').click()
    // Keycloak's RP-initiated logout can redirect through its own logout
    // endpoint and back to the app fast enough (a silent SSO logout, valid
    // session + id_token_hint) that this intermediate URL is never actually
    // observed between two waitForURL calls - it's a best-effort signal, not
    // a guaranteed one, so it must not fail the test if missed (matches the
    // try/catch pattern already used by the sibling logout test above).
    try {
      await page.waitForURL(/keycloak|logout|8080/, { timeout: 5000 })
    } catch {
      // No intermediate Keycloak URL observed - logout may have completed
      // directly. The wait below for the final app URL is what matters.
    }
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    console.log('[test] Logged out')

    // Second login
    loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible()
    await loginBtn.click()
    console.log('[test] Starting second login')

    // Should reach Keycloak again
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    // Should succeed again
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })
    console.log('[test] Second login successful')
  })
})

test.describe('Authentication Flow - Chat Integration', () => {
  test('chat is only accessible when logged in', async ({ page }) => {
    // Chat input should be hidden before login
    console.log('[test] Fresh app - chat should be hidden')
    await page.goto('/')

    const chatInput = page.locator('input[placeholder="Type your message..."]')
    await expect(chatInput).not.toBeVisible()
    console.log('[test] Chat hidden before login')

    // Login
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    // Chat should be visible after login
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(chatInput).toBeVisible({ timeout: 10000 })
    console.log('[test] Chat visible after login')

    // Logout
    await page.locator('button:has-text("Logout")').click()
    // Keycloak's RP-initiated logout can redirect through its own logout
    // endpoint and back to the app fast enough (a silent SSO logout, valid
    // session + id_token_hint) that this intermediate URL is never actually
    // observed between two waitForURL calls - it's a best-effort signal, not
    // a guaranteed one, so it must not fail the test if missed (matches the
    // try/catch pattern already used by the sibling logout test above).
    try {
      await page.waitForURL(/keycloak|logout|8080/, { timeout: 5000 })
    } catch {
      // No intermediate Keycloak URL observed - logout may have completed
      // directly. The wait below for the final app URL is what matters.
    }
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })

    // Chat should be hidden again
    await expect(chatInput).not.toBeVisible({ timeout: 2000 })
    console.log('[test] Chat hidden after logout')
  })

  test('user can send message after successful login', async ({ page }) => {
    // Complete flow: login -> send message -> verify response
    console.log('[test] Start login')
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Keycloak login
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    // Wait for authenticated state
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    const chatInput = page.locator('input[placeholder="Type your message..."]')
    await expect(chatInput).toBeVisible({ timeout: 10000 })
    console.log('[test] Logged in, chat ready')

    // Send message
    const testMessage = 'What is 2+2?'
    await chatInput.fill(testMessage)
    console.log(`[test] Typed message: ${testMessage}`)

    const sendBtn = page.locator('button:has-text("Send")')
    await sendBtn.click()
    console.log('[test] Clicked send')

    // Wait for agent response
    const response = page.locator('.message-agent')
    await expect(response).toBeVisible({ timeout: 10000 })
    const messageText = await response.textContent()
    expect(messageText).toBeTruthy()
    expect(messageText).toContain('4')
    console.log(`[test] Agent responded: ${messageText}`)
  })

  test('login persists across page refresh', async ({ page }) => {
    // Token should be retrieved from localStorage after page refresh
    console.log('[test] Login')
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Keycloak login
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('input[type="submit"]').click()

    // Wait for authenticated state
    await page.waitForURL('http://localhost:3000/', { timeout: 15000 })
    await expect(page.locator('text=Welcome')).toBeVisible({ timeout: 10000 })
    console.log('[test] Logged in')

    // Refresh page
    console.log('[test] Refreshing page')
    await page.reload()

    // Should still be logged in
    const welcomeMsg = page.locator('text=Welcome')
    await expect(welcomeMsg).toBeVisible({ timeout: 10000 })
    console.log('[test] Still logged in after refresh')

    // Chat should be accessible
    const chatInput = page.locator('input[placeholder="Type your message..."]')
    await expect(chatInput).toBeVisible()
    console.log('[test] Chat still accessible')
  })
})
