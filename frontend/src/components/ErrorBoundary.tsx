import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { traducirSinHook } from '../i18n/traducirSinHook'
import './ErrorBoundary.css'

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
        <div className="erroboun-stack-1">
          <div className="erroboun-txt-1">⚠️</div>
          <h2 className="erroboun-box-1">{traducirSinHook('errorboundary.algo_fue_mal')}</h2>
          <p className="erroboun-box-2">
            {traducirSinHook('errorboundary.se_produjo_un_error_inesperado')}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="erroboun-box-3"
          >
            {traducirSinHook('errorboundary.recargar_pagina')}
          </button>
          {import.meta.env.DEV && this.state.error && (
            <pre className="erroboun-box-4">
              {this.state.error.toString()}
            </pre>
          )}
        </div>
      )
    }
    return this.props.children
  }
}
