import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { AppLangProvider } from './i18n/AppLangContext'
import { AuthProvider } from './context/AuthContext'
import { useAppT } from './hooks/useAppT'
import { initOfflineSync } from './services/offlineQueue'
import api from './services/api'
import './index.css'

// Initialize offline sync — auto-syncs queued imputations when the browser comes back online
initOfflineSync(api, ({ synced, failed }) => {
  if (synced > 0) console.warn(`[Clarive] Offline sync: ${synced} imputations uploaded${failed ? `, ${failed} failed` : ''}`)
})

// ── Error Boundary — captura errores de render Y de lazy loading ──────────────
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('[Clarive] Error capturado:', error)
    console.error('[Clarive] Componente:', errorInfo?.componentStack)
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
          <div style={{ fontSize: 56, marginBottom: 20 }}>⚠</div>
          <h2 style={{ color: 'var(--danger)', marginBottom: 12, fontSize: 22 }}>
            {isChunkError ? this.props.t('app_errors.app_load_outdated') : this.props.t('app_errors.app_load_failed')}
          </h2>
          {isChunkError ? (
            <p style={{ color: 'var(--text-2)', marginBottom: 24, maxWidth: 500 }}>
              {this.props.t('app_errors.app_outdated_desc')}
            </p>
          ) : (
            <pre style={{
              background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8,
              padding: 20, maxWidth: 700, width: '100%', overflow: 'auto',
              fontSize: 12, color: 'var(--warning)', lineHeight: 1.6, textAlign: 'left',
              marginBottom: 24,
            }}>
              {err?.message}{'\n\n'}{err?.stack?.split('\n').slice(0, 6).join('\n')}
            </pre>
          )}
          <button
            onClick={() => {
              // Limpiar caché y recargar
              if ('caches' in window) {
                caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
              }
              window.location.reload(true)
            }}
            style={{
              padding: '12px 28px', background: 'var(--accent)', border: 'none',
              borderRadius: 8, color: 'var(--surface-0)', cursor: 'pointer',
              fontWeight: 700, fontSize: 15,
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

function RootBoundary({ children }) {
  const t = useAppT()
  return <ErrorBoundary t={t}>{children}</ErrorBoundary>
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

// ── Render ────────────────────────────────────────────────────────────────────
ReactDOM.createRoot(document.getElementById('root')).render(
  <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
    <AuthProvider>
      <AppLangProvider>
        <QueryClientProvider client={queryClient}>
          <RootBoundary>
            <App />
          </RootBoundary>
        </QueryClientProvider>
      </AppLangProvider>
    </AuthProvider>
  </BrowserRouter>
)
