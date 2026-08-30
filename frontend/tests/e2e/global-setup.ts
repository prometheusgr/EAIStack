async function waitForService(name: string, url: string, attempts = 30): Promise<boolean> {
  for (let i = 0; i < attempts; i++) {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 2000)
      const response = await fetch(url, { signal: controller.signal })
      clearTimeout(timeoutId)
      if (response.ok) {
        console.log(`[global-setup] ✓ ${name} available`)
        return true
      }
    } catch {
      // Not ready yet; fall through to retry below.
    }
    if (i < attempts - 1) {
      process.stdout.write('.')
      await new Promise((r) => setTimeout(r, 1000))
    }
  }
  return false
}

async function globalSetup() {
  console.log('[global-setup] Starting E2E tests...')
  console.log('[global-setup] Make sure docker-compose up is running with services ready')
  console.log('[global-setup] Required: Keycloak (http://localhost:8080), Backend (http://localhost:8001)')

  // Keycloak is checked first since it's most critical for auth tests.
  const keycloakReady = await waitForService('Keycloak', 'http://localhost:8080/realms/eaistack')
  if (!keycloakReady) {
    console.error('\n[global-setup] ✗ Keycloak not ready after 30 seconds')
    console.error('[global-setup] Make sure docker-compose is running: docker-compose up')
    throw new Error('Keycloak must be running for E2E tests')
  }

  const backendReady = await waitForService('Backend', 'http://localhost:8001/health')
  if (!backendReady) {
    console.error('\n[global-setup] ✗ Backend not ready after 30 seconds')
    console.error('[global-setup] Make sure docker-compose is running: docker-compose up')
    throw new Error('Backend must be running for E2E tests')
  }

  console.log('\n[global-setup] Ready to start tests!')
}

export default globalSetup
