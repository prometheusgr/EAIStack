export interface LogoutResponse {
  purged_conversations: number
}

export interface AuthClient {
  logout(token: string): Promise<LogoutResponse>
}

/** Logout does not go through authorizedFetch: that helper refreshes an
 * expired token and retries, which is the wrong behaviour here. If the token
 * is already gone there is nothing to clean up server-side, and renewing a
 * session purely to end it would be backwards.
 */
const authClient: AuthClient = {
  async logout(token: string): Promise<LogoutResponse> {
    const response = await fetch('/api/auth/logout', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      throw new Error(`Logout cleanup failed with status ${response.status}`)
    }

    return response.json()
  },
}

export { authClient }
