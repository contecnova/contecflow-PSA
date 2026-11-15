import { Component } from 'react'
import type { ComponentType, ErrorInfo, ReactNode } from 'react'
import { traducirSinHook } from '../i18n/traducirSinHook'
import { apiUrl } from '../services/api/urls'
import './RouteBoundary.css'

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
        className="routboun-stack-1"
      >
        <div className="routboun-txt-1">⚠️</div>
        <h3 className="routboun-box-1">
          {traducirSinHook('routeboundary.esta_seccion_tuvo_un_error')}
          {section ? ` (${section})` : ''}
        </h3>
        <p className="routboun-box-2">
          {traducirSinHook('routeboundary.algo_salio_mal_al_cargar')}
        </p>
        <div className="routboun-row-1">
          <button
            onClick={this.handleRetry}
            className="routboun-box-3"
          >
            {traducirSinHook('routeboundary.reintentar')}
          </button>
          <button
            onClick={this.handleReload}
            className="routboun-box-4"
          >
            {traducirSinHook('routeboundary.recargar_pagina')}
          </button>
        </div>
        {isDev && (
          <pre
            className="routboun-box-5"
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
