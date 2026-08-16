# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> Authentication Flow >> user can send message after login
- Location: tests\e2e\auth.spec.ts:59:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('button:has-text("Login")')
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=d0c0b68c-8045-4f66-bb78-3732c51ad9ee"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=4be4287f-0184-47c4-ad6e-36700e87aa78&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=4be4287f-0184-47c4-ad6e-36700e87aa78"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=7f6e2848-351c-4e95-8974-17c617134dbb&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=7f6e2848-351c-4e95-8974-17c617134dbb"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=65147dea-0174-4b53-8a97-b72f022a72e4&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=65147dea-0174-4b53-8a97-b72f022a72e4"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=396520db-b81c-46b4-8f08-d7266145ce44&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=396520db-b81c-46b4-8f08-d7266145ce44"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=a1ae36c9-4fb7-451a-8077-1988825eea8d"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=689cc5e4-c94b-4a17-8275-1df79bae6eeb"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=27f99897-4ae9-4b4e-84b8-5125180a1ce0"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=978c40bd-5704-4498-891e-9dbc66cc21e5"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=e76bd3e2-5e2c-4d65-95fc-ac6e29a5d2bb&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=e76bd3e2-5e2c-4d65-95fc-ac6e29a5d2bb"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=1883953b-cd60-451a-9958-6c642d092645&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=1883953b-cd60-451a-9958-6c642d092645"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=8f4ea6c0-432a-4e3a-bac6-556f420f2304"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=cc6024c3-a872-4fd6-8a9b-937fb3297dbc"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=aa781402-6e38-4b93-9ec6-3dd6c007de5a&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=aa781402-6e38-4b93-9ec6-3dd6c007de5a"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=8757892d-1cee-470b-8e18-00ddb0ff4e13"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=711c8c8c-6c9e-4a2a-8b52-435eeb28f7e2"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=a4a5d1b9-f2c3-48ad-9aaf-d5ec98ad772e"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=a262e9d2-3090-4b25-b0f7-b8bb2fbc4155"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=1d4b216c-d9ca-498f-8d7f-c2bdc41fd3b5"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=8d854142-e7c5-4108-b2a2-ca4c1dd5080d"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=0f30c58a-db06-443e-8729-64448c4f4da0"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=d4aa975b-d7ef-4e8c-9ddf-fe798f4ebdfb"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=9d83754c-be95-44e2-9075-23e2c81a94b4"

```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test'
  2   | 
  3   | test.describe('Authentication Flow', () => {
  4   |   test('user can login and access chat', async ({ page }) => {
  5   |     // 1. Navigate to app
  6   |     await page.goto('/')
  7   |     console.log('[test] Navigated to home page')
  8   | 
  9   |     // 2. Should see login button
  10  |     const loginBtn = page.locator('button:has-text("Login")')
  11  |     await expect(loginBtn).toBeVisible({ timeout: 5000 })
  12  |     console.log('[test] Login button visible')
  13  | 
  14  |     // 3. Click login - should redirect to Keycloak
  15  |     await loginBtn.click()
  16  |     console.log('[test] Clicked login button')
  17  | 
  18  |     // 4. Wait for Keycloak login form
  19  |     // The URL will be something like http://localhost:8080/auth/realms/...
  20  |     await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
  21  |     console.log('[test] Redirected to Keycloak')
  22  | 
  23  |     // 5. Fill username
  24  |     const usernameInput = page.locator('input[name="username"]')
  25  |     await expect(usernameInput).toBeVisible({ timeout: 5000 })
  26  |     await usernameInput.fill('testuser')
  27  |     console.log('[test] Filled username')
  28  | 
  29  |     // 6. Fill password
  30  |     const passwordInput = page.locator('input[name="password"]')
  31  |     await passwordInput.fill('testpassword')
  32  |     console.log('[test] Filled password')
  33  | 
  34  |     // 7. Submit login form
  35  |     const submitBtn = page.locator('button[type="submit"]')
  36  |     await submitBtn.click()
  37  |     console.log('[test] Submitted login form')
  38  | 
  39  |     // 8. Should redirect back to app
  40  |     await page.waitForURL('http://localhost:3000/', { timeout: 10000 })
  41  |     console.log('[test] Redirected back to app')
  42  | 
  43  |     // 9. Should see welcome message with username
  44  |     const welcomeMsg = page.locator('text=Welcome')
  45  |     await expect(welcomeMsg).toBeVisible({ timeout: 5000 })
  46  |     console.log('[test] Welcome message visible')
  47  | 
  48  |     // 10. Chat input should be enabled
  49  |     const chatInput = page.locator('input[placeholder="Type your message..."]')
  50  |     await expect(chatInput).toBeEnabled({ timeout: 5000 })
  51  |     console.log('[test] Chat input enabled')
  52  | 
  53  |     // 11. Should see logout button
  54  |     const logoutBtn = page.locator('button:has-text("Logout")')
  55  |     await expect(logoutBtn).toBeVisible()
  56  |     console.log('[test] Logout button visible')
  57  |   })
  58  | 
  59  |   test('user can send message after login', async ({ page }) => {
  60  |     // 1. Login first
  61  |     await page.goto('/')
  62  |     const loginBtn = page.locator('button:has-text("Login")')
> 63  |     await loginBtn.click()
      |                    ^ Error: locator.click: Test timeout of 30000ms exceeded.
  64  | 
  65  |     // Wait for Keycloak and login
  66  |     await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
  67  |     await page.locator('input[name="username"]').fill('testuser')
  68  |     await page.locator('input[name="password"]').fill('testpassword')
  69  |     await page.locator('button[type="submit"]').click()
  70  | 
  71  |     // Wait for redirect back to app
  72  |     await page.waitForURL('http://localhost:3000/', { timeout: 10000 })
  73  |     console.log('[test] Logged in successfully')
  74  | 
  75  |     // 2. Wait for chat input to be ready
  76  |     const chatInput = page.locator('input[placeholder="Type your message..."]')
  77  |     await expect(chatInput).toBeEnabled({ timeout: 5000 })
  78  |     console.log('[test] Chat input ready')
  79  | 
  80  |     // 3. Type message
  81  |     const testMessage = 'What is 2+2?'
  82  |     await chatInput.fill(testMessage)
  83  |     console.log(`[test] Typed message: ${testMessage}`)
  84  | 
  85  |     // 4. Send message
  86  |     const sendBtn = page.locator('button:has-text("Send")')
  87  |     await sendBtn.click()
  88  |     console.log('[test] Clicked send button')
  89  | 
  90  |     // 5. Wait for response to appear
  91  |     // The agent should respond within a few seconds
  92  |     const response = page.locator('.message-agent')
  93  |     await expect(response).toBeVisible({ timeout: 10000 })
  94  |     console.log('[test] Received agent response')
  95  | 
  96  |     // 6. Verify message content
  97  |     const messageText = await response.textContent()
  98  |     expect(messageText).toBeTruthy()
  99  |     expect(messageText).toContain('4') // Should contain answer to 2+2
  100 |     console.log(`[test] Response content: ${messageText}`)
  101 |   })
  102 | 
  103 |   test('user is logged out after logout', async ({ page }) => {
  104 |     // 1. Login first
  105 |     await page.goto('/')
  106 |     const loginBtn = page.locator('button:has-text("Login")')
  107 |     await loginBtn.click()
  108 | 
  109 |     await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
  110 |     await page.locator('input[name="username"]').fill('testuser')
  111 |     await page.locator('input[name="password"]').fill('testpassword')
  112 |     await page.locator('button[type="submit"]').click()
  113 | 
  114 |     await page.waitForURL('http://localhost:3000/', { timeout: 10000 })
  115 |     console.log('[test] Logged in')
  116 | 
  117 |     // 2. Click logout
  118 |     const logoutBtn = page.locator('button:has-text("Logout")')
  119 |     await logoutBtn.click()
  120 |     console.log('[test] Clicked logout')
  121 | 
  122 |     // 3. Should redirect to Keycloak logout endpoint
  123 |     await page.waitForURL(/keycloak|logout|8080/, { timeout: 10000 })
  124 |     console.log('[test] Logout in progress')
  125 | 
  126 |     // 4. Should eventually be back at login screen
  127 |     await page.waitForURL('http://localhost:3000/', { timeout: 10000 })
  128 | 
  129 |     // 5. Should see login button again
  130 |     const newLoginBtn = page.locator('button:has-text("Login")')
  131 |     await expect(newLoginBtn).toBeVisible({ timeout: 5000 })
  132 |     console.log('[test] Back at login screen')
  133 | 
  134 |     // 6. Chat input should not be visible
  135 |     const chatInput = page.locator('input[placeholder="Type your message..."]')
  136 |     await expect(chatInput).not.toBeVisible()
  137 |     console.log('[test] Chat input not visible')
  138 |   })
  139 | 
  140 |   test('login with wrong password fails', async ({ page }) => {
  141 |     // 1. Navigate and click login
  142 |     await page.goto('/')
  143 |     const loginBtn = page.locator('button:has-text("Login")')
  144 |     await loginBtn.click()
  145 | 
  146 |     // 2. Wait for Keycloak
  147 |     await page.waitForURL(/keycloak|8080/, { timeout: 10000 })
  148 | 
  149 |     // 3. Fill with wrong password
  150 |     await page.locator('input[name="username"]').fill('testuser')
  151 |     await page.locator('input[name="password"]').fill('wrongpassword')
  152 |     console.log('[test] Filled wrong password')
  153 | 
  154 |     // 4. Submit
  155 |     await page.locator('button[type="submit"]').click()
  156 | 
  157 |     // 5. Should see error message
  158 |     const errorMsg = page.locator('text=/Invalid user|invalid credentials|error/i')
  159 |     await expect(errorMsg).toBeVisible({ timeout: 5000 })
  160 |     console.log('[test] Error message appeared for wrong password')
  161 |   })
  162 | })
  163 | 
```