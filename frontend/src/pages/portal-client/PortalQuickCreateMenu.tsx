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
import { alpha } from '../../constants/theme'
import { useLang, rellenar } from './portalClientContext'
import './PortalQuickCreateMenu.css'
import { IconButton, Pulsable } from '../../components/ui'

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
  const t = useLang()
  const tp = useLang()
  const panelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const ACTIONS = [
    {
      id: 'ticket', icon: Headphones, label: tp('pqc_ticket'),
      hint: tp('nav_support'), color: 'var(--warning)',
      run: () => onAction('support', { mode: 'create' }),
    },
    {
      id: 'request', icon: Lightbulb, label: tp('pqc_request'),
      hint: tp('nav_requests'), color: 'var(--accent)',
      run: () => onAction('requests', { mode: 'create' }),
    },
    {
      id: 'message', icon: MessageSquare, label: tp('pqc_message'),
      hint: tp('nav_messages'),
      color: 'var(--accent)',
      run: () => onAction('messages'),
    },
    (badges.uat ?? 0) > 0 && {
      id: 'uat', icon: FlaskConical, label: rellenar(tp('pqc_uat'), { n: badges.uat }),
      hint: tp('nav_uat'), color: 'var(--accent)',
      run: () => onAction('uat'),
    },
    (badges.documents ?? 0) > 0 && {
      id: 'sign', icon: FileSignature, label: rellenar(tp('pqc_sign'), { n: badges.documents }),
      hint: tp('nav_documents'), color: 'var(--warning)',
      run: () => onAction('documents'),
    },
    (badges.invoices ?? 0) > 0 && {
      id: 'invoice', icon: Receipt, label: rellenar(tp('pqc_invoice'), { n: badges.invoices }),
      hint: tp('invoices_title'), color: 'var(--warning)',
      run: () => onAction('invoices'),
    },
    (badges.surveys ?? 0) > 0 && {
      id: 'survey', icon: Sparkles, label: rellenar(tp('pqc_survey'), { n: badges.surveys }),
      hint: tp('nav_surveys'), color: 'var(--accent)',
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
          <IconButton onClick={onClose} ariaLabel={t('common.close')}
            className="poqucrme-row-2">
            <X size={13} />
          </IconButton>
        </div>
        <div className="poqucrme-stack-1">
          {ACTIONS.map(({ id, icon: Icon, label, hint, color, run }) => (
            <Pulsable key={id} onClick={() => { run(); onClose() }}
              className="poqucrme-row-3"
            >
              <div className="poqucrme-row-4 portalqu-sx2 portal-quick-create-menu-e1" style={{ '--portal-quick-create-menu-background': alpha(color, '15'), '--portal-quick-create-menu-border': `1px solid ${alpha(color, '30')}` } as CSSProperties}>
                <Icon size={15} color={color} />
              </div>
              <div className="u-flex1-min0">
                <div className="u-text1-base-600">{label}</div>
                {hint && <div className="u-text3-xs">{hint}</div>}
              </div>
            </Pulsable>
          ))}
        </div>
      </div>
    </>
  )
}
