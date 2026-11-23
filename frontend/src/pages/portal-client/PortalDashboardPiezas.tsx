// Piezas pequeñas del panel del portal de cliente (fila de dato, bloque de metrica, enlace rapido). 23-11-2026: troceado de PortalDashboard sin cambio de comportamiento.
import { type CSSProperties, type ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { type PortalIcon } from './PortalUI'
import { Pulsable } from '../../components/ui'

// ── Helpers locales ──────────────────────────────────────────────────────────
export function DataRow({ label, value, tone = 'default', hint }: { label: ReactNode; value: ReactNode; tone?: string; hint?: ReactNode }) {
  const color = tone === 'success' ? 'var(--success)'
    : tone === 'warning' ? 'var(--warning)'
    : tone === 'danger'  ? 'var(--danger)'
    : tone === 'accent'  ? 'var(--accent)'
    : 'var(--text-1)'
  return (
    <div className="portdash-row-9">
      <div>
        <span className="u-text2-sm">{label}</span>
        {hint && <div className="u-text3-xs">{hint}</div>}
      </div>
      <span className="portdash-txt-4 portal-dashboard-e11" style={{ '--portal-dashboard-color': color } as CSSProperties}>{value}</span>
    </div>
  )
}

export function MetricBlock({ icon: Icon, label, value, tone }: { icon: PortalIcon; label: ReactNode; value: ReactNode; tone?: string }) {
  const color = tone === 'success' ? 'var(--success)' : tone === 'accent' ? 'var(--accent)' : 'var(--text-1)'
  return (
    <div className="portdash-box-9">
      <div className="portdash-row-10">
        <Icon size={12} /> {label}
      </div>
      <div className="portdash-txt-5 portal-dashboard-e11" style={{ '--portal-dashboard-color': color } as CSSProperties}>{value}</div>
    </div>
  )
}

export function QuickLink({ icon: Icon, label, hint, onClick }: { icon: PortalIcon; label: ReactNode; hint?: ReactNode; onClick?: () => void }) {
  return (
    <Pulsable onClick={onClick} className="portdash-row-11">
      <div className="portdash-row-12"><Icon size={16} /></div>
      <div className="u-flex1-min0">
        <div className="u-sm-700">{label}</div>
        <div className="u-text3-xs">{hint}</div>
      </div>
      <ArrowRight size={14} className="portalda-sx2" aria-hidden="true" />
    </Pulsable>
  )
}
