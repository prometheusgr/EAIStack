# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> Authentication Flow >> login with wrong password fails
- Location: tests\e2e\auth.spec.ts:140:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('button:has-text("Login")')
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=f8aaae71-09cd-4d7b-8899-439dd8601b4d&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=f8aaae71-09cd-4d7b-8899-439dd8601b4d"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=55b23ea6-f8f5-421f-87fe-015be4fbc5f5"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=3486a5fd-2144-455e-a43c-cc905a115ade"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=46e7a3d7-6121-46dc-8379-c7863119ed4c"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=9548d2f2-810d-4d36-9e54-c8047010b0bc"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=d8d2aba0-1843-4a31-a5c4-32d01a47d615"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=07edc6c9-0170-4e7b-8636-73d82b4fe3c2"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=e9f54497-2a90-4504-8197-2c4f8c9e2109&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=e9f54497-2a90-4504-8197-2c4f8c9e2109"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=2405839e-bad4-4e61-82ad-5e3ca97bd9d3"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=15f6ea0b-9c65-4e99-904b-762b1a74ceff"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=ff02f3da-28d6-4a60-ba8e-379ccf22ed33"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=099bf529-d953-47ea-8f98-b5d937f14eaf"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=67a713c0-0952-4b51-a9be-70ca4fd546f2"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=c931eb02-ebaf-4cee-8bc5-c37f34a21502"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=889824da-0172-4c86-8b7d-c5dc872dcf11&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=889824da-0172-4c86-8b7d-c5dc872dcf11"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=313ca1d9-097e-4aca-9ea3-1b66c2161d2f"
    - waiting for "http://localhost:3000/" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=26a975eb-fb46-48fc-907f-66f8f046ebb7"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=b48ed358-53ff-49c1-81d0-87dbaea3a3a6"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=e95426a1-003b-4801-a971-7c782f045c11&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=e95426a1-003b-4801-a971-7c782f045c11"
    - waiting for "http://localhost:8080/realms/eaistack/protocol/openid-connect/auth?client_id=eaistack-web&redirect_uri=http%3A%2F%2Flocalhost%3A3000&state=42762e8a-0cf3-422c-85ac-4a74ce41ca83&response_mode=fragment&…" navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=42762e8a-0cf3-422c-85ac-4a74ce41ca83"
    - waiting for navigation to finish...
    - navigated to "http://localhost:3000/#error=login_required&state=715310a4-5756-446d-bfd7-74033a8e0bc1"

```

# Test source

```ts
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
> 144 |     await loginBtn.click()
      |                    ^ Error: locator.click: Test timeout of 30000ms exceeded.
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