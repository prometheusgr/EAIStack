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
    message?: string,
    // Issue #47: how many seconds until a 429-throttled request may be
    // retried (backend/app/services/rate_limiter_service.rate_limit_exceeded_response's
    // Retry-After header). undefined for any response that never set the
    // header (every non-429 response, and a 429 with a malformed value) --
    // callers must treat "no countdown available" and "countdown is 0" as
    // distinct, so this is never coerced to 0 or NaN.
    public retryAfterSeconds?: number
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
  retryAfterSeconds?: number
}

/** Parses a Retry-After header value (always a plain integer-as-string from
 * this backend, e.g. "30" -- see rate_limit_exceeded_response) into a
 * number, or undefined if the header is absent or not a valid non-negative
 * integer. Never returns NaN, so callers can use a plain truthiness/
 * undefined check without also guarding against NaN.
 */
function parseRetryAfterSeconds(headers: Headers | undefined): number | undefined {
  const raw = headers?.get('Retry-After')
  if (!raw) return undefined
  const parsed = Number.parseInt(raw, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined
}

// Exported for app/context/AuthContext.tsx's pre-login /api/auth/token calls,
// which cannot go through authorizedFetch below (it requires a bearer token,
// but no token exists yet before login/refresh succeeds) but hit the same
// backend error-body shape (see backend/app/services/rate_limiter_service's
// rate_limit_exceeded_response and the guardrail rejection it mirrors).
export async function parseErrorBody(response: Response): Promise<ParsedErrorBody> {
  const retryAfterSeconds = parseRetryAfterSeconds(response.headers)
  try {
    const data = await response.json()
    if (data.detail) {
      // message is an optional, endpoint-specific human-readable string
      // alongside the stable machine-readable detail code (see
      // backend/app/api/agents.py's guardrail rejection response) -- not
      // every endpoint sets it, so callers fall back to detail/statusText.
      return {
        detail: data.detail,
        message: typeof data.message === 'string' ? data.message : undefined,
        retryAfterSeconds,
      }
    }
  } catch {
    // Response body isn't JSON; fall back to statusText.
  }
  return { detail: response.statusText, retryAfterSeconds }
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
    throw new ApiErrorImpl(response.status, body.detail, body.message, body.retryAfterSeconds)
  }

  return response
}
