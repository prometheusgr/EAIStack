async function globalSetup() {
  console.log('[global-setup] Starting E2E tests...')
  console.log('[global-setup] Make sure docker-compose up is running with services ready')
  console.log('[global-setup] Required: Keycloak (http://localhost:8080), Backend (http://localhost:8001)')

  // Check Keycloak (most critical for auth tests)
  let keycloakReady = false
  for (let i = 0; i < 30; i++) {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 2000)
      const response = await fetch('http://localhost:8080/realms/eaistack', { signal: controller.signal })
      clearTimeout(timeoutId)
      if (response.ok) {
        console.log('[global-setup] ✓ Keycloak available')
        keycloakReady = true
        break
      }
    } catch (err) {
      if (i < 29) {
        process.stdout.write('.')
        await new Promise((r) => setTimeout(r, 1000))
      }
    }
  }

  if (!keycloakReady) {
    console.error('\n[global-setup] ✗ Keycloak not ready after 30 seconds')
    console.error('[global-setup] Make sure docker-compose is running: docker-compose up')
    throw new Error('Keycloak must be running for E2E tests')
  }

  console.log('\n[global-setup] Ready to start tests!')
}

export default globalSetup
