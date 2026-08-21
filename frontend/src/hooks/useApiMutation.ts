import { useState } from 'react'
import { useIsMounted } from './useIsMounted'

export function useApiMutation<T, R>(
  mutateFn: (args: T) => Promise<R>,
  options?: {
    onSuccess?: (data: R) => void
    onError?: (error: Error) => void
  }
): {
  mutate: (args: T) => Promise<void>
  mutateAsync: (args: T) => Promise<R>
  isPending: boolean
  error: Error | null
  data: R | null
} {
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [data, setData] = useState<R | null>(null)
  const isMounted = useIsMounted()

  const mutateAsync = async (args: T): Promise<R> => {
    if (isMounted()) setIsPending(true)
    if (isMounted()) setError(null)
    try {
      const result = await mutateFn(args)
      if (isMounted()) setData(result)
      options?.onSuccess?.(result)
      return result
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err))
      if (isMounted()) setError(error)
      options?.onError?.(error)
      throw error
    } finally {
      if (isMounted()) setIsPending(false)
    }
  }

  const mutate = async (args: T): Promise<void> => {
    try {
      await mutateAsync(args)
    } catch {
      // Error is already set in state
    }
  }

  return {
    mutate,
    mutateAsync,
    isPending,
    error,
    data,
  }
}
