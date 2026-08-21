import { useEffect, useRef } from 'react'

export function useIsMounted(): () => boolean {
  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])
  return () => isMountedRef.current
}
