# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> Authentication Flow >> user is logged out after logout
- Location: tests\e2e\auth.spec.ts:103:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('button:has-text("Login")')
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=f40db232-908e-43e3-8f11-c88f8c8066e8"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=96d4d5ea-96c8-4888-8167-d7b71e2a4e12&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=96d4d5ea-96c8-4888-8167-d7b71e2a4e12"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=c0911669-ff1e-4074-84f7-10ec98e6c3b1"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=7a95314d-9424-43ba-8187-b033ab44ec68"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=4dd4172f-e988-4ebb-8ed9-4154f5c7cb9d"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=1dbca577-0e4b-4a77-8cc0-0d57d6b1af9e&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=1dbca577-0e4b-4a77-8cc0-0d57d6b1af9e"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=62bbf6c8-f5e5-4801-b8f9-f059e64c01ff"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=f050e6f2-7dcf-41f4-86ee-89dfdf1f7b52"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=2e500d0b-f3e4-4a57-86ee-4c693035200d"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=7dad7ef6-742d-4028-b384-f4027da63df2"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=16d7446a-c85c-4a46-8a6d-0ffd72d6549a"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=6d67022e-5b85-4f56-a3f0-02243289db86"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=b7ec4bd7-34dc-465e-9591-9e7ca5777f96"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=77213046-7a90-4340-a86b-7ff8ef10725a"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=5b30ced6-b164-4852-848b-29546d8a54b1"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=e706a296-1c2c-4cc0-8fa8-a7e52b3860da"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=cf8df603-30be-4e81-88e6-a4b6e6e76733"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=bec99a7b-c047-48bf-8bd8-74532fd686ec"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=a3f0bd1d-dfdc-4183-b1dd-0b74c5ba0023"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=2b8a0d44-b438-4cbb-8a97-7032e15cf514"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=34309ee4-b9c5-48bd-8b6d-31dd2bdf17ed&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=34309ee4-b9c5-48bd-8b6d-31dd2bdf17ed"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=0dcde786-7504-48fc-a7f3-3b7bbd3aa5cc"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=c31d4099-4cbd-4a83-8ff2-660d3fac9d88"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=b2d5bc05-a141-4ec5-946e-e3fa8098da65"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=26341864-360e-4e82-9ea3-c6b932266ef9"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=cffe4e27-7126-49d0-904a-633e2a116102"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=6e09376e-37a6-47f4-82b8-c836eae84e1a"

```

# Test source

```ts
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
> 107 |     await loginBtn.click()
      |                    ^ Error: locator.click: Test timeout of 30000ms exceeded.
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