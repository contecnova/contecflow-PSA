/// <reference types="vite/client" />
// Patch HTMLCanvasElement.getContext so Plotly 3D charts don't trigger the
// "willReadFrequently" browser warning on repeated getImageData calls.
// Audit #C9: getContext is a heavily overloaded method (2d / webgl / bitmaprenderer
// / webgl2). Re-typing the patched signature would require replicating every
// overload, so we cast through `any` once at the install site instead.
;(function patchCanvasGetContext() {
  const _orig = HTMLCanvasElement.prototype.getContext
  ;(HTMLCanvasElement.prototype as unknown as { getContext: unknown }).getContext = function (this: HTMLCanvasElement, type: string, attrs?: unknown) {
    if (type === '2d') {
      attrs = { willReadFrequently: true, ...(attrs as object | undefined) }
    }
    return (_orig as unknown as (type: string, attrs?: unknown) => unknown).call(this, type, attrs)
  }
})()

import React from 'react'
import type { ReactNode } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient} from '@tanstack/react-query'
import App from './App'
import AppProviders from './AppProviders'
import { useAppT } from './hooks/useAppT'
import type { TranslationParams } from './hooks/useAppT'
// TODO type: services/offlineQueue still JS
import { initOfflineSync } from './services/offlineQueue'
// TODO type: services/api still JS
import api from './services/api'
import './index.css'

// Initialize offline sync — auto-syncs queued imputations when the browser comes back online
const _bootOfflineSync = () => {
  initOfflineSync(api, ({ synced, failed }: { synced: number; failed: number }) => {
    if (synced > 0) console.warn(`[Contecflow] Offline sync: ${synced} imputations uploaded${failed ? `, ${failed} failed` : ''}`)
  })
}

if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
  ;(window as Window & { requestIdleCallback: (cb: () => void, opts?: { timeout: number }) => void }).requestIdleCallback(
    _bootOfflineSync,
    { timeout: 1500 },
  )
} else {
  setTimeout(_bootOfflineSync, 0)
}

// ── Error Boundary — captura errores de render Y de lazy loading ──────────────
interface RootErrorBoundaryProps {
  children?: ReactNode
  // i18n translator — TODO type: useAppT().t signature
  t: (key: string, vars?: Record<string, unknown>) => string
}
interface RootErrorBoundaryState {
  error: Error | null
  errorInfo: React.ErrorInfo | null
}
class ErrorBoundary extends React.Component<RootErrorBoundaryProps, RootErrorBoundaryState> {
  constructor(props: RootErrorBoundaryProps) {
    super(props)
    this.state = { error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error: Error): Partial<RootErrorBoundaryState> {
    return { error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[Contecflow] Error capturado:', error)
    console.error('[Contecflow] Componente:', errorInfo?.componentStack)
    this.setState({ errorInfo })
  }

  render() {
    if (this.state.error) {
      const err = this.state.error
      const isChunkError = err?.message?.includes('Failed to fetch dynamically imported module')
        || err?.message?.includes('Loading chunk')
        || err?.message?.includes('Importing a module')

      return (
        <div style={{
          minHeight: '100vh', background: 'var(--surface-0)', color: 'var(--text-1)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          fontFamily: 'system-ui, sans-serif', padding: 40, textAlign: 'center',
        }}>
          <div style={{ fontSize: "var(--text-56)", marginBottom: 20 }}>⚠</div>
          <h2 style={{ color: 'var(--danger)', marginBottom: 12, fontSize: "var(--text-xl-em)" }}>
            {isChunkError ? this.props.t('app_errors.app_load_outdated') : this.props.t('app_errors.app_load_failed')}
          </h2>
          {isChunkError ? (
            <p style={{ color: 'var(--text-2)', marginBottom: 24, maxWidth: 500 }}>
              {this.props.t('app_errors.app_outdated_desc')}
            </p>
          ) : (
            import.meta.env.DEV ? (
              <pre style={{
                background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8,
                padding: 20, maxWidth: 700, width: '100%', overflow: 'auto',
                fontSize: "var(--text-sm)", color: 'var(--warning)', lineHeight: 1.6, textAlign: 'left',
                marginBottom: 24,
              }}>
                {err?.message}{'\n\n'}{err?.stack?.split('\n').slice(0, 6).join('\n')}
              </pre>
            ) : (
              <p style={{ color: 'var(--text-2)', marginBottom: 24, maxWidth: 500 }}>
                {this.props.t('app_errors.app_unexpected_desc')}
              </p>
            )
          )}
          <button
            onClick={() => {
              // Limpiar caché y recargar
              if ('caches' in window) {
                caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
              }
              window.location.reload()
            }}
            style={{
              padding: '12px 28px', background: 'var(--accent)', border: 'none',
              borderRadius: 8, color: 'var(--surface-0)', cursor: 'pointer',
              fontWeight: 700, fontSize: "var(--text-md-em)",
            }}
          >
            {this.props.t('app_errors.app_reload')}
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function RootBoundary({ children }: { children?: ReactNode }) {
  const { t } = useAppT()
  const translate = (key: string, vars?: Record<string, unknown>) => t(key, vars as TranslationParams | undefined)
  return <ErrorBoundary t={translate}>{children}</ErrorBoundary>
}

// ── QueryClient ───────────────────────────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime:            30 * 1000,      // 30s — datos siempre frescos
      gcTime:               5 * 60 * 1000,  // 5min cache
      refetchOnWindowFocus: true,            // refrescar al volver a la ventana
      retry:                1,
    },
    mutations: {
      retry: false,   // las mutaciones no deben reintentarse automáticamente
    },
  },
})

// Suppress the React DevTools development hint — informational-only, not actionable.
if (import.meta.env.DEV) {
  const _consoleLog = console.log
  const _consoleInfo = console.info
  const isDevToolsHint = (msg: unknown): boolean => typeof msg === 'string' && msg.includes('Download the React DevTools')
  console.log = (...args: unknown[]) => {
    if (isDevToolsHint(args[0])) return
    _consoleLog.apply(console, args as Parameters<typeof console.log>)
  }
  console.info = (...args: unknown[]) => {
    if (isDevToolsHint(args[0])) return
    _consoleInfo.apply(console, args as Parameters<typeof console.info>)
  }
}

// ── Render ────────────────────────────────────────────────────────────────────
const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Root element #root not found in index.html')
// Auditoria 2026-09: el `BrowserRouter` llevaba
// `future={{ v7_startTransition: true, v7_relativeSplatPath: true }}`. Esas dos
// banderas servian para adoptar por adelantado el comportamiento de
// react-router 7 estando en la 6; con la 7 instalada **son el comportamiento
// por defecto** y la prop ya no existe, asi que dejarla puesta es un error de
// tipos. Que el proyecto las tuviera activadas es la razon de que la migracion
// 6 -> 7 no haya cambiado nada mas: el codigo ya corria con la semantica nueva.
ReactDOM.createRoot(rootEl).render(
  <BrowserRouter>
    <AppProviders queryClient={queryClient}>
      <RootBoundary>
        <App />
      </RootBoundary>
    </AppProviders>
  </BrowserRouter>
)

// Register service worker for offline support in production builds.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((err: unknown) => {
      console.warn('[Contecflow] Service worker registration failed:', err)
    })
  })
}
