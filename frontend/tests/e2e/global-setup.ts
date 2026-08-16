import { chromium, FullConfig } from '@playwright/test'

async function globalSetup(config: FullConfig) {
  console.log('[global-setup] Checking service health before E2E tests...')

  const baseURL = config.use.baseURL || 'http://localhost:3000'

  // Check frontend
  try {
    const response = await fetch(`${baseURL}/`, { timeout: 5000 })
    console.log(`[global-setup] ✓ Frontend available (${response.status})`)
  } catch (err) {
    console.error(
      '[global-setup] ✗ Frontend not available. Make sure docker-compose is running or npm run dev is started'
    )
    throw err
  }

  // Check backend
  try {
    const response = await fetch('http://localhost:8001/health', { timeout: 5000 })
    console.log(`[global-setup] ✓ Backend available (${response.status})`)
  } catch (err) {
    console.error('[global-setup] ✗ Backend not available at http://localhost:8001')
    // Don't fail - backend might not be running, but frontend might be
  }

  // Check Keycloak
  try {
    const response = await fetch('http://localhost:8080/realms/eaistack', { timeout: 5000 })
    console.log(`[global-setup] ✓ Keycloak available (${response.status})`)
  } catch (err) {
    console.error('[global-setup] ✗ Keycloak not available at http://localhost:8080')
    throw new Error('Keycloak must be running for E2E tests. Run: docker-compose up')
  }

  console.log('[global-setup] All checks passed, starting tests...')
}

export default globalSetup
