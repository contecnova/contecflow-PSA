import { Component } from 'react'
import type { ComponentType, ErrorInfo, ReactNode } from 'react'
import { traducirSinHook } from '../i18n/traducirSinHook'
import { apiUrl } from '../services/api/urls'

/**
 * RouteBoundary — per-section error boundary.
 *
 * Wraps a subtree (typically a lazy-loaded page or a group of routes) so
 * that a render error inside it does NOT derail the whole app. Unlike the
 * global `ErrorBoundary`, this one renders a contained, inline fallback so
 * the surrounding Layout/sidebar/topbar remain interactive.
 *
 * Props:
 *  - section: human-readable section label used in the fallback + log.
 *  - children: subtree to protect.
 *  - resetKey: optional key (e.g. pathname) that, when changed, clears the
 *    error state so navigating away from a broken page recovers the UI.
 */
interface RouteBoundaryProps {
  section?: string
  resetKey?: string | number | null
  children?: ReactNode
}

interface RouteBoundaryState {
  error: Error | null
}

export default class RouteBoundary extends Component<RouteBoundaryProps, RouteBoundaryState> {
  constructor(props: RouteBoundaryProps) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error: Error): RouteBoundaryState {
    return { error }
  }

  componentDidUpdate(prevProps: RouteBoundaryProps) {
    if (this.state.error && this.props.resetKey !== prevProps.resetKey) {
      this.setState({ error: null })
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    const section = this.props.section || 'unknown'
    // Local console log — always available.
    console.error(`[RouteBoundary:${section}]`, error, info?.componentStack)

    // Best-effort report to backend (non-blocking, fire-and-forget).
    try {
      const payload = {
        section,
        message: String(error?.message || error),
        stack: String(error?.stack || ''),
        component_stack: String(info?.componentStack || ''),
        url: typeof window !== 'undefined' ? window.location.href : '',
        ua: typeof navigator !== 'undefined' ? navigator.userAgent : '',
        ts: new Date().toISOString(),
      }
      if (typeof fetch === 'function') {
        // fetch directo a propósito: informe con `keepalive` desde un error boundary a POST /api/v1/client-errors (público, solo log) y sin depender de los interceptores del cliente (un 401 aquí no debe disparar el refresco de sesión).
        // eslint-disable-next-line no-restricted-syntax
        fetch(apiUrl('/client-errors'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          credentials: 'include',
          keepalive: true,
        }).catch(() => {})
      }
    } catch {
      // Reporting must never throw out of the boundary.
    }
  }

  handleReload = () => {
    window.location.reload()
  }

  handleRetry = () => {
    this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    const section = this.props.section || ''
    const isDev = typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.DEV
    return (
      <div
        role="alert"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          padding: 32,
          gap: 12,
          textAlign: 'center',
        }}
      >
        <div style={{ fontSize: 40 }}>⚠️</div>
        <h3 style={{ color: 'var(--text-1)', margin: 0 }}>
          {traducirSinHook('routeboundary.esta_seccion_tuvo_un_error')}
          {section ? ` (${section})` : ''}
        </h3>
        <p style={{ color: 'var(--text-3)', margin: 0, maxWidth: 480 }}>
          {traducirSinHook('routeboundary.algo_salio_mal_al_cargar')}
        </p>
        <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
          <button
            onClick={this.handleRetry}
            style={{
              padding: '8px 18px',
              background: 'var(--surface-2)',
              color: 'var(--text-1)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            Reintentar
          </button>
          <button
            onClick={this.handleReload}
            style={{
              padding: '8px 18px',
              background: 'var(--accent)',
              color: 'var(--on-accent-light)',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            {traducirSinHook('routeboundary.recargar_pagina')}
          </button>
        </div>
        {isDev && (
          <pre
            style={{
              background: 'var(--surface-2)',
              padding: 12,
              borderRadius: 8,
              color: 'var(--danger)',
              fontSize: 12,
              maxWidth: 720,
              overflow: 'auto',
              maxHeight: 220,
              marginTop: 12,
            }}
          >
            {String(this.state.error?.stack || this.state.error)}
          </pre>
        )}
      </div>
    )
  }
}

/**
 * withRouteBoundary(Page, sectionLabel)
 *
 * HOC that wraps a lazy/regular page component in a RouteBoundary so the
 * page can crash in isolation without taking the rest of the app down.
 *
 * Usage:
 *   const SafeBIPage = withRouteBoundary(BIPage, 'BI')
 *   <Route path="/executive" element={<SafeBIPage />} />
 */
export function withRouteBoundary<P extends object>(
  PageComponent: ComponentType<P>,
  section?: string,
): ComponentType<P> {
  function Wrapped(props: P) {
    return (
      <RouteBoundary section={section}>
        <PageComponent {...props} />
      </RouteBoundary>
    )
  }
  Wrapped.displayName = `withRouteBoundary(${section || PageComponent.displayName || PageComponent.name || 'Component'})`
  return Wrapped
}
