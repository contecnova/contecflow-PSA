// Graficos pequeños y formateadores del portal de cliente (donut, spark, barras, duracion, moneda). 23-11-2026: troceado de PortalUI sin cambio de comportamiento.
import type { CSSProperties, ReactNode } from 'react'
import { useLang } from './portalClientContext'
import { formatearMoneda } from '../../utils/helpers'
import { px } from '../../utils/estilos'

// ── Donut chart (lightweight SVG) ────────────────────────────────────────────
export interface PortalDonutSegment {
  value?: number | null
  color?: string
}

interface PortalDonutProps {
  size?: number
  stroke?: number
  segments?: PortalDonutSegment[]
  centerTop?: ReactNode
  centerBottom?: ReactNode
}

export function PortalDonut({ size = 110, stroke = 12, segments = [], centerTop, centerBottom }: PortalDonutProps) {
  const traducir = useLang()
  const radius = size / 2 - stroke / 2
  const circ = 2 * Math.PI * radius
  const total = segments.reduce((s, x) => s + Math.max(0, x.value || 0), 0)
  let offset = 0
  return (
    <div className="portui-box-33 portal-ui-e31" style={{ '--portal-ui-width': px(size), '--portal-ui-height': px(size) } as CSSProperties}>
      <svg width={size} height={size} role="img" aria-label={traducir('portalui.distribucion')}>
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke="var(--surface-4)" strokeWidth={stroke} />
        {total > 0 && segments.map((seg, i) => {
          const len = (Math.max(0, seg.value || 0) / total) * circ
          const dasharray = `${len} ${circ - len}`
          const dashoffset = -offset
          offset += len
          return (
            <circle key={i} cx={size/2} cy={size/2} r={radius} fill="none"
              stroke={seg.color} strokeWidth={stroke}
              strokeDasharray={dasharray} strokeDashoffset={dashoffset}
              transform={`rotate(-90 ${size/2} ${size/2})`}
              strokeLinecap="butt" />
          )
        })}
      </svg>
      <div className="portui-stack-4">
        {centerTop && <div className="portui-txt-6">{centerTop}</div>}
        {centerBottom && <div className="portui-txt-1">{centerBottom}</div>}
      </div>
    </div>
  )
}

// ── Sparkline ────────────────────────────────────────────────────────────────
interface PortalSparkProps {
  values?: number[]
  width?: number
  height?: number
  color?: string
}

export function PortalSpark({ values = [], width = 110, height = 32, color = 'var(--accent)' }: PortalSparkProps) {
  const traducir = useLang()
  if (!values.length) return null
  const min = Math.min(...values, 0)
  const max = Math.max(...values, 1)
  const span = max - min || 1
  const stepX = values.length > 1 ? width / (values.length - 1) : width
  const path = values
    .map((v: number, i: number) => {
      const x = i * stepX
      const y = height - ((v - min) / span) * height
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
  const areaPath = `${path} L ${(stepX * (values.length - 1)).toFixed(1)} ${height} L 0 ${height} Z`
  return (
    <svg width={width} height={height} role="img" aria-label={traducir('portalui.tendencia')}>
      <path d={areaPath} fill={color} opacity="0.15" />
      <path d={path} stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Horizontal bars (distribution) ──────────────────────────────────────────
export interface PortalBarItem {
  label: ReactNode
  value?: number | null
  color?: string
  suffix?: string
}

export function PortalBars({ items = [] }: { items?: PortalBarItem[] }) {
  const max = Math.max(1, ...items.map(i => i.value || 0))
  return (
    <div className="u-stack-10">
      {items.map((it, idx) => (
        <div key={idx}>
          <div className="portui-row-21">
            <span className="portui-txt-7">{it.label}</span>
            <span className="portui-txt-11 portal-ui-e16" style={{ '--portal-ui-color': it.color || 'var(--text-1)' } as CSSProperties}>{it.value}{it.suffix || ''}</span>
          </div>
          <div className="portui-box-24">
            <div className="portui-box-31 portal-ui-e28" style={{ '--portal-ui-width': `${((it.value || 0) / max) * 100}%`, '--portal-ui-background': it.color || 'var(--accent)' } as CSSProperties} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Helpers exportados ───────────────────────────────────────────────────────

export function formatDuration(minutes: number | string | null | undefined) {
  if (minutes == null || Number.isNaN(Number(minutes))) return '—'
  const m = Math.round(Number(minutes))
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r ? `${h}h ${r}min` : `${h}h`
}

/**
 * Moneda por defecto del portal cuando el dato no trae la suya. El portal no
 * puede leer la de la empresa: /settings/org-defaults exige sesion de empleado
 * (get_current_user) y el cliente entra con token de portal. Las facturas y
 * pedidos traen `currency`; esto solo cubre el caso de no tener ninguno.
 */
export const MONEDA_PORTAL_POR_DEFECTO = 'EUR'

export function formatMoney(value: number | string | null | undefined, currency: string | null | undefined = MONEDA_PORTAL_POR_DEFECTO) {
  return formatearMoneda(Number(value || 0), currency || MONEDA_PORTAL_POR_DEFECTO)
}
