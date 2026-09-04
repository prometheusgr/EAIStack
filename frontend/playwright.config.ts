import { defineConfig, devices } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Where the 'setup' project's one real login saves its session (see
// tests/e2e/auth.setup.ts) for the 'chromium' project's specs to reuse.
// Gitignored -- this file holds real access/refresh tokens for the seeded
// e2e-only testuser account.
export const AUTH_FILE = './tests/e2e/.auth/user.json'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false, // Run sequentially to avoid resource conflicts
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker to avoid timeouts
  reporter: [['html'], ['json', { outputFile: 'test-results.json' }]],
  timeout: 30 * 1000,
  expect: {
    timeout: 5000,
  },
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    // Runs once, before every other project: performs one real Keycloak
    // login and saves the resulting session to AUTH_FILE (see
    // tests/e2e/auth.setup.ts). Matched only by its filename, not part of
    // the normal spec run.
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    // Most specs: pre-authenticated via the 'setup' project's saved
    // session, so they never call POST /api/auth/token themselves (issue
    // #53 -- see auth.setup.ts's own comment for the full rationale).
    // Excludes the three spec files that test the login/logout flow
    // itself and must start unauthenticated.
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: AUTH_FILE },
      dependencies: ['setup'],
      testIgnore: ['**/auth.spec.ts', '**/login-logout-complete.spec.ts', '**/no-infinite-loop.spec.ts'],
    },
    // The three login/logout-flow specs: deliberately NOT authenticated
    // via 'setup' and have no dependency on it, so they start from a
    // genuine logged-out state and drive real logins themselves.
    {
      name: 'chromium-unauthenticated',
      use: { ...devices['Desktop Chrome'] },
      testMatch: ['**/auth.spec.ts', '**/login-logout-complete.spec.ts', '**/no-infinite-loop.spec.ts'],
    },
  ],
  globalSetup: path.resolve(__dirname, './tests/e2e/global-setup.ts'),
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
})
