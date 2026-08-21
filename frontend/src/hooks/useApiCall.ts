import { useEffect, useRef, useState } from 'react'

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

  // apiFn is typically a fresh closure every render (see useThreadsService,
  // useSettingsService), so it can't be a useEffect dependency without
  // re-firing the immediate-fetch effect on every render. Read the latest
  // closure through a ref instead, updated on every render body (not in an
  // effect, so it's current before the mount effect below ever runs).
  const apiFnRef = useRef(apiFn)
  apiFnRef.current = apiFn

  // Guards every setState below: without it, a request still in flight when
  // the component unmounts keeps running, and its resolution calls setState
  // on a component nothing is listening to anymore. That stray update is a
  // no-op in the running app, but in this test suite - where every test
  // mounts a fresh provider tree via renderSettings()/renderHook() and none
  // of them wait for in-flight requests to settle before moving on - it can
  // land during a *later*, unrelated test and trigger an extra render at
  // the wrong moment, which is the shape of the intermittent CI failures
  // this guard was added to fix (dialogs that "never open", fields that
  // "never populate").
  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const execute = async (): Promise<T | null> => {
    if (isMountedRef.current) {
      setState({ data: null, error: null, isLoading: true })
    }
    try {
      const result = await apiFnRef.current()
      if (isMountedRef.current) {
        setState({ data: result, error: null, isLoading: false })
      }
      options?.onSuccess?.(result)
      return result
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err))
      if (isMountedRef.current) {
        setState({ data: null, error, isLoading: false })
      }
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
