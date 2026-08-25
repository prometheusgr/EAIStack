import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { authorizedFetch, ApiErrorImpl } from '../../src/api/authorizedFetch'

describe('authorizedFetch', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('retries once with the refreshed token when the first response is 401', async () => {
    localStorage.setItem('access_token', 'new-token')

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 401, statusText: 'Unauthorized', json: async () => ({}) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ result: 'ok' }) })
    vi.stubGlobal('fetch', fetchMock)

    const onRefresh = vi.fn().mockResolvedValue(true)

    const response = await authorizedFetch('/api/thing', 'expired-token', onRefresh)

    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe('Bearer new-token')
    await expect(response.json()).resolves.toEqual({ result: 'ok' })
  })

  it('propagates the original 401 error when the refresh genuinely fails, without retrying a second request', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        json: async () => ({ detail: 'Token expired' }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const onRefresh = vi.fn().mockResolvedValue(false)

    await expect(authorizedFetch('/api/thing', 'expired-token', onRefresh)).rejects.toMatchObject({
      status: 401,
      detail: 'Token expired',
    })

    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('throws an ApiErrorImpl carrying the backend detail message on non-ok responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: async () => ({ detail: 'name is required' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const onRefresh = vi.fn().mockResolvedValue(true)

    await expect(authorizedFetch('/api/thing', 'token', onRefresh)).rejects.toThrow(ApiErrorImpl)
    await expect(authorizedFetch('/api/thing', 'token', onRefresh)).rejects.toMatchObject({
      status: 422,
      detail: 'name is required',
    })
  })

  it('carries an endpoint-supplied human-readable message alongside detail when present', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => ({
        detail: 'prompt_injection_suspected',
        message: "That message couldn't be sent. Please rephrase your question.",
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const onRefresh = vi.fn().mockResolvedValue(true)

    await expect(authorizedFetch('/api/thing', 'token', onRefresh)).rejects.toMatchObject({
      status: 400,
      detail: 'prompt_injection_suspected',
      message: "That message couldn't be sent. Please rephrase your question.",
    })
  })

  it('falls back to detail as the message when the endpoint does not supply one', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ detail: 'Thread not found' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const onRefresh = vi.fn().mockResolvedValue(true)

    await expect(authorizedFetch('/api/thing', 'token', onRefresh)).rejects.toMatchObject({
      status: 404,
      detail: 'Thread not found',
      message: 'Thread not found',
    })
  })
})
