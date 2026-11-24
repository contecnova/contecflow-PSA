/**
 * PortalUI – diseño compartido del portal cliente, alineado con el backoffice.
 *
 * Provee:
 *   PortalShell        — sidebar agrupado + topbar + área principal
 *   PortalPageHeader   — cabecera de página con título / subtítulo / acciones / meta
 *   PortalCard         — tarjeta base (var(--surface-2))
 *   PortalKpi          — tarjeta KPI con valor / icono / trend
 *   PortalSection      — heading reutilizable
 *   PortalTabs         — pestañas
 *   PortalEmpty        — estado vacío
 *   PortalProgress     — barra de progreso
 *   PortalSpark        — sparkline mini
 *   PortalDonut        — donut SVG ligero
 *   PortalBars         — barras horizontales para distribuciones
 *   PortalAlert        — banner de aviso
 *
 * Inspirado en components/layout/Layout.jsx + components/ui/index.jsx pero
 * autocontenido para no acoplar el portal al AuthContext del operador.
 */
import type { CSSProperties, ReactNode, MouseEvent as ReactMouseEvent, KeyboardEvent as ReactKeyboardEvent, InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { X, Inbox } from 'lucide-react'
import { useLang } from './portalClientContext'
import Tabs from '../../components/ui/Tabs'
import { Button, EmptyState, Pulsable, Select, Input, Textarea, useDialogoEditable, IconButton } from '../../components/ui'
import { SinGuardarContext } from '../../components/ui/useCambiosSinGuardar'
import { tonoDe, UMBRALES_POR_DEFECTO } from '../../utils/umbrales'
import type { Umbrales } from '../../utils/umbrales'
import StatusBadge, { type StatusBadgeKind } from '../../components/ui/StatusBadge'
import './PortalUI.css'
import { px } from '../../utils/estilos'
import { type PortalIcon } from './PortalShell'
export { PORTAL_NAV_GROUPS } from './PortalShell'
export type { PortalIcon } from './PortalShell'
export type { PortalBranding } from './PortalShell'
export type { PortalBadges } from './PortalShell'
export { PortalShell } from './PortalShell'
export type { PortalDonutSegment } from './PortalUIGraficos'
export { PortalDonut } from './PortalUIGraficos'
export { PortalSpark } from './PortalUIGraficos'
export type { PortalBarItem } from './PortalUIGraficos'
export { PortalBars } from './PortalUIGraficos'
export { formatDuration } from './PortalUIGraficos'
export { MONEDA_PORTAL_POR_DEFECTO } from './PortalUIGraficos'
export { formatMoney } from './PortalUIGraficos'

// ── Page Header ──────────────────────────────────────────────────────────────
export interface PortalBreadcrumb {
  label: ReactNode
  onClick?: () => void
}

export interface PortalMetaItem {
  icon?: ReactNode
  value?: ReactNode
  label?: ReactNode
  color?: string
}

/** Quita las entradas condicionales (`cond && {...}`) de una lista de meta. */
export function metaItems(items: Array<PortalMetaItem | false | null | undefined | 0 | ''>): PortalMetaItem[] {
  return items.filter((m): m is PortalMetaItem => Boolean(m))
}

interface PortalPageHeaderProps {
  title: ReactNode
  subtitle?: ReactNode
  icon?: PortalIcon
  actions?: ReactNode
  meta?: PortalMetaItem[]
  breadcrumb?: PortalBreadcrumb[]
}

export function PortalPageHeader({ title, subtitle, icon: Icon, actions, meta, breadcrumb }: PortalPageHeaderProps) {
  return (
    <div className="portui-box-16">
      {breadcrumb && (
        <div className="portui-row-8">
          {breadcrumb.map((c, i) => (
            <span key={i} className="u-row-center-6">
              {i > 0 && <span className="portui-txt-2">›</span>}
              {c.onClick ? (
                <Pulsable className={`portui-box-26 ${i === breadcrumb.length - 1 ? 'portal-ui-m12' : 'portal-ui-m13'}`} onClick={c.onClick}>{c.label}</Pulsable>
              ) : (
                <span className={`portui-txt-8 ${i === breadcrumb.length - 1 ? 'portal-ui-m12' : 'portal-ui-m13'}`}>{c.label}</span>
              )}
            </span>
          ))}
        </div>
      )}
      <div className="portui-row-9">
        <div className="u-min0">
          <div className="u-row-center-12">
            {Icon && (
              <div className="portui-row-10"><Icon size={18} /></div>
            )}
            <h1 className="portui-box-17">{title}</h1>
          </div>
          {subtitle && (
            <p className={`portui-box-27 ${Icon ? 'portal-ui-m14' : 'portal-ui-m15'}`}>{subtitle}</p>
          )}
          {meta && meta.length > 0 && (
            <div className={`portui-row-25 ${Icon ? 'portal-ui-m14' : 'portal-ui-m15'}`}>
              {meta.map((m, i) => (
                <div key={i} className="portui-row-11">
                  {m.icon && <span className="portui-row-12">{m.icon}</span>}
                  <span className="portal-ui-e16" style={{ '--portal-ui-color': m.color || 'var(--text-2)' } as CSSProperties}>{m.value}</span>
                  {m.label && <span className="u-text3">{m.label}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
        {actions && (
          <div className="portui-row-13">
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Card ─────────────────────────────────────────────────────────────────────
interface PortalCardProps {
  children?: ReactNode
  className?: string
  style?: CSSProperties
  accent?: boolean
  padding?: CSSProperties['padding']
  onClick?: (e: ReactMouseEvent<HTMLDivElement> | ReactKeyboardEvent<HTMLDivElement>) => void
}

export function PortalCard({ children, className, style, accent, padding, onClick }: PortalCardProps) {
  const cls = `portal-card${accent ? ' portal-card--accent' : ''}${onClick ? ' portal-card--click' : ''}${className ? ` ${className}` : ''}`
  const st = padding === undefined ? style : ({ '--portal-card-pad': typeof padding === 'number' ? `${padding}px` : padding, ...style } as CSSProperties)
  if (onClick) {
    return (
      <div
        role="button" tabIndex={0}
        onClick={onClick}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(e) } }}
        className={cls}
        style={st}
      >{children}</div>
    )
  }
  return <div className={cls} style={st}>{children}</div>
}

// ── KPI ──────────────────────────────────────────────────────────────────────
interface PortalKpiProps {
  icon?: PortalIcon
  label: ReactNode
  value: ReactNode
  sub?: ReactNode
  tone?: string
  trend?: number | null
  footer?: ReactNode
  big?: boolean
}

/**
 * 16-11-2026 (pasada de diseño): misma forma que `KpiCard` (components/ui):
 * cifra grande sin monoespaciado, etiqueta en versalitas debajo, icono pequeño
 * y apagado. Se queda aquí solo porque el portal necesita `footer` (barra de
 * progreso), que KpiCard no tiene; `big` se acepta y se ignora.
 */
export function PortalKpi({ icon: Icon, label, value, sub, tone = 'default', trend, footer }: PortalKpiProps) {
  const toneColor = ({
    default: 'var(--text-1)',
    accent:  'var(--accent)',
    success: 'var(--success)',
    warning: 'var(--warning)',
    danger:  'var(--danger)',
    purple:  'var(--text-1)',
  } as Record<string, string>)[tone] || 'var(--text-1)'
  const trendColor = (trend ?? 0) > 0 ? 'var(--success)' : (trend ?? 0) < 0 ? 'var(--danger)' : 'var(--text-3)'
  const hayTrend = trend !== undefined && trend !== null
  return (
    <div className="ds-card ui-kpi portal-ui-kpi">
      <div className="ui-kpi__fila">
        <div className="ui-kpi__valor portal-ui-e16" style={{ '--portal-ui-color': toneColor } as CSSProperties}>{value}</div>
        {(Icon || hayTrend) && (
          <div className="ui-kpi__extra">
            {trend !== undefined && trend !== null && (
              <span className="portui-txt-9 portal-ui-e16" style={{ '--portal-ui-color': trendColor } as CSSProperties}>
                {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'} {Math.abs(trend)}%
              </span>
            )}
            {Icon && <span className="ui-kpi__icono" aria-hidden="true"><Icon size={16} /></span>}
          </div>
        )}
      </div>
      <div className="ds-eyebrow">{label}</div>
      {sub && <div className="ui-kpi__sub">{sub}</div>}
      {footer && <div className="portui-sp-2">{footer}</div>}
    </div>
  )
}

// ── Section heading ──────────────────────────────────────────────────────────
interface PortalSectionProps {
  title?: ReactNode
  hint?: ReactNode
  action?: ReactNode
  children?: ReactNode
  style?: CSSProperties
}

export function PortalSection({ title, hint, action, children, style = {} }: PortalSectionProps) {
  return (
    <div className="portal-ui-e32" style={style}>
      <div className="portui-row-15">
        <div>
          <div className="portui-txt-4">{title}</div>
          {hint && <div className="u-text3-xs-mt2">{hint}</div>}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

// ── Tabs ─────────────────────────────────────────────────────────────────────
export interface PortalTab {
  id: string
  label: ReactNode
  icon?: ReactNode
  badge?: number | null
}

interface PortalTabsProps {
  tabs: PortalTab[]
  value: string
  onChange: (id: string) => void
  ariaLabel?: string
}

/** 16-11-2026 (pasada de diseño): las pestañas del portal son las de la
 *  aplicación (`Tabs`, pastilla); antes eran un subrayado propio. */
export function PortalTabs({ tabs, value, onChange, ariaLabel }: PortalTabsProps) {
  return (
    <Tabs
      className="portui-tabs"
      ariaLabel={ariaLabel}
      active={value}
      onChange={onChange}
      items={tabs.map(tab => ({
        id: tab.id,
        label: tab.label,
        icon: tab.icon,
        count: tab.badge != null && tab.badge > 0 ? tab.badge : undefined,
      }))}
    />
  )
}

// ── Empty state ──────────────────────────────────────────────────────────────
interface PortalEmptyProps {
  icon?: PortalIcon
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
}

/** 16-11-2026 (pasada de diseño): el vacío de la aplicación (`EmptyState`). */
export function PortalEmpty({ icon: Icon, title, description, action }: PortalEmptyProps) {
  return (
    <EmptyState
      icon={Icon ? <Icon size={28} /> : <Inbox size={28} />}
      title={title}
      description={description}
      action={action}
    />
  )
}

// ── Progress ─────────────────────────────────────────────────────────────────
interface PortalProgressProps {
  value: number
  max?: number
  color?: string
  height?: number
  showLabel?: boolean
  /** Sin `color`: semáforo de presupuesto con estos umbrales (los de la empresa llegan con el panel). */
  umbrales?: Umbrales
}

export function PortalProgress({ value, max = 100, color, height = 6, showLabel = false, umbrales = UMBRALES_POR_DEFECTO }: PortalProgressProps) {
  const pct = max ? Math.min((value / max) * 100, 100) : 0
  // 19-11-2026: los umbrales de presupuesto de la empresa (antes 70/90 aquí).
  const c = color || `var(--${tonoDe('presupuesto', pct, umbrales) ?? 'success'})`
  return (
    <div>
      <div className="portui-box-30 portal-ui-e27" style={{ '--portal-ui-height': px(height) } as CSSProperties}>
        <div className="portui-box-31 portal-ui-e28" style={{ '--portal-ui-width': `${pct}%`, '--portal-ui-background': c } as CSSProperties} />
      </div>
      {showLabel && (
        <div className="portui-box-20">
          {Math.round(pct)}%
        </div>
      )}
    </div>
  )
}

// ── Badge ────────────────────────────────────────────────────────────────────
interface PortalBadgeProps {
  children?: ReactNode
  tone?: string
  icon?: ReactNode
}

export function PortalBadge({ children, tone = 'default', icon }: PortalBadgeProps) {
  // Mismo API de siempre (tone/icon); el pintado es el badge compartido.
  const kinds: Record<string, StatusBadgeKind> = {
    default: 'neutral', accent: 'accent', success: 'success', warning: 'warning',
    danger: 'danger', orange: 'orange', purple: 'purple',
  }
  return (
    <StatusBadge kind={kinds[tone] || 'neutral'}>
      {icon}
      {children}
    </StatusBadge>
  )
}

// ── Button ───────────────────────────────────────────────────────────────────
interface PortalButtonProps {
  children?: ReactNode
  onClick?: (e: ReactMouseEvent<HTMLButtonElement>) => void
  variant?: string
  size?: string
  disabled?: boolean
  loading?: boolean
  icon?: ReactNode
  type?: 'button' | 'submit' | 'reset'
  style?: CSSProperties
}

/** 16-11-2026 (pasada de diseño): el botón de la aplicación (`Button`), con
 *  la misma API de siempre. */
export function PortalButton({ children, onClick, variant = 'primary', size = 'md', disabled, loading, icon, type = 'button', style }: PortalButtonProps) {
  const v = (['primary', 'secondary', 'danger', 'ghost', 'subtle'].includes(variant) ? variant : 'primary') as 'primary' | 'secondary' | 'danger' | 'ghost' | 'subtle'
  const sz = (['xs', 'sm', 'md', 'lg'].includes(size) ? size : 'md') as 'xs' | 'sm' | 'md' | 'lg'
  return (
    <Button type={type} onClick={onClick} variant={v} size={sz} disabled={disabled} loading={loading} icon={icon} style={style}>
      {children}
    </Button>
  )
}

// ── Input / Select / Textarea ────────────────────────────────────────────────
interface PortalFieldProps {
  label?: ReactNode
  hint?: ReactNode
  required?: boolean
  /** Error de validación del servidor (o local) de este campo. */
  error?: string
  children?: ReactNode
}

export function PortalField({ label, hint, required, error, children }: PortalFieldProps) {
  return (
    <div className="portui-stack-3">
      {label && (
        <label className="portui-txt-5">
          {label}{required && <span className="u-danger"> *</span>}
        </label>
      )}
      {children}
      {error && <div className="u-field-error" role="alert">{error}</div>}
      {hint && <div className="u-text3-xs">{hint}</div>}
    </div>
  )
}

export function PortalInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Input {...props} onFocus={e => { e.target.style.borderColor = 'var(--accent-border-strong, color-mix(in srgb, var(--accent) 50%, transparent))'; e.target.style.boxShadow = '0 0 0 3px color-mix(in srgb, var(--accent) 8%, transparent)' }} onBlur={e => { e.target.style.borderColor = 'var(--surface-4)'; e.target.style.boxShadow = 'none' }} className={props.className} />
  )
}

/** Desplegable del portal: el `Select` del kit (suelto) con la clase `portal-campo`. Conserva la API de
 *  atributos de `<select>`; las opciones van como hijos (la opción vacía, si la hay, también). */
export function PortalSelect({ className, children, value, onChange, id, name, disabled, required, autoFocus, title, onBlur, onKeyDown,
  'aria-label': ariaLabel, 'aria-describedby': ariaDescribedBy }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <Select suelto placeholder={false} className={className ? `portal-campo ${className}` : 'portal-campo'}
      value={value as string | number | undefined} onChange={onChange} id={id} name={name} disabled={disabled} required={required}
      autoFocus={autoFocus} title={title} onBlur={onBlur} onKeyDown={onKeyDown} aria-label={ariaLabel} aria-describedby={ariaDescribedBy}>
      {children}
    </Select>
  )
}

export function PortalTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <Textarea {...props} className={props.className} inputClassName="portal-campo--vertical" />
  )
}

// ── Modal ────────────────────────────────────────────────────────────────────
interface PortalModalProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  subtitle?: ReactNode
  width?: CSSProperties['maxWidth']
  children?: ReactNode
  footer?: ReactNode
  /** false en modales de solo lectura: no preguntan por cambios sin guardar. */
  avisarSinGuardar?: boolean
  /** Controlado por la pantalla: manda sobre la detección automática. */
  cambiosSinGuardar?: boolean
}

/**
 * Modal del portal. 23-11-2026: mismo estándar que el `Modal` del kit
 * (`useDialogoEditable`): trampa de foco, Esc, devolución del foco y, si el
 * cliente ha tocado algo, clic fuera / Esc / X preguntan antes de cerrar
 * (textos `sin_guardar.*` del portal, 8 idiomas). Cerrar tras guardar
 * (`onClose` desde la pantalla o `open=false`) no pregunta.
 */
export function PortalModal({ open, onClose, title, subtitle, width = 560, children, footer, avisarSinGuardar = true, cambiosSinGuardar }: PortalModalProps) {
  const traducir = useLang()
  const { ref, pedirCierre, sinGuardar } = useDialogoEditable<HTMLDivElement>(open, onClose, { avisarSinGuardar, cambiosSinGuardar })
  if (!open) return null
  return (
    <div role="presentation" onMouseDown={e => { e.preventDefault(); pedirCierre() }} className="portalui-sx5">
      <SinGuardarContext.Provider value={sinGuardar}>
      <div ref={ref} className="portui-box-32 portalui-sx6 portal-ui-e29" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined} tabIndex={-1} onMouseDown={e => e.stopPropagation()} style={{ '--portal-ui-max-width': px(width) } as CSSProperties}>
        <div className="portui-row-18">
          <div>
            <h2 className="portui-box-22">{title}</h2>
            {subtitle && <p className="portui-box-23">{subtitle}</p>}
          </div>
          <IconButton variante="caja" onClick={pedirCierre} ariaLabel={traducir('common.close')}><X size={14} /></IconButton>
        </div>
        {children}
        {footer && (
          <div className="portui-row-20">
            {footer}
          </div>
        )}
      </div>
      </SinGuardarContext.Provider>
    </div>
  )
}

// ── Banner ───────────────────────────────────────────────────────────────────
interface PortalBannerProps {
  tone?: string
  icon?: ReactNode
  title?: ReactNode
  body?: ReactNode
  action?: ReactNode
}

export function PortalBanner({ tone = 'info', icon, title, body, action }: PortalBannerProps) {
  const tones: Record<string, { bg: string; bd: string; fg: string }> = {
    info:    { bg: 'var(--accent-muted)', bd: 'var(--accent-border, color-mix(in srgb, var(--accent) 25%, transparent))', fg: 'var(--accent)' },
    warning: { bg: 'var(--warning-bg)', bd: 'var(--warning-border)', fg: 'var(--warning)' },
    danger:  { bg: 'var(--danger-bg)',  bd: 'var(--danger-border)',  fg: 'var(--danger)' },
    success: { bg: 'var(--success-bg)', bd: 'var(--success-border)', fg: 'var(--success)' },
  }
  const c = tones[tone] || tones.info
  return (
    <div className="portui-row-28 portalui-sx7 portal-ui-e30" style={{ '--portal-ui-background': c.bg, '--portal-ui-border': `1px solid ${c.bd}` } as CSSProperties}>
      {icon && <div className="portui-row-29 portal-ui-e16" style={{ '--portal-ui-color': c.fg } as CSSProperties}>{icon}</div>}
      <div className="u-flex1-min0">
        <div className="portui-txt-10 portal-ui-e16" style={{ '--portal-ui-color': c.fg } as CSSProperties}>{title}</div>
        {body && <div className="u-text2-sm-mt2">{body}</div>}
      </div>
      {action}
    </div>
  )
}

