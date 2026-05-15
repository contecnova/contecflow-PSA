/**
 * useSwipeGesture.ts — Touch swipe + pinch-zoom gesture detection hook.
 *
 * Usage:
 *   const { onTouchStart, onTouchEnd, onTouchMove } = useSwipeGesture({
 *     onSwipeLeft: () => goNext(),
 *     onSwipeRight: () => goPrev(),
 *     onPinchIn: () => zoomOut(),
 *     onPinchOut: () => zoomIn(),
 *     threshold: 50,
 *   })
 *   <div onTouchStart={onTouchStart} onTouchEnd={onTouchEnd} onTouchMove={onTouchMove}>...</div>
 */
import { useRef, useCallback } from 'react'
import type { TouchEvent as ReactTouchEvent } from 'react'

const DEFAULT_THRESHOLD = 50  // px
const DEFAULT_VELOCITY_THRESHOLD = 0.3  // px/ms
const PINCH_THRESHOLD = 20  // px distance change to trigger pinch

export interface UseSwipeGestureOptions {
  onSwipeLeft?: () => void
  onSwipeRight?: () => void
  onSwipeUp?: () => void
  onSwipeDown?: () => void
  /** fingers coming together (zoom out) */
  onPinchIn?: (delta: number) => void
  /** fingers spreading (zoom in) */
  onPinchOut?: (delta: number) => void
  threshold?: number
  velocityThreshold?: number
  pinchThreshold?: number
}

export interface UseSwipeGestureHandlers {
  onTouchStart: (e: ReactTouchEvent) => void
  onTouchMove: (e: ReactTouchEvent) => void
  onTouchEnd: (e: ReactTouchEvent) => void
  onTouchCancel: () => void
}

interface TouchSnapshot {
  x: number
  y: number
  time: number
}

export function useSwipeGesture({
  onSwipeLeft,
  onSwipeRight,
  onSwipeUp,
  onSwipeDown,
  onPinchIn,
  onPinchOut,
  threshold = DEFAULT_THRESHOLD,
  velocityThreshold = DEFAULT_VELOCITY_THRESHOLD,
  pinchThreshold = PINCH_THRESHOLD,
}: UseSwipeGestureOptions = {}): UseSwipeGestureHandlers {
  const touchStart = useRef<TouchSnapshot | null>(null)
  const pinchStart = useRef<number | null>(null)

  const _pinchDist = (touches: TouchList | React.TouchList): number => {
    const dx = touches[0].clientX - touches[1].clientX
    const dy = touches[0].clientY - touches[1].clientY
    return Math.sqrt(dx * dx + dy * dy)
  }

  const onTouchStart = useCallback((e: ReactTouchEvent) => {
    if (e.touches.length === 2) {
      // Two-finger pinch start
      pinchStart.current = _pinchDist(e.touches)
      touchStart.current = null
      return
    }
    const touch = e.touches[0]
    touchStart.current = {
      x: touch.clientX,
      y: touch.clientY,
      time: Date.now(),
    }
    pinchStart.current = null
  }, [])

  const onTouchMove = useCallback((e: ReactTouchEvent) => {
    if (e.touches.length === 2 && pinchStart.current !== null) {
      e.preventDefault?.()
      const dist = _pinchDist(e.touches)
      const delta = dist - pinchStart.current
      if (Math.abs(delta) >= pinchThreshold) {
        if (delta < 0 && onPinchIn) onPinchIn(delta)
        else if (delta > 0 && onPinchOut) onPinchOut(delta)
        pinchStart.current = dist  // reset so continuous pinch fires incrementally
      }
    }
  }, [onPinchIn, onPinchOut, pinchThreshold])

  const onTouchEnd = useCallback((e: ReactTouchEvent) => {
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
    pinchStart.current = null
  }, [])

  return { onTouchStart, onTouchMove, onTouchEnd, onTouchCancel }
}

export default useSwipeGesture
