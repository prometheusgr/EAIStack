# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> Authentication Flow >> user can login and access chat
- Location: tests\e2e\auth.spec.ts:4:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('button:has-text("Login")')
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=8bdc99e7-049b-4f59-b2fa-b700efde0620&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=8bdc99e7-049b-4f59-b2fa-b700efde0620"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=08eec704-f4d3-46da-ab04-7af36e65ede8&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=08eec704-f4d3-46da-ab04-7af36e65ede8"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=99551c34-c5c4-4985-9074-3ec974de3e0e&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=99551c34-c5c4-4985-9074-3ec974de3e0e"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=bfc2f6ad-e2b7-4b27-a431-45dd9964b1d1&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=bfc2f6ad-e2b7-4b27-a431-45dd9964b1d1"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=e86b9778-898d-41f1-b185-2d4c250ef707"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=75216041-7606-48b6-99e7-3f65b267645f"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=b9dee799-f9db-4ae8-80e0-6c69e6c89226"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=7dbf13a6-d6e5-4925-9fca-53ca80abc238"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=bbdaffc9-fe23-43d1-891c-14dcae01f31c"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=443b5404-cf35-4f5a-be7d-984a14a77aa8"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=ef37ead4-3be1-46bb-84cd-f31ce6cdcf77"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=a4240676-fd6a-4773-8983-15f78b7b7c21&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=a4240676-fd6a-4773-8983-15f78b7b7c21"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=dd526072-cdce-46dd-865b-3c725eb08240"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=5c10d348-51eb-448e-8ca1-cffdd18976ea"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=945fac2e-3aed-427f-9d68-3d425ae5e1bf"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=59a5ffae-b320-4ce3-bb35-1523390db402"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=3a396b0b-2414-422e-b603-759d0f7c81b4"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=307226b5-951d-4751-9a6e-3888295ca7bf"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=4c39a229-8ff2-4d39-82f2-389bb9803ab1"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=66348226-72da-40d1-85db-2f3e2539bd3c&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=66348226-72da-40d1-85db-2f3e2539bd3c"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=eb5d58a8-b57b-4613-956c-29274a3ed2fa"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=95064aa5-23a8-4349-a7df-8adb64b65682&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=95064aa5-23a8-4349-a7df-8adb64b65682"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=b480c9ec-43e2-4ba4-90e3-3f3f598c1a13"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=d3ea0fd9-9e6a-4d04-9210-27b47804e0f6"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=4965abf3-cb4c-46e3-b8e1-3b714f07bc30&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=4965abf3-cb4c-46e3-b8e1-3b714f07bc30"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=4f19759d-2db8-4f00-8692-acbfaa7885e4&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=4f19759d-2db8-4f00-8692-acbfaa7885e4"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=4095ac1f-3bbb-4ad2-80c1-ed9c7b9f30b8"

```

# Page snapshot

```yaml
- generic [ref=f813e3]:
  - heading "EAIStack" [level=1] [ref=f813e4]
  - paragraph [ref=f813e5]: Enterprise AI Stack - Please log in
  - button "Login" [ref=f813e6] [cursor=pointer]
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
> 15  |     await loginBtn.click()
      |                    ^ Error: locator.click: Test timeout of 30000ms exceeded.
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
  63  |     await loginBtn.click()
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
```