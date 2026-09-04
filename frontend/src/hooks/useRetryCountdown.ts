import { useEffect, useState } from 'react'

/** Counts down from `initialSeconds` to 0, ticking once a second, and
 * reports `null` once there is nothing left to wait for -- either because
 * the countdown finished, or because `initialSeconds` was undefined/0 to
 * begin with (issue #47: a 429's Retry-After header, when present, drives
 * this so a rate-limited Send/Login button can re-enable itself
 * automatically instead of leaving the user to guess when to retry).
 *
 * Restarts whenever `initialSeconds` changes to a new defined value (e.g. a
 * second, later rate-limit trip while an earlier countdown was still
 * running) -- callers don't need to key/remount anything themselves.
 */
export function useRetryCountdown(initialSeconds: number | undefined): number | null {
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(
    initialSeconds ? initialSeconds : null
  )

  useEffect(() => {
    setRemainingSeconds(initialSeconds ? initialSeconds : null)
  }, [initialSeconds])

  useEffect(() => {
    if (remainingSeconds === null || remainingSeconds <= 0) {
      return
    }
    const timeoutId = setTimeout(() => {
      setRemainingSeconds((current) => (current === null ? null : current - 1))
    }, 1000)
    return () => clearTimeout(timeoutId)
  }, [remainingSeconds])

  return remainingSeconds !== null && remainingSeconds > 0 ? remainingSeconds : null
}
