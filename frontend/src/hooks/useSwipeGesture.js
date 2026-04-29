/**
 * useSwipeGesture.js — Touch swipe gesture detection hook.
 * 
 * Usage:
 *   const { onTouchStart, onTouchEnd } = useSwipeGesture({
 *     onSwipeLeft: () => goNext(),
 *     onSwipeRight: () => goPrev(),
 *     threshold: 50,
 *   })
 *   <div onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>...</div>
 */
import { useRef, useCallback } from 'react'

const DEFAULT_THRESHOLD = 50  // px
const DEFAULT_VELOCITY_THRESHOLD = 0.3  // px/ms

/**
 * @param {object} opts
 * @param {function} [opts.onSwipeLeft]   — swipe left (next)
 * @param {function} [opts.onSwipeRight]  — swipe right (prev)
 * @param {function} [opts.onSwipeUp]     — swipe up
 * @param {function} [opts.onSwipeDown]   — swipe down
 * @param {number}   [opts.threshold=50]  — minimum distance in px
 * @param {number}   [opts.velocityThreshold=0.3] — minimum px/ms velocity
 */
export function useSwipeGesture({
  onSwipeLeft,
  onSwipeRight,
  onSwipeUp,
  onSwipeDown,
  threshold = DEFAULT_THRESHOLD,
  velocityThreshold = DEFAULT_VELOCITY_THRESHOLD,
} = {}) {
  const touchStart = useRef(null)

  const onTouchStart = useCallback((e) => {
    const touch = e.touches[0]
    touchStart.current = {
      x: touch.clientX,
      y: touch.clientY,
      time: Date.now(),
    }
  }, [])

  const onTouchEnd = useCallback((e) => {
    if (!touchStart.current) return
    const touch = e.changedTouches[0]
    const dx = touch.clientX - touchStart.current.x
    const dy = touch.clientY - touchStart.current.y
    const dt = Date.now() - touchStart.current.time
    const absDx = Math.abs(dx)
    const absDy = Math.abs(dy)
    const velocityX = absDx / dt
    const velocityY = absDy / dt

    // Determine dominant axis
    if (absDx > absDy) {
      // Horizontal
      if (absDx >= threshold && velocityX >= velocityThreshold) {
        if (dx < 0 && onSwipeLeft) onSwipeLeft()
        else if (dx > 0 && onSwipeRight) onSwipeRight()
      }
    } else {
      // Vertical
      if (absDy >= threshold && velocityY >= velocityThreshold) {
        if (dy < 0 && onSwipeUp) onSwipeUp()
        else if (dy > 0 && onSwipeDown) onSwipeDown()
      }
    }

    touchStart.current = null
  }, [onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown, threshold, velocityThreshold])

  const onTouchCancel = useCallback(() => {
    touchStart.current = null
  }, [])

  return { onTouchStart, onTouchEnd, onTouchCancel }
}

export default useSwipeGesture
