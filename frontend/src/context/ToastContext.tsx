/**
 * ToastContext — Sistema global de notificaciones no bloqueantes
 * Reemplaza todos los alert() del sistema
 * Uso: const toast = useToast(); toast.success('Guardado'); toast.error('Error')
 */
import { createContext, useContext, useState, useCallback, useRef } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useAppT } from '../hooks/useAppT'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: number
  type: ToastType
  message: string
}

export type ToastMessage = string | number | null | undefined | unknown[] | Record<string, unknown>

export interface ToastApi {
  success: (msg: ToastMessage, duration?: number) => number
  error: (msg: ToastMessage, duration?: number) => number
  warning: (msg: ToastMessage, duration?: number) => number
  info: (msg: ToastMessage, duration?: number) => number
}

const ToastContext = createContext<ToastApi | null>(null)

const ICONS: Record<ToastType, string> = {
  success: '✓',
  error:   '✕',
  warning: '⚠',
  info:    'ℹ',
}

interface ToastColor {
  bg: string
  text: string
  border: string
}

const COLORS: Record<ToastType, ToastColor> = {
  success: { bg: 'var(--success)', text: 'var(--success-bg)', border: 'var(--success)' },
  error:   { bg: 'var(--danger)', text: 'var(--danger-bg)', border: 'var(--danger)' },
  warning: { bg: 'var(--warning)', text: 'var(--warning-bg)', border: 'var(--warning)' },
  info:    { bg: 'var(--accent)', text: 'var(--surface-0)', border: 'var(--accent)' },
}

let _id = 0

interface ToastProviderProps {
  children?: ReactNode
}

export function ToastProvider({ children }: ToastProviderProps) {
  const { t } = useAppT()
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})

  const dismiss = useCallback((id: number) => {
    clearTimeout(timers.current[id])
    setToasts(curr => curr.filter(x => x.id !== id))
  }, [])

  const add = useCallback((type: ToastType, message: ToastMessage, duration = 4000): number => {
    const id = ++_id
    // Normalise message to string — Pydantic 422 detail is an array of objects
    let msg: unknown = message
    if (Array.isArray(msg)) msg = msg.map((d: unknown) => (d as { msg?: string })?.msg || String(d)).filter(Boolean).join(' · ')
    else if (msg !== null && typeof msg === 'object') msg = String(msg)
    else if (msg == null) msg = t('toast.unexpected_error')
    setToasts(curr => [...curr.slice(-4), { id, type, message: String(msg) }])
    timers.current[id] = setTimeout(() => dismiss(id), duration)
    return id
  }, [dismiss, t])

  const toast: ToastApi = {
    success: (msg, d) => add('success', msg, d),
    error:   (msg, d) => add('error',   msg, d || 6000),
    warning: (msg, d) => add('warning', msg, d),
    info:    (msg, d) => add('info',    msg, d),
  }

  const containerStyle: CSSProperties = {
    position: 'fixed', bottom: 24, right: 24,
    display: 'flex', flexDirection: 'column', gap: 10,
    // CSS variable is a valid value at runtime although the type expects number
    zIndex: 'var(--z-toast)' as unknown as number,
    pointerEvents: 'none',
  }

  return (
    <ToastContext.Provider value={toast}>
      {children}
      {/* Toast container */}
      <div style={containerStyle}>
        {toasts.map(item => {
          const c = COLORS[item.type]
          return (
            <div key={item.id} style={{
              pointerEvents: 'all',
              display: 'flex', alignItems: 'center', gap: 12,
              background: 'var(--surface-1)',
              border: `1px solid ${c.border}40`,
              borderLeft: `4px solid ${c.bg}`,
              borderRadius: 10,
              padding: '12px 16px',
              minWidth: 280, maxWidth: 420,
              boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
              animation: 'toast-in 0.25s ease',
              fontFamily: 'inherit',
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                background: c.bg + '20', border: `1px solid ${c.bg}40`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 'var(--text-md)', fontWeight: 800, color: c.bg,
              }}>{ICONS[item.type]}</div>
              <div style={{ flex: 1, fontSize: 'var(--text-base)', color: 'var(--text-1)', lineHeight: 1.4 }}>
                {item.message}
              </div>
              <button onClick={() => dismiss(item.id)} style={{
                background: 'none', border: 'none', color: 'var(--text-2)',
                cursor: 'pointer', fontSize: 'var(--text-lg)', padding: '0 2px', lineHeight: 1,
                flexShrink: 0,
              }}>×</button>
            </div>
          )
        })}
      </div>
      <style>{`
        @keyframes toast-in {
          from { opacity: 0; transform: translateX(40px) scale(0.95); }
          to   { opacity: 1; transform: translateX(0) scale(1); }
        }
      `}</style>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be inside ToastProvider')
  return ctx
}

export default ToastContext
