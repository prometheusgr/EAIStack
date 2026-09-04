import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useRetryCountdown } from '../../src/hooks/useRetryCountdown'

describe('useRetryCountdown', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns null when no initial seconds are given', () => {
    const { result } = renderHook(() => useRetryCountdown(undefined))

    expect(result.current).toBeNull()
  })

  it('returns null when given 0 seconds -- nothing to count down', () => {
    const { result } = renderHook(() => useRetryCountdown(0))

    expect(result.current).toBeNull()
  })

  it('counts down from the given number of seconds to 0, then reports null', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })

    const { result } = renderHook(() => useRetryCountdown(3))

    expect(result.current).toBe(3)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(result.current).toBe(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(result.current).toBe(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(result.current).toBeNull()
  })

  it('restarts the countdown when given a new initial seconds value', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })

    const { result, rerender } = renderHook(({ seconds }) => useRetryCountdown(seconds), {
      initialProps: { seconds: 5 as number | undefined },
    })
    expect(result.current).toBe(5)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(result.current).toBe(4)

    rerender({ seconds: 10 })
    expect(result.current).toBe(10)
  })
})
