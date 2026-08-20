export type AuthRefresh = () => Promise<boolean>

export interface ApiError extends Error {
  status: number
  detail: string
}

export class ApiErrorImpl extends Error implements ApiError {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (data.detail) {
      return data.detail
    }
  } catch {
    // Response body isn't JSON; fall back to statusText.
  }
  return response.statusText
}

export async function authorizedFetch(
  url: string,
  token: string | null,
  onRefresh: AuthRefresh,
  options?: RequestInit
): Promise<Response> {
  if (!token) {
    throw new Error('No auth token available')
  }

  const headers = {
    ...options?.headers,
    Authorization: `Bearer ${token}`,
  } as Record<string, string>

  let response = await fetch(url, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    const refreshed = await onRefresh()
    if (refreshed) {
      const newToken = localStorage.getItem('access_token')
      if (newToken) {
        headers.Authorization = `Bearer ${newToken}`
        response = await fetch(url, {
          ...options,
          headers,
        })
      }
    }
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response)
    throw new ApiErrorImpl(response.status, detail)
  }

  return response
}
