import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { traducirSinHook } from '../i18n/traducirSinHook'

interface ErrorBoundaryProps {
  children?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log to console in dev; Sentry would capture in prod via its own error boundary
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100vh',
          background: 'var(--surface-0)', gap: 16, padding: 32,
        }}>
          <div style={{ fontSize: 40 }}>⚠️</div>
          <h2 style={{ color: 'var(--text-1)', margin: 0 }}>{traducirSinHook('errorboundary.algo_fue_mal')}</h2>
          <p style={{ color: 'var(--text-3)', margin: 0, textAlign: 'center' }}>
            {traducirSinHook('errorboundary.se_produjo_un_error_inesperado')}
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 20px', background: 'var(--accent)', color: '#fff',
              border: 'none', borderRadius: 8, cursor: 'pointer',
              fontSize: 14, fontFamily: 'inherit',
            }}
          >
            {traducirSinHook('errorboundary.recargar_pagina')}
          </button>
          {import.meta.env.DEV && this.state.error && (
            <pre style={{
              background: 'var(--surface-2)', padding: 16, borderRadius: 8,
              color: 'var(--danger)', fontSize: 12, maxWidth: 800,
              overflow: 'auto', maxHeight: 300,
            }}>
              {this.state.error.toString()}
            </pre>
          )}
        </div>
      )
    }
    return this.props.children
  }
}
