export interface AuthTokenPayload {
  sub: string
  preferred_username: string
  email?: string
  name?: string
  exp: number
  aud?: string | string[]
}

export interface AuthUser {
  username?: string
  email?: string
  name?: string
}

export function decodeJwt(token: string): AuthTokenPayload {
  const parts = token.split('.')
  if (parts.length !== 3) {
    throw new Error('Invalid token format')
  }

  const payload = JSON.parse(
    atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))
  )
  return payload
}

export function buildKeycloakLoginUrl(
  keycloakUrl: string,
  redirectUri: string
): string {
  const baseUrl = keycloakUrl.replace(/\/$/, '')
  const loginUrl = new URL(`${baseUrl}/realms/eaistack/protocol/openid-connect/auth`)

  loginUrl.searchParams.set('client_id', 'eaistack-web')
  loginUrl.searchParams.set('redirect_uri', redirectUri)
  loginUrl.searchParams.set('response_type', 'code')
  loginUrl.searchParams.set('response_mode', 'query')
  loginUrl.searchParams.set('scope', 'openid profile email')
  loginUrl.searchParams.set('state', `eaistack-${Date.now()}`)
  loginUrl.searchParams.set('prompt', 'login')

  return loginUrl.href
}

export function buildKeycloakLogoutUrl(
  keycloakUrl: string,
  redirectUri: string
): string {
  const baseUrl = keycloakUrl.replace(/\/$/, '')
  const logoutUrl = new URL(
    `${baseUrl}/realms/eaistack/protocol/openid-connect/logout`
  )

  logoutUrl.searchParams.set('redirect_uri', redirectUri)
  return logoutUrl.href
}
