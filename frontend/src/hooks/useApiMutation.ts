import { useState } from 'react'

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

  const mutateAsync = async (args: T): Promise<R> => {
    setIsPending(true)
    setError(null)
    try {
      const result = await mutateFn(args)
      setData(result)
      options?.onSuccess?.(result)
      return result
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err))
      setError(error)
      options?.onError?.(error)
      throw error
    } finally {
      setIsPending(false)
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
