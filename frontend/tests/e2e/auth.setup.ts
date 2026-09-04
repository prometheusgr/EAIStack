import { test as setup } from '@playwright/test'
import { login } from './helpers'
import { AUTH_FILE } from '../../playwright.config'

// Playwright's own recommended pattern for reusing one authenticated
// session across specs: this file runs as its own "setup" project (see
// playwright.config.ts's `projects` array), once, before the specs that
// declare `dependencies: ['setup']` run. It performs exactly one real
// Keycloak login and snapshots the resulting localStorage (where
// AuthContext.tsx stores the access/refresh/id tokens -- Playwright's
// storageState captures localStorage per-origin, not just cookies, so
// this token-storage strategy is compatible with it) to AUTH_FILE below.
//
// Issue #53: every e2e spec previously logged in fresh per test against
// the real POST /api/auth/token endpoint, and since the whole suite runs
// as one Docker-network client IP (see docker-compose.yml's
// RATE_LIMIT_AUTH_CAPACITY stopgap), those per-test logins summed into one
// shared rate-limit bucket -- a large enough suite eventually trips it.
// Most specs don't need a *fresh* login; they need *a* logged-in session.
// Routing those specs through this one-time setup instead removes ~21 of
// the suite's ~36 real login calls (see the issue's own research) from
// that shared bucket entirely, rather than just raising the ceiling
// further.
//
// Specs that test the login/logout flow itself as their subject
// (auth.spec.ts, login-logout-complete.spec.ts, no-infinite-loop.spec.ts)
// deliberately do NOT depend on this setup and are not eligible: they
// need to start unauthenticated and drive a real login themselves.

setup('authenticate as the seeded testuser', async ({ page }) => {
  await login(page)
  await page.context().storageState({ path: AUTH_FILE })
})
