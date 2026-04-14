import { useEffect, useRef, useState } from 'react'

/**
 * useCountUp — Animates a number from 0 (or prev value) to `target`.
 * Returns the current animated value as a string.
 * @param {number|string} target — final value
 * @param {number} duration — animation duration in ms (default 700)
 * @param {boolean} enabled — only animate when true (e.g. data loaded)
 */
export default function useCountUp(target, duration = 700, enabled = true) {
  const [display, setDisplay] = useState(target)
  const rafRef = useRef(null)
  const startRef = useRef(null)

  useEffect(() => {
    if (!enabled) { setDisplay(target); return }

    // If target is not a pure number, just set it directly
    const numeric = typeof target === 'string' ? parseFloat(target.replace(/[^0-9.-]/g, '')) : target
    if (isNaN(numeric) || typeof target === 'string' && /[^0-9.\-%€$h]/.test(target)) {
      setDisplay(target)
      return
    }

    let startVal = 0
    startRef.current = null
    cancelAnimationFrame(rafRef.current)

    const isFloat = String(target).includes('.')
    const decimalPlaces = isFloat ? (String(target).split('.')[1]?.length || 1) : 0
    // Suffix detection (%, h, €, $)
    const suffix = typeof target === 'string' ? target.replace(/[-0-9.]/g, '').trim() : ''

    const tick = (timestamp) => {
      if (!startRef.current) startRef.current = timestamp
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
    return () => cancelAnimationFrame(rafRef.current)
  }, [target, duration, enabled])

  return display
}
