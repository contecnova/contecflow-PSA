import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * TopProgressBar — Thin top loading bar that fires on every route change.
 * Replaces the full-screen spinner for lazy-loaded pages.
 * Automatically completes when Suspense resolves.
 */
export default function TopProgressBar() {
  const location = useLocation()
  const [state, setState] = useState('idle') // idle | loading | done

  useEffect(() => {
    setState('loading')
    const t = setTimeout(() => setState('done'), 600)
    const t2 = setTimeout(() => setState('idle'), 950)
    return () => { clearTimeout(t); clearTimeout(t2) }
  }, [location.pathname])

  if (state === 'idle') return null

  return (
    <div
      role="progressbar"
      aria-label="Cargando página"
      aria-valuemin={0}
      aria-valuemax={100}
      className={state === 'done' ? 'top-progress-done' : 'top-progress-bar'}
    />
  )
}
