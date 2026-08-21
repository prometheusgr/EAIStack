import { describe, it, expect, vi, beforeEach } from 'vitest'
import { authClient } from '../authClient'

describe('authClient.logout', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('POSTs to the logout endpoint with the bearer token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ purged_conversations: 2 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await authClient.logout('token-abc')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/logout',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer token-abc' }),
      })
    )
    expect(result.purged_conversations).toBe(2)
  })

  it('reports zero purged when the backend declines to clean up', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ purged_conversations: 0 }),
      })
    )

    const result = await authClient.logout('token-abc')

    expect(result.purged_conversations).toBe(0)
  })

  it('throws when the backend rejects the request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Not authenticated' }),
      })
    )

    await expect(authClient.logout('bad-token')).rejects.toThrow()
  })
})
