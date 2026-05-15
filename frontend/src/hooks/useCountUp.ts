import { useEffect, useRef, useState } from 'react'

export type CountUpTarget = number | string

/**
 * useCountUp — Animates a number from 0 (or prev value) to `target`.
 * Returns the current animated value as a string.
 * @param target — final value
 * @param duration — animation duration in ms (default 700)
 * @param enabled — only animate when true (e.g. data loaded)
 */
export default function useCountUp(
  target: CountUpTarget,
  duration = 700,
  enabled = true,
): CountUpTarget {
  const [display, setDisplay] = useState<CountUpTarget>(target)
  const rafRef = useRef<number | null>(null)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (!enabled) { setDisplay(target); return }

    // If target is not a pure number, just set it directly
    const numeric = typeof target === 'string' ? parseFloat(target.replace(/[^0-9.-]/g, '')) : target
    if (isNaN(numeric) || (typeof target === 'string' && /[^0-9.\-%€$h]/.test(target))) {
      setDisplay(target)
      return
    }

    const startVal = 0
    startRef.current = null
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)

    const isFloat = String(target).includes('.')
    const decimalPlaces = isFloat ? (String(target).split('.')[1]?.length || 1) : 0
    // Suffix detection (%, h, €, $)
    const suffix = typeof target === 'string' ? target.replace(/[-0-9.]/g, '').trim() : ''

    const tick = (timestamp: number): void => {
      if (startRef.current === null) startRef.current = timestamp
      const elapsed = timestamp - startRef.current
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const ease = 1 - Math.pow(1 - progress, 3)
      const current = startVal + (numeric - startVal) * ease

      const formatted = isFloat
        ? current.toFixed(decimalPlaces) + suffix
        : Math.round(current) + suffix

      setDisplay(formatted)

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [target, duration, enabled])

  return display
}
