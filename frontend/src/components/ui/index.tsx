import { CHART } from '../../constants/theme'
import { useDialogo } from './useDialogo'
import React from 'react'
import { X } from 'lucide-react'

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
/** Human-readable labels for common status/priority enum values. */
const BADGE_DISPLAY: Record<string, string> = {
  // Task / project statuses
  in_progress:  'In Progress',
  todo:         'To Do',
  backlog:      'Backlog',
  done:         'Done',
  blocked:      'Blocked',
  review:       'In Review',
  in_review:    'In Review',
  planning:     'Planning',
  active:       'Active',
  paused:       'Paused',
  closed:       'Closed',
  cancelled:    'Cancelled',
  on_hold:      'On Hold',
  // Priority
  low:          'Low',
  medium:       'Medium',
  high:         'High',
  critical:     'Critical',
  p1_critical:  'P1 Critical',
  p2_high:      'P2 High',
  p3_medium:    'P3 Medium',
  p4_low:       'P4 Low',
  // Deliverables
  planned:      'Planned',
  delivered:    'Delivered',
  accepted:     'Accepted',
  rejected:     'Rejected',
  // Approvals / expenses
  draft:        'Draft',
  submitted:    'Submitted',
  approved:     'Approved',
  pending:      'Pending',
  // Risk
  identified:   'Identified',
  analyzing:    'Analyzing',
  mitigating:   'Mitigating',
  monitoring:   'Monitoring',
  materialized: 'Materialized',
  // Service desk
  open:         'Open',
  new:          'New',
  resolved:     'Resolved',
  // Tickets support level
  l1: 'L1', l2: 'L2', l3: 'L3',
  // Boolean-like
  normal:       'Normal',
}


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
  const texto = (label && BADGE_DISPLAY[label]) || humanize(label)
  const shown: React.ReactNode = display || texto
  return (
    <span
      style={{
        fontSize: "var(--text-xs)", fontWeight: 600, padding: '2px 8px', borderRadius: 'var(--radius-full)',
        background: c.bg, color: c.text, border: `1px solid ${c.border}`,
        textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap',
        display: 'inline-block',
      }}
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
    <div role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={max}
      aria-label={label || `${Math.round(pct)}%`}
      style={{ background: 'var(--surface-4)', borderRadius: 'var(--radius-full)', height, overflow: 'hidden' }}>
      <div style={{
        width: `${pct}%`, height: '100%', background: color,
        borderRadius: 'var(--radius-full)', transition: 'width 0.5s ease',
      }} />
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
    <img src={url} alt={name} loading="lazy" decoding="async" style={{ width: size, height: size, borderRadius: '50%', objectFit: 'cover' }} />
  ) : (
    <div
      role="img"
      aria-label={name || 'Usuario'}
      style={{
      width: size, height: size, borderRadius: '50%', display: 'flex', flexShrink: 0,
      alignItems: 'center', justifyContent: 'center', fontSize: Math.round(size * 0.36),
      fontWeight: 700, background: `linear-gradient(145deg, ${from}, ${to})`,
      color: 'var(--on-accent-light)', letterSpacing: '0.02em',
    }}>
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

export function Card({ children, className, style = {}, accent = false, onClick = undefined }: CardProps) {
  if (onClick) {
    const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        onClick(e)
      }
    }

    return (
      <div
        className={className}
        onClick={onClick}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        style={{
          background: 'var(--surface-2)',
          border: `1px solid ${accent ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}`,
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-6)',
          boxShadow: accent ? 'var(--shadow-accent)' : 'none',
          cursor: 'pointer',
          transition: 'border-color 0.15s, box-shadow 0.15s',
          ...style,
        }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = accent ? 'var(--accent-border-strong)' : 'var(--surface-5)'
          e.currentTarget.style.boxShadow = 'var(--shadow-md)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = accent ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'
          e.currentTarget.style.boxShadow = accent ? 'var(--shadow-accent)' : 'none'
        }}
      >
        {children}
      </div>
    )
  }

  return (
    <div
      className={className}
      style={{
        background: 'var(--surface-2)',
        border: `1px solid ${accent ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}`,
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-6)',
        boxShadow: accent ? 'var(--shadow-accent)' : 'none',
        cursor: 'default',
        transition: 'border-color 0.15s, box-shadow 0.15s',
        ...style,
      }}
    >
      {children}
    </div>
  )
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
    <Card accent={accent} style={{ flex: 1, minWidth: 140 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-3)' }}>
        <div style={{ fontSize: "var(--text-xl)" }}>{icon}</div>
        {trend !== undefined && (
          <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: trendColor }}>
            {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'} {Math.abs(trend)}%
          </span>
        )}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: "var(--text-2xl-em)", fontWeight: 700,
        color: valueColor, letterSpacing: '-0.02em', lineHeight: 1, marginBottom: 6,
      }}>
        {value}
      </div>
      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', fontWeight: 500 }}>{label}</div>
      {sub && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 3 }}>{sub}</div>}
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
  style?: React.CSSProperties
  type?: 'button' | 'submit' | 'reset'
  title?: string
}

export function Button({ children, onClick, variant = 'primary', size = 'md', disabled = false, loading = false, icon = null, style = {}, type = 'button', title = undefined }: ButtonProps) {
  const variants: Record<string, React.CSSProperties> = {
    primary:   {
      background: 'var(--accent)',
      color: 'var(--on-accent)',   // blanco fijo no llegaba a AA (2,37:1 en freight)
      border: 'none',
      boxShadow: '0 1px 3px var(--accent-border)',
    },
    secondary: {
      background: 'var(--surface-3)',
      color: 'var(--text-1)',
      border: '1px solid var(--surface-4)',
    },
    danger:    {
      background: 'var(--danger-bg)',
      color: 'var(--danger)',
      border: '1px solid var(--danger-border)',
    },
    ghost:     {
      background: 'transparent',
      color: 'var(--accent)',
      border: '1px solid color-mix(in srgb, var(--accent) 25%, transparent)',
    },
    subtle:    {
      background: 'var(--accent-muted)',
      color: 'var(--accent)',
      border: '1px solid color-mix(in srgb, var(--accent) 15%, transparent)',
    },
  }
  const sizes: Record<string, { fontSize: string; padding: string; borderRadius: string; gap: number }> = {
    xs: { fontSize: "var(--text-xs)", padding: '4px 10px',  borderRadius: 'var(--radius-sm)', gap: 4 },
    sm: { fontSize: "var(--text-sm)", padding: '6px 14px',  borderRadius: 'var(--radius-md)', gap: 5 },
    md: { fontSize: "var(--text-base)", padding: '8px 18px',  borderRadius: 'var(--radius-md)', gap: 6 },
    lg: { fontSize: "var(--text-md)", padding: '11px 24px', borderRadius: 'var(--radius-lg)', gap: 7 },
  }
  const v = variants[variant] || variants.primary
  const s = sizes[size] || sizes.md
  const isDisabled = disabled || loading

  return (
    <button
      type={type}
      title={title}
      onClick={isDisabled ? undefined : onClick}
      aria-disabled={isDisabled || undefined}
      aria-busy={loading || undefined}
      disabled={isDisabled}
      style={{
        display: 'inline-flex', alignItems: 'center',
        fontFamily: 'var(--font-sans)', fontWeight: 600,
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        opacity: isDisabled ? 0.5 : 1,
        transition: 'opacity 0.15s, transform 0.1s, background 0.15s',
        whiteSpace: 'nowrap',
        ...v, ...s, ...style,
      }}
      onMouseEnter={e => { if (!isDisabled) e.currentTarget.style.opacity = '0.85' }}
      onMouseLeave={e => { if (!isDisabled) e.currentTarget.style.opacity = '1' }}
      onMouseDown={e => { if (!isDisabled) e.currentTarget.style.transform = 'scale(0.97)' }}
      onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)' }}
    >
      {loading ? (
        <span style={{
          display: 'inline-block', width: 12, height: 12,
          border: '2px solid currentColor', borderTopColor: 'transparent',
          borderRadius: '50%', animation: 'spin 0.65s linear infinite',
        }} />
      ) : icon ? <span style={{ fontSize: '1em', lineHeight: 1 }}>{icon}</span> : null}
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

const ESTILO_ETIQUETA: React.CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }

export function Input({ label, value, onChange, placeholder, type = 'text', required, style = {}, hint, error, id }: InputProps) {
  const { base, idHint, idError, describedBy } = useIdsDeCampo(id, hint, error)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
      {label && (
        <label htmlFor={base} style={ESTILO_ETIQUETA}>
          {label}{required && <span className="u-danger" aria-hidden="true"> *</span>}
        </label>
      )}
      <input
        id={base}
        type={type} value={value} onChange={onChange} placeholder={placeholder}
        required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        style={{
          background: 'var(--surface-3)', border: `1px solid ${error ? 'var(--danger-border)' : 'var(--surface-4)'}`,
          borderRadius: 'var(--radius-md)', padding: '9px 13px',
          color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none',
          fontFamily: 'var(--font-sans)', width: '100%',
          transition: 'border-color 0.15s, box-shadow 0.15s',
        }}
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
  const { base, idHint, idError, describedBy } = useIdsDeCampo(id, hint, error)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
      {label && (
        <label htmlFor={base} style={ESTILO_ETIQUETA}>
          {label}
        </label>
      )}
      <select
        id={base}
        value={value} onChange={onChange}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        style={{
          background: 'var(--surface-3)', border: `1px solid ${error ? 'var(--danger-border)' : 'var(--surface-4)'}`,
          borderRadius: 'var(--radius-md)', padding: '9px 13px',
          color: value ? 'var(--text-1)' : 'var(--text-3)', fontSize: "var(--text-base)",
          outline: 'none', fontFamily: 'var(--font-sans)', cursor: 'pointer', width: '100%',
        }}
      >
        <option value="">Seleccionar...</option>
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

export function Spinner({ size = 22, color = 'var(--accent)', label = 'Cargando...' }: SpinnerProps) {
  return (
    <div role="status" aria-label={label} style={{
      width: size, height: size, borderRadius: '50%',
      border: `2px solid var(--surface-4)`, borderTopColor: color,
      animation: 'spin 0.65s linear infinite', flexShrink: 0,
    }} />
  )
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
          ? <span style={{ fontSize: "var(--text-2xl-em)" }}>{icon}</span>
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
        <div style={{ marginTop: 8 }}>
          {action || (
            <button className="btn-primary" onClick={onCta}
              style={{ fontSize: "var(--text-base)", padding: '8px 20px' }}>
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
  const anchoFinal = width ?? ANCHOS_DE_MODAL[size ?? 'md']
  // Trampa de foco, Esc y devolucion del foco: compartido con los dialogos propios.
  const dialogRef = useDialogo<HTMLDivElement>(open, onClose)

  if (!open) return null
  return (
    <div
      onMouseDown={onClose}
      role="presentation"
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(8,12,20,0.85)',
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        zIndex: 'var(--z-modal)', padding: '40px 24px',
        overflowY: 'auto',
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        onMouseDown={e => e.stopPropagation()}
        style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--surface-4)',
          borderRadius: 'var(--radius-xl)',
          width: '100%', maxWidth: anchoFinal,
          padding: 28, animation: 'fadeUp 0.2s ease',
          boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 22 }}>
          <div>
            <h2 style={{ fontSize: "var(--text-lg)", fontWeight: 700, color: 'var(--text-1)' }}>{title}</h2>
            {subtitle && <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 3 }}>{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="Cerrar"
            style={{
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 'var(--radius-sm)', color: 'var(--text-2)',
              cursor: 'pointer', width: 28, height: 28, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              flexShrink: 0, marginLeft: 12, marginTop: 2,
            }}
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

export function DataTable<T>({ columns, data = [], loading, emptyIcon = '○', emptyTitle = 'Sin datos', pageSize = 15 }: DataTableProps<T>) {
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

  const btnBase = {
    background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 'var(--radius-sm)', color: 'var(--text-1)',
    padding: '4px 10px', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'var(--font-sans)',
  }

  return (
    <div>
      {data.length > pageSize && (
        <div className="u-mb-12">
          <input aria-label="Filtrar..." value={filter} onChange={e => { setFilter(e.target.value); setPage(0) }}
            placeholder="Filtrar..." style={{
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 'var(--radius-md)', padding: '7px 12px',
              color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none',
              fontFamily: 'var(--font-sans)', width: 220,
            }} />
        </div>
      )}
      <div className="u-scroll-x">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
          <thead>
            <tr className="u-border-b">
              {columns.map(col => (
                <th key={col.key} onClick={() => col.sortable !== false && toggleSort(col.key)}
                  style={{
                    textAlign: 'left', padding: '10px 14px', fontSize: "var(--text-xs)", fontWeight: 600,
                    color: sort.col === col.key ? 'var(--accent)' : 'var(--text-2)',
                    textTransform: 'uppercase', letterSpacing: '0.07em', whiteSpace: 'nowrap',
                    cursor: col.sortable !== false ? 'pointer' : 'default',
                    userSelect: 'none',
                  }}>
                  {col.label}
                  {sort.col === col.key && <span style={{ marginLeft: 4, opacity: 0.7 }}>{sort.dir === 'asc' ? '↑' : '↓'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length} style={{ textAlign: 'center', padding: 32 }}>
                <div style={{ display: 'flex', justifyContent: 'center' }}><Spinner /></div>
              </td></tr>
            ) : pageData.length === 0 ? (
              <tr><td colSpan={columns.length}>
                <EmptyState icon={emptyIcon} title={emptyTitle} />
              </td></tr>
            ) : pageData.map((row, i) => (
              <tr key={(row as { id?: string }).id || i}
                style={{ borderBottom: '1px solid var(--surface-4)', transition: 'background 0.1s' }}
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
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'flex-end', marginTop: 14 }}>
          <span className="u-text3-xs">{sorted.length} registros</span>
          <button onClick={() => setPage(p => Math.max(0, p-1))} disabled={page === 0} style={{ ...btnBase, opacity: page === 0 ? 0.4 : 1, cursor: page === 0 ? 'not-allowed' : 'pointer' }}>‹</button>
          <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', minWidth: 60, textAlign: 'center' }}>{page+1} / {pages}</span>
          <button onClick={() => setPage(p => Math.min(pages-1, p+1))} disabled={page === pages-1} style={{ ...btnBase, opacity: page === pages-1 ? 0.4 : 1, cursor: page === pages-1 ? 'not-allowed' : 'pointer' }}>›</button>
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
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
        <thead>
          <tr className="u-border-b">
            {columns.map(col => (
              <th key={col.key} style={{
                padding: '10px 14px', textAlign: 'left', fontSize: "var(--text-xs)", fontWeight: 600,
                color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', whiteSpace: 'nowrap',
              }}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} onClick={() => onRowClick?.(row)} style={{
              borderBottom: '1px solid var(--surface-4)',
              cursor: onRowClick ? 'pointer' : 'default', transition: 'background 0.1s',
            }}
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
                <td key={col.key} style={{ padding: '11px 14px', color: 'var(--text-1)' }}>
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
