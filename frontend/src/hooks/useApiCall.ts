import { useEffect, useRef, useState } from 'react'
import { useIsMounted } from './useIsMounted'

export interface UseApiCallState<T> {
  data: T | null
  error: Error | null
  isLoading: boolean
}

export function useApiCall<T>(
  apiFn: () => Promise<T>,
  options?: {
    onError?: (error: Error) => void
    onSuccess?: (data: T) => void
    immediate?: boolean
  }
): UseApiCallState<T> & { execute: () => Promise<T | null> } {
  const [state, setState] = useState<UseApiCallState<T>>({
    data: null,
    error: null,
    isLoading: false,
  })
  const isMounted = useIsMounted()

  // apiFn is typically a fresh closure every render (see useThreadsService,
  // useSettingsService), so it can't be a useEffect dependency without
  // re-firing the immediate-fetch effect on every render. Read the latest
  // closure through a ref instead, updated on every render body (not in an
  // effect, so it's current before the mount effect below ever runs).
  const apiFnRef = useRef(apiFn)
  apiFnRef.current = apiFn

  const execute = async (): Promise<T | null> => {
    if (isMounted()) setState({ data: null, error: null, isLoading: true })
    try {
      const result = await apiFnRef.current()
      if (isMounted()) setState({ data: result, error: null, isLoading: false })
      options?.onSuccess?.(result)
      return result
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err))
      if (isMounted()) setState({ data: null, error, isLoading: false })
      options?.onError?.(error)
      return null
    }
  }

  useEffect(() => {
    if (options?.immediate !== false) {
      execute()
    }
  }, [])

  return {
    ...state,
    execute,
  }
}
