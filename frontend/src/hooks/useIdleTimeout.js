import { useEffect, useRef, useCallback, useState } from 'react'

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click']

/**
 * useIdleTimeout — cierra la sesión tras N minutos de inactividad.
 *
 * @param {object} opts
 * @param {boolean}  opts.enabled        - Si el timeout está activado
 * @param {number}   opts.timeoutMinutes - Minutos de inactividad antes de cerrar
 * @param {function} opts.onTimeout      - Callback llamado al expirar (debe hacer logout)
 * @param {number}   [opts.warningSeconds=60] - Segundos antes del cierre en que se muestra aviso
 *
 * @returns {{ showWarning: boolean, secondsLeft: number, dismiss: function }}
 */
export function useIdleTimeout({ enabled, timeoutMinutes, onTimeout, warningSeconds = 60 }) {
  const [showWarning, setShowWarning] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(warningSeconds)

  const idleTimer   = useRef(null)
  const warnTimer   = useRef(null)
  const countdown   = useRef(null)
  const onTimeoutRef = useRef(onTimeout)

  useEffect(() => { onTimeoutRef.current = onTimeout }, [onTimeout])

  const clearAll = useCallback(() => {
    clearTimeout(idleTimer.current)
    clearTimeout(warnTimer.current)
    clearInterval(countdown.current)
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
        setSecondsLeft(s => {
          if (s <= 1) {
            clearInterval(countdown.current)
            return 0
          }
          return s - 1
        })
      }, 1000)
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
    const reset = () => startTimers()
    ACTIVITY_EVENTS.forEach(e => window.addEventListener(e, reset, { passive: true }))
    return () => {
      clearAll()
      ACTIVITY_EVENTS.forEach(e => window.removeEventListener(e, reset))
    }
  }, [enabled, startTimers, clearAll])

  return { showWarning, secondsLeft, dismiss }
}
