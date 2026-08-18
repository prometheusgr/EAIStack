export interface ApiError extends Error {
  status: number
  detail: string
}

export class ApiErrorImpl extends Error implements ApiError {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(`API Error ${status}: ${detail}`)
    this.name = 'ApiError'
  }
}

export interface ApiCallOptions extends RequestInit {
  token?: string
  onRefresh?: () => Promise<boolean>
}

export async function apiCall<T>(
  endpoint: string,
  options: ApiCallOptions = {}
): Promise<T> {
  const { token, onRefresh, ...fetchOptions } = options

  const headers = new Headers(fetchOptions.headers || {})

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  let response = await fetch(endpoint, {
    ...fetchOptions,
    headers,
  })

  if (response.status === 401 && onRefresh) {
    const refreshed = await onRefresh()
    if (refreshed) {
      const newToken = localStorage.getItem('access_token')
      if (newToken) {
        headers.set('Authorization', `Bearer ${newToken}`)
        response = await fetch(endpoint, {
          ...fetchOptions,
          headers,
        })
      }
    }
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const data = await response.json()
      if (data.detail) {
        detail = data.detail
      }
    } catch {
      // If response isn't JSON, use statusText
    }
    throw new ApiErrorImpl(response.status, detail)
  }

  return response.json() as Promise<T>
}
