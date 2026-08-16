import { test, expect } from '@playwright/test'

test.describe('Authentication Flow', () => {
  test('user can login and access chat', async ({ page }) => {
    // 1. Navigate to app
    await page.goto('/')
    console.log('[test] Navigated to home page')

    // 2. Should see login button
    const loginBtn = page.locator('button:has-text("Login")')
    await expect(loginBtn).toBeVisible({ timeout: 5000 })
    console.log('[test] Login button visible')

    // 3. Click login - should redirect to Keycloak
    await loginBtn.click()
    console.log('[test] Clicked login button')

    // 4. Wait for Keycloak login form
    // The URL will be something like http://localhost:8080/auth/realms/...
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    console.log('[test] Redirected to Keycloak')

    // 5. Fill username
    const usernameInput = page.locator('input[name="username"]')
    await expect(usernameInput).toBeVisible({ timeout: 5000 })
    await usernameInput.fill('testuser')
    console.log('[test] Filled username')

    // 6. Fill password
    const passwordInput = page.locator('input[name="password"]')
    await passwordInput.fill('testpassword')
    console.log('[test] Filled password')

    // 7. Submit login form
    const submitBtn = page.locator('button[type="submit"]')
    await submitBtn.click()
    console.log('[test] Submitted login form')

    // 8. Should redirect back to app
    await page.waitForURL('http://localhost:3000/', { timeout: 10000 })
    console.log('[test] Redirected back to app')

    // 9. Should see welcome message with username
    const welcomeMsg = page.locator('text=Welcome')
    await expect(welcomeMsg).toBeVisible({ timeout: 5000 })
    console.log('[test] Welcome message visible')

    // 10. Chat input should be enabled
    const chatInput = page.locator('input[placeholder="Type your message..."]')
    await expect(chatInput).toBeEnabled({ timeout: 5000 })
    console.log('[test] Chat input enabled')

    // 11. Should see logout button
    const logoutBtn = page.locator('button:has-text("Logout")')
    await expect(logoutBtn).toBeVisible()
    console.log('[test] Logout button visible')
  })

  test('user can send message after login', async ({ page }) => {
    // 1. Login first
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // Wait for Keycloak and login
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('button[type="submit"]').click()

    // Wait for redirect back to app
    await page.waitForURL('http://localhost:3000/', { timeout: 10000 })
    console.log('[test] Logged in successfully')

    // 2. Wait for chat input to be ready
    const chatInput = page.locator('input[placeholder="Type your message..."]')
    await expect(chatInput).toBeEnabled({ timeout: 5000 })
    console.log('[test] Chat input ready')

    // 3. Type message
    const testMessage = 'What is 2+2?'
    await chatInput.fill(testMessage)
    console.log(`[test] Typed message: ${testMessage}`)

    // 4. Send message
    const sendBtn = page.locator('button:has-text("Send")')
    await sendBtn.click()
    console.log('[test] Clicked send button')

    // 5. Wait for response to appear
    // The agent should respond within a few seconds
    const response = page.locator('.message-agent')
    await expect(response).toBeVisible({ timeout: 10000 })
    console.log('[test] Received agent response')

    // 6. Verify message content
    const messageText = await response.textContent()
    expect(messageText).toBeTruthy()
    expect(messageText).toContain('4') // Should contain answer to 2+2
    console.log(`[test] Response content: ${messageText}`)
  })

  test('user is logged out after logout', async ({ page }) => {
    // 1. Login first
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('testpassword')
    await page.locator('button[type="submit"]').click()

    await page.waitForURL('http://localhost:3000/', { timeout: 10000 })
    console.log('[test] Logged in')

    // 2. Click logout
    const logoutBtn = page.locator('button:has-text("Logout")')
    await logoutBtn.click()
    console.log('[test] Clicked logout')

    // 3. Should redirect to Keycloak logout endpoint
    await page.waitForURL(/keycloak|logout|8080/, { timeout: 10000 })
    console.log('[test] Logout in progress')

    // 4. Should eventually be back at login screen
    await page.waitForURL('http://localhost:3000/', { timeout: 10000 })

    // 5. Should see login button again
    const newLoginBtn = page.locator('button:has-text("Login")')
    await expect(newLoginBtn).toBeVisible({ timeout: 5000 })
    console.log('[test] Back at login screen')

    // 6. Chat input should not be visible
    const chatInput = page.locator('input[placeholder="Type your message..."]')
    await expect(chatInput).not.toBeVisible()
    console.log('[test] Chat input not visible')
  })

  test('login with wrong password fails', async ({ page }) => {
    // 1. Navigate and click login
    await page.goto('/')
    const loginBtn = page.locator('button:has-text("Login")')
    await loginBtn.click()

    // 2. Wait for Keycloak
    await page.waitForURL(/keycloak|8080/, { timeout: 10000 })

    // 3. Fill with wrong password
    await page.locator('input[name="username"]').fill('testuser')
    await page.locator('input[name="password"]').fill('wrongpassword')
    console.log('[test] Filled wrong password')

    // 4. Submit
    await page.locator('button[type="submit"]').click()

    // 5. Should see error message
    const errorMsg = page.locator('text=/Invalid user|invalid credentials|error/i')
    await expect(errorMsg).toBeVisible({ timeout: 5000 })
    console.log('[test] Error message appeared for wrong password')
  })
})
