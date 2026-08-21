import { authClient, type LogoutResponse } from '@/api/authClient'

export class AuthService {
  constructor(private token: string) {}

  async logout(): Promise<LogoutResponse> {
    if (!this.token) throw new Error('No auth token available')
    return authClient.logout(this.token)
  }
}
