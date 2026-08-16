export type AuthRefresh = () => Promise<boolean>

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

  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    const refreshed = await onRefresh()
    if (refreshed) {
      const newToken = localStorage.getItem('access_token')
      if (newToken) {
        headers.Authorization = `Bearer ${newToken}`
        return fetch(url, {
          ...options,
          headers,
        })
      }
    }
  }

  return response
}
