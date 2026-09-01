export type AuthRefresh = () => Promise<boolean>

export interface ApiError extends Error {
  status: number
  detail: string
  message: string
}

export class ApiErrorImpl extends Error implements ApiError {
  constructor(
    public status: number,
    public detail: string,
    message?: string
  ) {
    // Never fall back to `detail` here: `detail` is a stable, internal,
    // machine-readable code and may not be fit for a user to see (see
    // parseErrorBody below). Leaving `message` as '' when the caller didn't
    // supply one lets callers like ChatWindow's describeSendError use a
    // plain truthiness check to tell "no message was provided" apart from
    // an endpoint-supplied human-readable string.
    super(message ?? '')
    this.name = 'ApiError'
  }
}

export interface ParsedErrorBody {
  detail: string
  message?: string
}

// Exported for app/context/AuthContext.tsx's pre-login /api/auth/token calls,
// which cannot go through authorizedFetch below (it requires a bearer token,
// but no token exists yet before login/refresh succeeds) but hit the same
// backend error-body shape (see backend/app/services/rate_limiter_service's
// rate_limit_exceeded_response and the guardrail rejection it mirrors).
export async function parseErrorBody(response: Response): Promise<ParsedErrorBody> {
  try {
    const data = await response.json()
    if (data.detail) {
      // message is an optional, endpoint-specific human-readable string
      // alongside the stable machine-readable detail code (see
      // backend/app/api/agents.py's guardrail rejection response) -- not
      // every endpoint sets it, so callers fall back to detail/statusText.
      return { detail: data.detail, message: typeof data.message === 'string' ? data.message : undefined }
    }
  } catch {
    // Response body isn't JSON; fall back to statusText.
  }
  return { detail: response.statusText }
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
    const body = await parseErrorBody(response)
    throw new ApiErrorImpl(response.status, body.detail, body.message)
  }

  return response
}
