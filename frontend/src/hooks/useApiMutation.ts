import { useEffect, useRef, useState } from 'react'

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

  // See the matching guard in useApiCall: without it, a mutation still in
  // flight when the component unmounts keeps running, and its resolution
  // calls setState on a component nothing is listening to anymore.
  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const mutateAsync = async (args: T): Promise<R> => {
    if (isMountedRef.current) {
      setIsPending(true)
      setError(null)
    }
    try {
      const result = await mutateFn(args)
      if (isMountedRef.current) {
        setData(result)
      }
      options?.onSuccess?.(result)
      return result
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err))
      if (isMountedRef.current) {
        setError(error)
      }
      options?.onError?.(error)
      throw error
    } finally {
      if (isMountedRef.current) {
        setIsPending(false)
      }
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
