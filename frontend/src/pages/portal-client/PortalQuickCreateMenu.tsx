/**
 * PortalQuickCreateMenu — réplica del QuickCreateMenu del backoffice.
 *
 * Mismo layout que `frontend/src/components/layout/QuickCreateMenu.jsx`:
 *   panel flotante 280px en top:52 / right:16, header "Crear nuevo",
 *   tarjetas con icono coloreado y label.
 *
 * Acciones navegan a secciones del portal (algunas con flag que abre modal).
 */
import { useEffect, useRef } from 'react'
import type { ComponentType } from 'react'
import {
  X, Headphones, Lightbulb, MessageSquare, FileSignature,
  Receipt, FlaskConical, Sparkles,
} from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'

interface PortalQuickCreateBadges {
  uat?: number
  documents?: number
  invoices?: number
  surveys?: number
}

interface PortalQuickCreateMenuProps {
  onClose: () => void
  onAction: (target: string, params?: Record<string, unknown>) => void
  badges?: PortalQuickCreateBadges
}

interface QuickAction {
  id: string
  icon: ComponentType<{ size?: number; color?: string }>
  label: string
  hint?: string
  color: string
  run: () => void
}

export default function PortalQuickCreateMenu({ onClose, onAction, badges = {} }: PortalQuickCreateMenuProps) {
  const { t } = useAppLang()
  const panelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const ACTIONS = [
    {
      id: 'ticket', icon: Headphones, label: 'Abrir ticket de soporte',
      hint: 'Service desk', color: 'var(--warning, #f59e0b)',
      run: () => onAction('support', { mode: 'create' }),
    },
    {
      id: 'request', icon: Lightbulb, label: 'Solicitar cambio',
      hint: 'Feature request', color: 'var(--accent)',
      run: () => onAction('requests', { mode: 'create' }),
    },
    {
      id: 'message', icon: MessageSquare, label: 'Enviar mensaje al equipo',
      hint: 'Mensajes',
      color: 'var(--purple, #7c3aed)',
      run: () => onAction('messages'),
    },
    (badges.uat ?? 0) > 0 && {
      id: 'uat', icon: FlaskConical, label: `Ejecutar UAT pendiente (${badges.uat})`,
      hint: 'UAT', color: 'var(--accent)',
      run: () => onAction('uat'),
    },
    (badges.documents ?? 0) > 0 && {
      id: 'sign', icon: FileSignature, label: `Firmar documento (${badges.documents})`,
      hint: 'Documentos', color: 'var(--warning, #f59e0b)',
      run: () => onAction('documents'),
    },
    (badges.invoices ?? 0) > 0 && {
      id: 'invoice', icon: Receipt, label: `Aprobar factura (${badges.invoices})`,
      hint: 'Facturas', color: 'var(--warning, #f59e0b)',
      run: () => onAction('invoices'),
    },
    (badges.surveys ?? 0) > 0 && {
      id: 'survey', icon: Sparkles, label: `Responder encuesta (${badges.surveys})`,
      hint: 'Encuestas', color: 'var(--purple, #7c3aed)',
      run: () => onAction('surveys'),
    },
  ].filter(Boolean) as QuickAction[]

  return (
    <>
      <div role="presentation" onMouseDown={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 500 }} />
      <div ref={panelRef}
        role="dialog" aria-label={t('portalquickcreatemenu.crear_nuevo')}
        style={{
          position: 'fixed', top: 52, right: 16, zIndex: 501,
          width: 300,
          background: 'var(--surface-1)',
          border: '1px solid var(--surface-4)',
          borderRadius: 12,
          boxShadow: '0 12px 40px rgba(0,0,0,0.4)',
          overflow: 'hidden',
          fontFamily: 'inherit',
        }}
      >
        <div style={{
          padding: '12px 16px 8px',
          fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-3)',
          textTransform: 'uppercase', letterSpacing: '.07em',
          borderBottom: '1px solid var(--surface-4)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span>{t('portalquickcreatemenu.crear_nuevo')}</span>
          <button onClick={onClose} aria-label="Cerrar"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', display: 'flex', padding: 2 }}>
            <X size={13} />
          </button>
        </div>
        <div style={{ padding: '6px 8px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {ACTIONS.map(({ id, icon: Icon, label, hint, color, run }) => (
            <button key={id} onClick={() => { run(); onClose() }}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 12px', borderRadius: 8,
                background: 'transparent', border: 'none',
                cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                width: '100%',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div style={{
                width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                background: `${color}15`, border: `1px solid ${color}30`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Icon size={15} color={color} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--text-1)' }}>{label}</div>
                {hint && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{hint}</div>}
              </div>
            </button>
          ))}
        </div>
      </div>
    </>
  )
}
