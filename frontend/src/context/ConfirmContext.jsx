/**
 * ConfirmContext — reemplaza los confirm() nativos del navegador con un
 * diálogo modal estilizado, no bloqueante y accesible.
 *
 * Dos formas de uso:
 *
 * 1. Hook (dentro de un componente React):
 *    const { openConfirm } = useConfirm()
 *    openConfirm({ message: '¿Eliminar X?', onConfirm: () => del(id) })
 *
 * 2. Función global (desde cualquier sitio, sin hook):
 *    import { openConfirmGlobal } from '../context/ConfirmContext'
 *    openConfirmGlobal({ message: '…', onConfirm: fn, danger: true })
 */
import _React, { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { Button } from '../components/ui'
import { useAppT } from '../hooks/useAppT'

const ConfirmContext = createContext(null)

// Referencia mutable al handler — permite llamar desde fuera de React sin hooks
let _openConfirmRef = null

/** Llama al diálogo desde cualquier lugar (sin useConfirm hook) */
export function openConfirmGlobal(opts) {
  _openConfirmRef?.(opts)
}

export function ConfirmProvider({ children }) {
  const { t } = useAppT()
  const [state, setState] = useState({
    open: false, title: '', message: '', danger: false, onConfirm: null,
  })

  const openConfirm = useCallback(({ title, message, onConfirm, danger = false }) => {
    setState({
      open: true,
      title: title || (danger ? t('confirm_modal.danger_title') : t('confirm_modal.default_title')),
      message, danger, onConfirm,
    })
  }, [t])

  // Exponer globalmente para uso sin hook
  useEffect(() => {
    _openConfirmRef = openConfirm
    return () => { _openConfirmRef = null }
  }, [openConfirm])

  const close = useCallback(() =>
    setState(s => ({ ...s, open: false, onConfirm: null })), [])

  const handleConfirm = useCallback(() => {
    state.onConfirm?.()
    close()
  }, [state, close])

  return (
    <ConfirmContext.Provider value={{ openConfirm }}>
      {children}
      {state.open && (
        <div
          onMouseDown={close}
          role="presentation"
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(8,12,20,0.85)',
            backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 2000, padding: 24,
          }}
        >
          <div
            onMouseDown={e => e.stopPropagation()}
            role="presentation"
            style={{
              background: 'var(--surface-2)',
              border: `1px solid ${state.danger ? 'var(--danger-border)' : 'var(--surface-4)'}`,
              borderRadius: 'var(--radius-xl)',
              width: '100%', maxWidth: 420,
              padding: 28, animation: 'fadeUp 0.2s ease',
              boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
            }}
          >
            <h2 style={{ fontSize: 16, fontWeight: 700, color: state.danger ? 'var(--danger)' : 'var(--text-1)', marginBottom: 12 }}>
              {state.title}
            </h2>
            <p style={{ color: 'var(--text-2)', fontSize: 14, lineHeight: 1.6, marginBottom: 24 }}>
              {state.message}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={close}>{t('common.cancel')}</Button>
              <Button variant={state.danger ? 'danger' : 'primary'} onClick={handleConfirm}>
                {t('confirm_modal.default_title')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error('useConfirm must be used within ConfirmProvider')
  return ctx
}
