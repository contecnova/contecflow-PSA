import { useEffect, useRef, useCallback, useState } from 'react'
import { CLOCK_TICK_MS } from '../constants/timings'

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'] as const

export interface UseIdleTimeoutOptions {
  /** Si el timeout está activado */
  enabled: boolean
  /** Minutos de inactividad antes de cerrar */
  timeoutMinutes: number | null | undefined
  /** Callback llamado al expirar (debe hacer logout) */
  onTimeout: () => void
  /** Segundos antes del cierre en que se muestra aviso (default 60) */
  warningSeconds?: number
}

export interface UseIdleTimeoutResult {
  showWarning: boolean
  secondsLeft: number
  dismiss: () => void
}

/**
 * useIdleTimeout — cierra la sesión tras N minutos de inactividad.
 */
export function useIdleTimeout({
  enabled,
  timeoutMinutes,
  onTimeout,
  warningSeconds = 60,
}: UseIdleTimeoutOptions): UseIdleTimeoutResult {
  const [showWarning, setShowWarning] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(warningSeconds)

  const idleTimer   = useRef<ReturnType<typeof setTimeout> | null>(null)
  const warnTimer   = useRef<ReturnType<typeof setTimeout> | null>(null)
  const countdown   = useRef<ReturnType<typeof setInterval> | null>(null)
  const onTimeoutRef = useRef<() => void>(onTimeout)

  useEffect(() => { onTimeoutRef.current = onTimeout }, [onTimeout])

  const clearAll = useCallback(() => {
    if (idleTimer.current) clearTimeout(idleTimer.current)
    if (warnTimer.current) clearTimeout(warnTimer.current)
    if (countdown.current) clearInterval(countdown.current)
  }, [])

  const startTimers = useCallback(() => {
    if (!enabled || !timeoutMinutes) return
    clearAll()
    setShowWarning(false)

    const totalMs   = timeoutMinutes * 60 * 1000
    const warnMs    = Math.max(totalMs - warningSeconds * 1000, 0)

    // Show warning when warnMs have elapsed
    warnTimer.current = setTimeout(() => {
      setShowWarning(true)
      setSecondsLeft(warningSeconds)
      countdown.current = setInterval(() => {
        setSecondsLeft((s) => {
          if (s <= 1) {
            if (countdown.current) clearInterval(countdown.current)
            return 0
          }
          return s - 1
        })
      }, CLOCK_TICK_MS)
    }, warnMs)

    // Force logout when totalMs have elapsed
    idleTimer.current = setTimeout(() => {
      clearAll()
      setShowWarning(false)
      onTimeoutRef.current?.()
    }, totalMs)
  }, [enabled, timeoutMinutes, warningSeconds, clearAll])

  // Dismiss warning and restart timers (user clicked "Continuar")
  const dismiss = useCallback(() => {
    setShowWarning(false)
    startTimers()
  }, [startTimers])

  useEffect(() => {
    if (!enabled) {
      clearAll()
      setShowWarning(false)
      return
    }
    startTimers()
    const reset = (): void => { startTimers() }
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, reset, { passive: true }))
    return () => {
      clearAll()
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, reset))
    }
  }, [enabled, startTimers, clearAll])

  return { showWarning, secondsLeft, dismiss }
}
