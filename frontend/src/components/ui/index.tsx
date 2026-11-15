import { CHART } from '../../constants/theme'
import { useDialogo } from './useDialogo'
import React, { type CSSProperties } from 'react'
import { X } from 'lucide-react'
import { DATA_TABLE_PAGE_SIZE } from '../../constants/pagination'
import './index.css'
import { useTextoUi } from './useTextoUi'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { px } from '../../utils/estilos'

export { default as Confirm } from './Confirm'
export { default as IconButton } from './IconButton'
export { default as Tabs, TabPanel } from './Tabs'
export { default as Toolbar } from './Toolbar'
export { default as FormField } from './FormField'
// Design system v2 primitivos
export { default as Page } from './Page'
export { default as Section } from './Section'
export { default as StatusBadge } from './StatusBadge'

export {
  ClientSelect, UserSelect, ProjectSelect,
  SprintSelect, EpicSelect, ContractSelect,
  MilestoneSelect, TaskSelect,
  AssetSelect, LicenseSelect, VendorSelect,
  TicketSelect, ProblemSelect, SubcontractorSelect,
} from './EntitySelect'

export { useSort, SortableTH, ariaSort, ViewToggle, FilterSelect, SearchInput, ActiveFilters } from './TableControls'

// ── Badge ─────────────────────────────────────────────────────────────────────


// ─────────────────────────────────────────────────────────────────────────────
// Tipos del kit
//
// Auditoría 2026-09 (modo estricto): este fichero es el kit de componentes que
// usa toda la aplicación y **no declaraba ni una sola prop**. La mitad de los
// componentes llevaban `: any` en la desestructuración y la otra mitad ni eso,
// así que cada sitio que los usa venía pasando lo que quería sin que nadie lo
// comprobara. Tiparlos aquí es lo que más rinde de la pasada: un error de props
// en el kit se multiplica por los sitios que lo llaman.
//
// Dos decisiones conscientes:
//
//  · `Table` y `DataTable` son **genéricas sobre la fila**. Es lo que son: la
//    tabla no sabe qué hay en la fila, la columna sí. Con la fila fijada a
//    `Record<string, unknown>` ninguna `interface` del dominio encajaría —las
//    interfaces de TypeScript no tienen índice implícito— y todas las llamadas
//    romperían por un detalle del sistema de tipos, no por un fallo real.
//  · `render` recibe el valor como `unknown`. Sale de `fila[col.key]`, que es un
//    acceso dinámico de verdad: prometer un tipo ahí sería inventarlo.
// ─────────────────────────────────────────────────────────────────────────────

/** La definición de una columna de `Table` / `DataTable`. */
export interface ColumnaDeTabla<T = unknown> {
  /** La clave con la que se lee el valor en la fila. */
  key: string
  label: React.ReactNode
  /** `false` desactiva la ordenación por esta columna (`DataTable`). */
  sortable?: boolean
  style?: React.CSSProperties
  /** Pinta la celda. Sin él se muestra el valor crudo, o un guion si no hay. */
  render?: (valor: never, fila: T) => React.ReactNode
}

/** El contenido de una celda: lo que diga `render`, o el valor crudo, o guion.
 *
 *  Vive fuera de los dos componentes porque los dos hacían exactamente esto, y
 *  el acceso dinámico `fila[col.key]` necesita **un** sitio donde justificarse:
 *  la tabla no conoce la forma de la fila —es genérica— y la columna sí, así
 *  que aquí es donde el `Record` es la verdad y no una tirita.
 */
function celda<T>(col: ColumnaDeTabla<T>, fila: T): React.ReactNode {
  const valor = (fila as Record<string, unknown>)[col.key]
  if (col.render) return (col.render as unknown as (v: unknown, f: T) => React.ReactNode)(valor, fila)
  return (valor ?? '—') as React.ReactNode
}

/** Convert snake_case to Title Case as fallback for unknown values. */
function humanize(str?: string | null): string {
  if (!str) return ''
  return String(str).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

interface BadgeProps {
  /** El valor crudo (p. ej. `p1_critical`); elige color y, si no hay
   *  `display`, tambien el texto. */
  label?: string | null
  /** Texto a mostrar cuando el valor crudo no se quiere ensenar tal cual. */
  display?: React.ReactNode
  /** Sin uso: se conserva porque hay llamadas que lo pasan. */
  _color?: string
}

export function Badge({ label, display, _color }: BadgeProps) {
  const t = useTextoUi()
  const presets: Record<string, { bg: string; text: string; border: string }> = {
    low:         { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    medium:      { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    high:        { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    critical:    { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    p1_critical: { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    p2_high:     { bg: 'var(--orange-bg)',   text: 'var(--orange)',   border: 'var(--orange-border)' },
    p3_medium:   { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    p4_low:      { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
    active:      { bg: 'var(--accent-muted)', text: 'var(--accent)', border: 'color-mix(in srgb, var(--accent) 25%, transparent)' },
    planning:    { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
    paused:      { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    closed:      { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    done:        { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    accepted:    { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    approved:    { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    cancelled:   { bg: 'var(--surface-3)',   text: 'var(--text-3)',   border: 'var(--surface-4)' },
    in_progress: { bg: 'var(--accent-muted)', text: 'var(--accent)', border: 'color-mix(in srgb, var(--accent) 25%, transparent)' },
    in_review:   { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    blocked:     { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    rejected:    { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    materialized:{ bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    review:      { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    todo:        { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
    backlog:     { bg: 'var(--surface-3)',   text: 'var(--text-3)',   border: 'var(--surface-4)' },
    draft:       { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
    submitted:   { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    pending:     { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    resolved:    { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    normal:      { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
  }
  const c = (label && presets[label]) || presets.normal
  const texto = etiquetaCodigo(t, 'estado', label, humanize(label))
  const shown: React.ReactNode = display || texto
  return (
    <span className="uiinde-box-13 index-sx1 ui-index-e1"
      style={{ '--ui-index-background': c.bg, '--ui-index-color': c.text, '--ui-index-border': `1px solid ${c.border}` } as CSSProperties}
      aria-label={texto}
    >
      {shown}
    </span>
  )
}

// ── LoadBar ───────────────────────────────────────────────────────────────────
interface LoadBarProps {
  value: number
  max?: number
  height?: number
  /** Etiqueta accesible; sin ella se anuncia el porcentaje. */
  label?: string
}

export function LoadBar({ value, max = 100, height = 5, label }: LoadBarProps) {
  const pct   = Math.min((value / max) * 100, 100)
  const color = value > max ? 'var(--danger)' : value / max > 0.85 ? 'var(--warning)' : 'var(--success)'
  return (
    <div className="uiinde-box-14 ui-index-e2" role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={max}
      aria-label={label || `${Math.round(pct)}%`}
      style={{ '--ui-index-height': px(height) } as CSSProperties}>
      <div className="uiinde-box-15 ui-index-e3" style={{ '--ui-index-width': `${pct}%`, '--ui-index-background': color } as CSSProperties} />
    </div>
  )
}

// ── Avatar ────────────────────────────────────────────────────────────────────
interface AvatarProps {
  name?: string
  size?: number
  /** Si hay foto se usa; si no, se pintan las iniciales. */
  url?: string | null
}

export function Avatar({ name = '', size = 34, url }: AvatarProps) {
  const initials = name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()
  const palettes = [
    ['var(--accent)', 'rgba(26,58,110,0.8)'], ['var(--success)', 'rgba(15,70,50,0.8)'], ['var(--warning)', 'rgba(107,62,0,0.8)'],
    ['var(--danger)', 'rgba(92,26,26,0.9)'], ['var(--purple)', 'rgba(59,31,110,0.9)'], [CHART.sky, 'var(--surface-5)'],
  ]
  const [from, to] = palettes[name.charCodeAt(0) % palettes.length]
  return url ? (
    <img className="uiinde-box-16 ui-index-e4" src={url} alt={name} loading="lazy" decoding="async" style={{ '--ui-index-width': px(size), '--ui-index-height': px(size) } as CSSProperties} />
  ) : (
    <div className="uiinde-row-6 ui-index-e5"
      role="img"
      aria-label={name || 'Usuario'}
      style={{ '--ui-index-width': px(size), '--ui-index-height': px(size), '--ui-index-font-size': px(Math.round(size * 0.36)), '--ui-index-background': `linear-gradient(145deg, ${from}, ${to})` } as CSSProperties}>
      {initials || '?'}
    </div>
  )
}

// ── Card ──────────────────────────────────────────────────────────────────────
interface CardProps {
  children?: React.ReactNode
  /** Auditoria 2026-09: se pasaba desde fuera y `Card` no lo reenviaba, asi que
   *  la clase no llegaba al DOM y el estilo que dependia de ella no existia. */
  className?: string
  style?: React.CSSProperties
  /** Resalta el borde y la sombra. */
  accent?: boolean
  /** Si se pasa, la tarjeta pasa a ser pulsable **y navegable con teclado**. */
  onClick?: (e: React.MouseEvent | React.KeyboardEvent) => void
}

export function Card({ children, className, style, accent = false, onClick = undefined }: CardProps) {
  const cls = `ui-card${accent ? ' ui-card--accent' : ''}${onClick ? ' ui-card--click' : ''}${className ? ` ${className}` : ''}`
  if (onClick) {
    const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        onClick(e)
      }
    }
    return (
      <div className={cls} onClick={onClick} onKeyDown={handleKeyDown} role="button" tabIndex={0} style={style}>
        {children}
      </div>
    )
  }
  return <div className={cls} style={style}>{children}</div>
}

// ── KPI Card ──────────────────────────────────────────────────────────────────
interface KpiCardProps {
  icon?: React.ReactNode
  label?: React.ReactNode
  value?: React.ReactNode
  sub?: React.ReactNode
  accent?: boolean
  danger?: boolean
  warning?: boolean
  /** Variacion en porcentaje. `undefined` esconde el indicador; 0 lo muestra
   *  en neutro, que no es lo mismo que no tener dato. */
  trend?: number
}

export function KpiCard({ icon, label, value, sub, accent, danger, warning, trend }: KpiCardProps) {
  const valueColor = danger ? 'var(--danger)' : warning ? 'var(--warning)' : accent ? 'var(--accent)' : 'var(--text-1)'
  const trendColor = (trend ?? 0) > 0 ? 'var(--success)' : (trend ?? 0) < 0 ? 'var(--danger)' : 'var(--text-3)'
  return (
    <Card accent={accent} className="index-sx2">
      <div className="uiinde-row-1">
        <div className="uiinde-txt-1">{icon}</div>
        {trend !== undefined && (
          <span className="uiinde-txt-6 ui-index-e6" style={{ '--ui-index-color': trendColor } as CSSProperties}>
            {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'} {Math.abs(trend)}%
          </span>
        )}
      </div>
      <div className="uiinde-box-17 ui-index-e6" style={{ '--ui-index-color': valueColor } as CSSProperties}>
        {value}
      </div>
      <div className="uiinde-txt-2">{label}</div>
      {sub && <div className="uiinde-box-1">{sub}</div>}
    </Card>
  )
}

// ── Button ────────────────────────────────────────────────────────────────────
interface ButtonProps {
  children?: React.ReactNode
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'subtle'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  disabled?: boolean
  /** Deshabilita ademas de mostrar el spinner: un boton cargando no se pulsa. */
  loading?: boolean
  icon?: React.ReactNode
  className?: string
  style?: React.CSSProperties
  type?: 'button' | 'submit' | 'reset'
  title?: string
}

export function Button({ children, onClick, variant = 'primary', size = 'md', disabled = false, loading = false, icon = null, className, style, type = 'button', title = undefined }: ButtonProps) {
  const v = ['primary', 'secondary', 'danger', 'ghost', 'subtle'].includes(variant) ? variant : 'primary'
  const sz = ['xs', 'sm', 'md', 'lg'].includes(size) ? size : 'md'
  const isDisabled = disabled || loading

  return (
    <button
      type={type}
      title={title}
      onClick={isDisabled ? undefined : onClick}
      aria-disabled={isDisabled || undefined}
      aria-busy={loading || undefined}
      disabled={isDisabled}
      className={`ui-btn ui-btn--${v} ui-btn--${sz}${className ? ` ${className}` : ''}`}
      style={style}
    >
      {loading ? (
        <span className="uiinde-box-2" />
      ) : icon ? <span className="uiinde-txt-3">{icon}</span> : null}
      {children}
    </button>
  )
}

// ── Input ─────────────────────────────────────────────────────────────────────
// Auditoria 2026-11 (#10): la <label> no estaba asociada al control (sin
// htmlFor/id), asi que el lector de pantalla anunciaba "campo de edicion" sin
// nombre y pulsar la etiqueta no enfocaba. Ahora cada campo genera su id con
// useId (o usa el que se pase) y enlaza ayuda y error con aria-describedby.
interface InputProps {
  label?: React.ReactNode
  value?: string | number
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void
  placeholder?: string
  type?: string
  /** Solo pinta el asterisco: la validacion es de quien lo usa. */
  required?: boolean
  style?: React.CSSProperties
  hint?: React.ReactNode
  /** Mensaje de error: se pinta bajo el campo y marca aria-invalid. */
  error?: React.ReactNode
  /** Id del control; si no se pasa se genera uno. */
  id?: string
  /** Nombre accesible cuando no hay `label` visible. */
  'aria-label'?: string
}

/** Ids del control y de sus textos de apoyo (ayuda, error). */
function useIdsDeCampo(id: string | undefined, hint: unknown, error: unknown) {
  const generado = React.useId()
  const base = id || `campo-${generado}`
  const idHint = hint ? `${base}-ayuda` : undefined
  const idError = error ? `${base}-error` : undefined
  const describedBy = [idHint, idError].filter(Boolean).join(' ') || undefined
  return { base, idHint, idError, describedBy }
}


export function Input({ label, value, onChange, placeholder, type = 'text', required, style = {}, hint, error, id, 'aria-label': ariaLabel }: InputProps) {
  const { base, idHint, idError, describedBy } = useIdsDeCampo(id, hint, error)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
      {label && (
        <label htmlFor={base} id={`${base}-etiqueta`} className="uiinde-estiloetiqueta">
          {label}{required && <span className="u-danger" aria-hidden="true"> *</span>}
        </label>
      )}
      <input className="uiinde-box-18 index-sx3 ui-index-e7"
        id={base}
        aria-labelledby={label ? `${base}-etiqueta` : undefined}
        aria-label={label ? undefined : ariaLabel}
        type={type} value={value} onChange={onChange} placeholder={placeholder}
        required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        style={{ '--ui-index-border': `1px solid ${error ? 'var(--danger-border)' : 'var(--surface-4)'}` } as CSSProperties}
        onFocus={e => {
          e.target.style.borderColor = 'color-mix(in srgb, var(--accent) 50%, transparent)'
          e.target.style.boxShadow = '0 0 0 3px color-mix(in srgb, var(--accent) 8%, transparent)'
        }}
        onBlur={e => {
          e.target.style.borderColor = error ? 'var(--danger-border)' : 'var(--surface-4)'
          e.target.style.boxShadow = 'none'
        }}
      />
      {hint && <div id={idHint} className="u-text3-xs">{hint}</div>}
      {error && <div id={idError} role="alert" className="u-field-error">{error}</div>}
    </div>
  )
}

// ── Select ────────────────────────────────────────────────────────────────────
interface SelectProps {
  label?: React.ReactNode
  value?: string
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void
  options?: Array<{ value: string; label: string }>
  style?: React.CSSProperties
  hint?: React.ReactNode
  error?: React.ReactNode
  id?: string
}

export function Select({ label, value, onChange, options = [], style = {}, hint, error, id }: SelectProps) {
  const t = useTextoUi()
  const { base, idHint, idError, describedBy } = useIdsDeCampo(id, hint, error)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
      {label && (
        <label htmlFor={base} className="uiinde-estiloetiqueta">
          {label}
        </label>
      )}
      <select className={`uiinde-box-19 index-sx3 ui-index-e7 ${value ? 'ui-index-m8' : 'ui-index-m9'}`}
        id={base}
        value={value} onChange={onChange}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        style={{ '--ui-index-border': `1px solid ${error ? 'var(--danger-border)' : 'var(--surface-4)'}` } as CSSProperties}
      >
        <option value="">{t('invoices.select')}</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {hint && <div id={idHint} className="u-text3-xs">{hint}</div>}
      {error && <div id={idError} role="alert" className="u-field-error">{error}</div>}
    </div>
  )
}

// ── Spinner ───────────────────────────────────────────────────────────────────
interface SpinnerProps {
  size?: number
  color?: string
  label?: string
}

export function Spinner({ size = 22, color = 'var(--accent)', label }: SpinnerProps) {
  const t = useTextoUi()
  return (
    <div className="uiinde-box-20 ui-index-e10" role="status" aria-label={label ?? t('uikit.cargando')} style={{ '--ui-index-width': px(size), '--ui-index-height': px(size), '--ui-index-border-top-color': color } as CSSProperties} />
  )
}

/** Spinner centrado en su contenedor (celda de carga de DataTable). Como
 *  componente propio, la regla control-has-associated-label ve su nombre
 *  accesible (el role="status" del Spinner) sin tener que bajar niveles. */
function SpinnerCentrado() {
  return <div className="uiinde-row-2"><Spinner /></div>
}

// ── Empty state ───────────────────────────────────────────────────────────────
// ── Predefined SVG icons for empty states ────────────────────────────────────
const EMPTY_ICONS = {
  folder: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V7z"/>
    </svg>
  ),
  tasks: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="14" rx="2"/>
      <path d="M8 10h8M8 14h5"/>
    </svg>
  ),
  search: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>
    </svg>
  ),
  users: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="7" r="3"/><path d="M3 20c0-4 3-6 6-6s6 2 6 6"/>
      <circle cx="17" cy="8" r="2"/><path d="M21 20c0-3-1.5-5-4-5"/>
    </svg>
  ),
  docs: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"/><polyline points="14 2 14 8 20 8"/>
      <line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/>
    </svg>
  ),
  chart: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
    </svg>
  ),
  inbox: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>
      <path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/>
    </svg>
  ),
}

interface EmptyStateProps {
  /** Clave de `EMPTY_ICONS`, o un emoji/texto suelto (compatibilidad). */
  icon?: React.ReactNode
  /** Un SVG explicito, que gana sobre `icon`. */
  svgIcon?: React.ReactNode
  title?: React.ReactNode
  description?: React.ReactNode
  /** Un nodo de accion completo; gana sobre el par `ctaLabel` + `onCta`. */
  action?: React.ReactNode
  ctaLabel?: React.ReactNode
  onCta?: () => void
}

export function EmptyState({ icon = null, svgIcon = null, title = '', description = '', action = null, ctaLabel = '', onCta = undefined }: EmptyStateProps) {
  // svgIcon: explicit SVG node
  // icon: named key from EMPTY_ICONS dict, OR emoji/text string (backward-compat)
  const resolvedIcon = svgIcon
    ? svgIcon
    : ((icon ? EMPTY_ICONS[icon as keyof typeof EMPTY_ICONS] : undefined) || (
        icon
          ? <span className="uiinde-txt-4">{icon}</span>
          : <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01" strokeLinecap="round"/>
            </svg>
      ))

  return (
    <div className="empty-state">
      <div className="empty-state-icon">{resolvedIcon}</div>
      <div className="empty-state-title">{title}</div>
      {description && <div className="empty-state-desc">{description}</div>}
      {(action || (ctaLabel && onCta)) && (
        <div className="uiinde-sp-1">
          {action || (
            <button className="btn-primary uiinde-box-3" onClick={onCta}
              >
              {ctaLabel}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Modal ─────────────────────────────────────────────────────────────────────
/** Los anchos con nombre. `size` gana sobre el defecto y pierde contra un
 *  `width` explicito, que es el orden que uno espera: lo mas concreto manda. */
const ANCHOS_DE_MODAL: Record<'sm' | 'md' | 'lg' | 'xl', number> = {
  sm: 400, md: 520, lg: 760, xl: 1040,
}

interface ModalProps {
  open?: boolean
  onClose: () => void
  title?: React.ReactNode
  children?: React.ReactNode
  /** Ancho maximo en pixeles, o cualquier medida CSS. Gana sobre `size`. */
  width?: number | string
  /** Ancho con nombre. Auditoria 2026-09: ocho llamadas ya lo pasaban y el
   *  componente **no tenia esta prop**, asi que React la descartaba sin avisar
   *  y esos ocho modales salian con el ancho por defecto. Lo destapo tipar las
   *  props del kit; antes no habia nada que pudiera destaparlo. */
  size?: 'sm' | 'md' | 'lg' | 'xl'
  subtitle?: React.ReactNode
}

export function Modal({ open, onClose, title, children, width, size, subtitle }: ModalProps) {
  const t = useTextoUi()
  const anchoFinal = width ?? ANCHOS_DE_MODAL[size ?? 'md']
  // Trampa de foco, Esc y devolucion del foco: compartido con los dialogos propios.
  const dialogRef = useDialogo<HTMLDivElement>(open, onClose)

  if (!open) return null
  return (
    <div
      onMouseDown={onClose}
      role="presentation" className="index-sx4"
    >
      <div className="uiinde-box-21 index-sx5 ui-index-e11"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        onMouseDown={e => e.stopPropagation()}
        style={{ '--ui-index-max-width': px(anchoFinal) } as CSSProperties}
      >
        <div className="uiinde-row-3">
          <div>
            <h2 className="uiinde-txt-5">{title}</h2>
            {subtitle && <p className="uiinde-box-4">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('uikit.cerrar')}
            className="uiinde-row-4"
          ><X size={14} aria-hidden="true" /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── DataTable ─────────────────────────────────────────────────────────────────
interface DataTableProps<T> {
  columns: Array<ColumnaDeTabla<T>>
  data?: T[]
  loading?: boolean
  emptyIcon?: React.ReactNode
  emptyTitle?: React.ReactNode
  pageSize?: number
}

export function DataTable<T>({ columns, data = [], loading, emptyIcon = '○', emptyTitle, pageSize = DATA_TABLE_PAGE_SIZE }: DataTableProps<T>) {
  const t = useTextoUi()
  const [sort, setSort] = React.useState<{ col: string | null; dir: 'asc' | 'desc' }>({ col: null, dir: 'asc' })
  const [page, setPage] = React.useState(0)
  const [filter, setFilter] = React.useState('')

  const filtered = filter
    ? data.filter(row => Object.values(row as Record<string, unknown>).some(v => String(v || '').toLowerCase().includes(filter.toLowerCase())))
    : data
  const sorted = sort.col
    ? [...filtered].sort((a, b) => {
        const sortCol = sort.col as string
        const cmp = String((a as Record<string, unknown>)[sortCol] || '').localeCompare(String((b as Record<string, unknown>)[sortCol] || ''), undefined, { numeric: true })
        return sort.dir === 'asc' ? cmp : -cmp
      })
    : filtered
  const pages    = Math.max(1, Math.ceil(sorted.length / pageSize))
  const pageData = sorted.slice(page * pageSize, (page + 1) * pageSize)
  const toggleSort = (col: string) => setSort(s => s.col === col ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: 'asc' })


  return (
    <div>
      {data.length > pageSize && (
        <div className="u-mb-12">
          <input aria-label={t('uikit.filtrar')} value={filter} onChange={e => { setFilter(e.target.value); setPage(0) }}
            placeholder={t('uikit.filtrar')} className="uiinde-box-5" />
        </div>
      )}
      <div className="u-scroll-x">
        <table className="uiinde-box-6">
          <thead>
            <tr className="u-border-b">
              {columns.map(col => (
                <th className={`uiinde-box-22 ${sort.col === col.key ? 'ui-index-m12' : 'ui-index-m13'} ${col.sortable !== false ? 'ui-index-m14' : 'ui-index-m15'}`} key={col.key} onClick={() => col.sortable !== false && toggleSort(col.key)}>
                  {col.label}
                  {sort.col === col.key && <span className="uiinde-box-7">{sort.dir === 'asc' ? '↑' : '↓'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length} className="uiinde-box-8">
                <SpinnerCentrado />
              </td></tr>
            ) : pageData.length === 0 ? (
              <tr><td colSpan={columns.length}>
                <EmptyState icon={emptyIcon} title={emptyTitle ?? t('uikit.sin_datos')} />
              </td></tr>
            ) : pageData.map((row, i) => (
              <tr key={(row as { id?: string }).id || i}
                className="uiinde-box-9"
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                {columns.map(col => (
                  <td key={col.key} style={{ padding: '11px 14px', color: 'var(--text-1)', ...col.style }}>
                    {celda(col, row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="uiinde-row-5">
          <span className="u-text3-xs">{t('uikit.n_registros', { n: sorted.length })}</span>
          <button type="button" aria-label={t('pagination.anterior')} className={`uiinde-btnbase ${page === 0 ? 'ui-index-m16' : 'ui-index-m17'}`} onClick={() => setPage(p => Math.max(0, p-1))} disabled={page === 0}>‹</button>
          <span className="uiinde-box-10">{page+1} / {pages}</span>
          <button type="button" aria-label={t('pagination.siguiente')} className={`uiinde-btnbase ${page === pages-1 ? 'ui-index-m16' : 'ui-index-m17'}`} onClick={() => setPage(p => Math.min(pages-1, p+1))} disabled={page === pages-1}>›</button>
        </div>
      )}
    </div>
  )
}

// ── Table simple ──────────────────────────────────────────────────────────────
interface TableProps<T> {
  columns?: Array<ColumnaDeTabla<T>>
  data?: T[]
  /** Si se pasa, cada fila es pulsable **y navegable con teclado**. */
  onRowClick?: (fila: T) => void
}

export function Table<T>({ columns = [], data = [], onRowClick }: TableProps<T>) {
  return (
    <div className="u-scroll-x">
      <table className="uiinde-box-6">
        <thead>
          <tr className="u-border-b">
            {columns.map(col => (
              <th key={col.key} className="uiinde-box-11">{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr className={`uiinde-box-23 ${onRowClick ? 'ui-index-m14' : 'ui-index-m15'}`} key={i} onClick={() => onRowClick?.(row)}
              role={onRowClick ? 'button' : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={onRowClick ? (e: React.KeyboardEvent<HTMLTableRowElement>) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onRowClick(row)
                }
              } : undefined}
              onMouseEnter={e => onRowClick && (e.currentTarget.style.background = 'var(--surface-3)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              {columns.map(col => (
                <td key={col.key} className="uiinde-box-12">
                  {celda(col, row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export { useDialogo } from './useDialogo'
export { Drawer } from './Drawer'
