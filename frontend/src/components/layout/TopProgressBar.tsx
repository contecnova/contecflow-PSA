import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAppLang } from '../../i18n/AppLangContext'
import { PROGRESS_BAR_DONE_MS, PROGRESS_BAR_RESET_MS } from '../../constants/timings'

/**
 * TopProgressBar — Thin top loading bar that fires on every route change.
 * Replaces the full-screen spinner for lazy-loaded pages.
 * Automatically completes when Suspense resolves.
 */
type ProgressState = 'idle' | 'loading' | 'done'

export default function TopProgressBar() {
  const { t: traducir } = useAppLang()
  const location = useLocation()
  const [state, setState] = useState<ProgressState>('idle')

  useEffect(() => {
    setState('loading')
    const t = setTimeout(() => setState('done'), PROGRESS_BAR_DONE_MS)
    const t2 = setTimeout(() => setState('idle'), PROGRESS_BAR_RESET_MS)
    return () => { clearTimeout(t); clearTimeout(t2) }
  }, [location.pathname])

  if (state === 'idle') return null

  return (
    <div
      role="progressbar"
      aria-label={traducir('topprogressbar.cargando_pagina')}
      aria-valuemin={0}
      aria-valuemax={100}
      className={state === 'done' ? 'top-progress-done' : 'top-progress-bar'}
    />
  )
}
