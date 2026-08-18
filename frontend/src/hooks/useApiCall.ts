import { useEffect, useState } from 'react'

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

  const execute = async (): Promise<T | null> => {
    setState({ data: null, error: null, isLoading: true })
    try {
      const result = await apiFn()
      setState({ data: result, error: null, isLoading: false })
      options?.onSuccess?.(result)
      return result
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err))
      setState({ data: null, error, isLoading: false })
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
