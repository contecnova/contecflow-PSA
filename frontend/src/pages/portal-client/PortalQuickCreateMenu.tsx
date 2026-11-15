/**
 * PortalQuickCreateMenu — réplica del QuickCreateMenu del backoffice.
 *
 * Mismo layout que `frontend/src/components/layout/QuickCreateMenu.jsx`:
 *   panel flotante 280px en top:52 / right:16, header "Crear nuevo",
 *   tarjetas con icono coloreado y label.
 *
 * Acciones navegan a secciones del portal (algunas con flag que abre modal).
 */
import { type CSSProperties, useEffect, useRef } from 'react'
import type { ComponentType } from 'react'
import {
  X, Headphones, Lightbulb, MessageSquare, FileSignature,
  Receipt, FlaskConical, Sparkles,
} from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'
import './PortalQuickCreateMenu.css'

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
        className="poqucrme-box-1" />
      <div ref={panelRef}
        role="dialog" aria-label={t('portalquickcreatemenu.crear_nuevo')} className="portalqu-sx1"
      >
        <div className="poqucrme-row-1">
          <span>{t('portalquickcreatemenu.crear_nuevo')}</span>
          <button onClick={onClose} aria-label={t('common.close')}
            className="poqucrme-row-2">
            <X size={13} />
          </button>
        </div>
        <div className="poqucrme-stack-1">
          {ACTIONS.map(({ id, icon: Icon, label, hint, color, run }) => (
            <button key={id} onClick={() => { run(); onClose() }}
              className="poqucrme-row-3"
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div className="poqucrme-row-4 portalqu-sx2 portal-quick-create-menu-e1" style={{ '--portal-quick-create-menu-background': alpha(color, '15'), '--portal-quick-create-menu-border': `1px solid ${alpha(color, '30')}` } as CSSProperties}>
                <Icon size={15} color={color} />
              </div>
              <div className="u-flex1-min0">
                <div className="u-text1-base-600">{label}</div>
                {hint && <div className="u-text3-xs">{hint}</div>}
              </div>
            </button>
          ))}
        </div>
      </div>
    </>
  )
}
