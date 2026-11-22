import { CHART } from '../../constants/theme'
import { useDialogo } from './useDialogo'
import React, { type CSSProperties } from 'react'
import { BarChart3, ClipboardList, FileText, Folder, Inbox, Plus, Search, Users, X } from 'lucide-react'
import { DATA_TABLE_PAGE_SIZE } from '../../constants/pagination'
import './index.css'
import { useTextoUi } from './useTextoUi'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { px } from '../../utils/estilos'
import { CampoFecha } from './SelectorDeFecha'
import { eventoDeCambio } from './DateInput'
import StatusBadge, { type StatusBadgeKind } from './StatusBadge'
import { Tabla } from './Tabla'

export { default as Confirm } from './Confirm'
export { default as IconButton } from './IconButton'
export { default as Tabs, TabPanel } from './Tabs'
export { default as Toolbar } from './Toolbar'
export { default as FormField } from './FormField'
// Design system v2 primitivos
export { default as Page } from './Page'
export { default as Section } from './Section'
export { default as StatusBadge } from './StatusBadge'
export type { StatusBadgeKind, StatusBadgeProps } from './StatusBadge'
// Migración al kit, fase 1 (16-11-2026): tabla común, casillas y controles.
export { Tabla, TablaSimple, CeldaEditable, EditorTexto, EditorLista, EditorFecha } from './Tabla'
export type { TablaProps, TablaSimpleProps, ColumnaTabla, EdicionDeCelda, OrdenDeTabla, ClaveDeFila, DensidadDeTabla, VacioDeTabla, CerrarEditor } from './Tabla'
export { SelectRico } from './SelectRico'
export type { SelectRicoProps, OpcionRica } from './SelectRico'
export { Checkbox, Radio, Switch, GrupoDeOpciones } from './Opciones'
export type { CheckboxProps, GrupoDeOpcionesProps, OpcionDeGrupo } from './Opciones'
export { BarraDeFiltros, Chip, Segmentado, Pulsable } from './Controles'
export type { BarraDeFiltrosProps, ChipProps, SegmentadoProps, OpcionSegmentada, PulsableProps } from './Controles'
// Recurso externo («Externo · proveedor») en listas y selectores de persona
export { default as MarcaExterno, esExterno, textoMarcaExterno, etiquetaDePersona } from './MarcaExterno'
export type { PersonaConEmpresa } from './MarcaExterno'

export {
  ClientSelect, UserSelect, ProjectSelect,
  SprintSelect, EpicSelect, ContractSelect,
  MilestoneSelect, TaskSelect,
  AssetSelect, LicenseSelect, VendorSelect,
  TicketSelect, ProblemSelect, SubcontractorSelect,
} from './EntitySelect'

export { useSort, SortableTH, ariaSort, ViewToggle, FilterSelect, SearchInput, ActiveFilters } from './TableControls'
// Fechas propias del kit y periodo libre de los informes (16-11-2026)
export { CampoFecha, CampoRangoDeFechas } from './SelectorDeFecha'
export type { CampoFechaProps, CampoRangoDeFechasProps, TextosDeFecha } from './SelectorDeFecha'
export { default as DateInput } from './DateInput'
export { default as SelectorDePeriodo } from './SelectorDePeriodo'
// Errores de validación del servidor junto a cada campo (17-11-2026)
export { useErroresDeCampo } from './useErroresDeCampo'
export type { ErroresDeCampo } from './useErroresDeCampo'
// Rejilla única fila × día / semana y su navegador de mes (16-11-2026)
export { default as RejillaPersonaDia, NavegadorDeMes, MuestraDeRejilla, columnasDeDias, columnasDeSemanas, rangoDelMes, isoLocal } from './RejillaPersonaDia'
export type { RejillaPersonaDiaProps, FilaDeRejilla, ColumnaDeRejilla, CeldaDeRejilla, EntradaDeLeyenda, TonoDeRejilla } from './RejillaPersonaDia'

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
  /** Clases de la celda (la base es `ui-celda-datos`). */
  className?: string
  style?: React.CSSProperties
  /** Pinta la celda. Sin él se muestra el valor crudo, o un guion si no hay. */
  render?: (valor: never, fila: T) => React.ReactNode
}

/** Convert snake_case to Title Case as fallback for unknown values. */
function humanize(str?: string | null): string {
  if (!str) return ''
  return String(str).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

interface BadgeProps {
  /** El valor crudo (p. ej. `p1_critical`); elige el tono y, si no hay
   *  `display` ni `children`, tambien el texto. */
  label?: string | null
  /** Texto a mostrar cuando el valor crudo no se quiere ensenar tal cual. */
  display?: React.ReactNode
  /** Tono semantico explicito (prevalece sobre el que sale de `label`). */
  tono?: StatusBadgeKind
  children?: React.ReactNode
  /** Sin uso: se conserva porque hay llamadas que lo pasan. */
  _color?: string
}

/** Tono de cada estado conocido (el resto, neutro). */
const TONO_DE_ESTADO: Record<string, StatusBadgeKind> = {
  low: 'success', medium: 'warning', high: 'danger', critical: 'danger',
  p1_critical: 'danger', p2_high: 'orange', p3_medium: 'warning', p4_low: 'neutral',
  active: 'accent', in_progress: 'accent',
  planning: 'neutral', todo: 'neutral', backlog: 'neutral', draft: 'neutral', normal: 'neutral', cancelled: 'neutral',
  paused: 'warning', in_review: 'warning', review: 'warning', submitted: 'warning', pending: 'warning',
  closed: 'success', done: 'success', accepted: 'success', approved: 'success', resolved: 'success',
  blocked: 'danger', rejected: 'danger', materialized: 'danger',
}

/**
 * Etiqueta de estado. Es `StatusBadge` (la unica pastilla del kit) con el
 * tono sacado del valor crudo: `<Badge label="approved" />`. Con `tono` y
 * `children` es una pastilla libre: `<Badge tono="warning">Pendiente</Badge>`.
 */
export function Badge({ label, display, tono, children, _color }: BadgeProps) {
  const t = useTextoUi()
  void _color
  const kind = tono ?? (label ? TONO_DE_ESTADO[label] : undefined) ?? 'neutral'
  const texto = children ?? display ?? etiquetaCodigo(t, 'estado', label, humanize(label))
  return <StatusBadge kind={kind}>{texto}</StatusBadge>
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
  /** La tarjeta abre algo (una pestaña, un filtro): se pinta como botón. */
  onClick?: () => void
  /** Nombre accesible del botón cuando hay `onClick`. */
  ariaLabel?: string
}

/**
 * KpiCard — la cifra de cabecera de una pantalla.
 *
 * 16-11-2026 (pasada de diseño): una sola forma para todo el producto, la de
 * /projects: cifra grande (sin monoespaciado), etiqueta en versalitas
 * (`ds-eyebrow`) debajo y, si hay, una línea de detalle. El icono es opcional,
 * pequeño y apagado (lucide); un emoji/texto como icono se ignora. `accent`,
 * `danger` y `warning` sólo colorean la cifra: la tarjeta no lleva borde ni
 * fondo de color (eran las variantes que hacían cada pantalla distinta).
 */
export function KpiCard({ icon, label, value, sub, accent, danger, warning, trend, onClick, ariaLabel }: KpiCardProps) {
  const valueColor = danger ? 'var(--danger)' : warning ? 'var(--warning)' : accent ? 'var(--accent)' : 'var(--text-1)'
  const trendColor = (trend ?? 0) > 0 ? 'var(--success)' : (trend ?? 0) < 0 ? 'var(--danger)' : 'var(--text-3)'
  const icono = icon && typeof icon !== 'string' && typeof icon !== 'number' ? icon : null
  const Raiz = onClick ? 'button' : 'div'
  return (
    <Raiz className={`ds-card ui-kpi${onClick ? ' ui-kpi--boton' : ''}`} {...(onClick ? { type: 'button' as const, onClick, 'aria-label': ariaLabel } : {})}>
      <div className="ui-kpi__fila">
        <div className="ui-kpi__valor ui-index-e6" style={{ '--ui-index-color': valueColor } as CSSProperties}>
          {value}
        </div>
        {(icono || trend !== undefined) && (
          <div className="ui-kpi__extra">
            {trend !== undefined && (
              <span className="uiinde-txt-6 ui-index-e6" style={{ '--ui-index-color': trendColor } as CSSProperties}>
                {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'} {Math.abs(trend)}%
              </span>
            )}
            {icono && <span className="ui-kpi__icono" aria-hidden>{icono}</span>}
          </div>
        )}
      </div>
      <div className="ds-eyebrow">{label}</div>
      {sub && <div className="ui-kpi__sub">{sub}</div>}
    </Raiz>
  )
}

/** Emojis y sus modificadores (selector de variante, unión de anchura cero). */
const RE_PICTOGRAMA_G = /[\p{Extended_Pictographic}\u{FE0F}\u{200D}]/gu

// ── Button ────────────────────────────────────────────────────────────────────
interface ButtonProps {
  children?: React.ReactNode
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void
  /** `link`: boton con aspecto de enlace (texto en acento, sin caja). */
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'subtle' | 'link'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  disabled?: boolean
  /** Deshabilita ademas de mostrar el spinner: un boton cargando no se pulsa. */
  loading?: boolean
  icon?: React.ReactNode
  className?: string
  style?: React.CSSProperties
  type?: 'button' | 'submit' | 'reset'
  title?: string
  'aria-label'?: string
  'aria-expanded'?: boolean
  'aria-pressed'?: boolean
  'aria-controls'?: string
  /** Marcas para tours y pruebas (`data-tour`, `data-testid`…). */
  [atributoData: `data-${string}`]: string | undefined
}

export function Button({ children, onClick, variant = 'primary', size = 'md', disabled = false, loading = false, icon = null, className, style, type = 'button', title = undefined, ...resto }: ButtonProps) {
  // 16-11-2026: `subtle` (azul claro) ya no es una variante del estándar; se
  // pinta como `secondary`. Las variantes son primary/secondary/ghost/danger.
  const v = variant === 'subtle' ? 'secondary' : ['primary', 'secondary', 'danger', 'ghost', 'link'].includes(variant) ? variant : 'primary'
  const sz = ['xs', 'sm', 'md', 'lg'].includes(size) ? size : 'md'
  const isDisabled = disabled || loading
  // 16-11-2026 (pasada de diseño): red de seguridad para textos heredados. Un
  // "+ Nuevo…" pasa a icono Plus + "Nuevo…" y los emojis del texto se quitan
  // (el icono va en `icon` y es lucide). Un `icon` de texto (emoji) se ignora.
  let texto: React.ReactNode = children
  let iconoFinal: React.ReactNode = icon && typeof icon !== 'string' ? icon : null
  if (typeof texto === 'string') {
    texto = texto.replace(RE_PICTOGRAMA_G, '').replace(/\s{2,}/g, ' ').trim()
    const conMas = /^\+\s*/.exec(texto as string)
    if (conMas) {
      texto = (texto as string).slice(conMas[0].length)
      if (!iconoFinal) iconoFinal = <Plus size={14} aria-hidden />
    }
  } else if (Array.isArray(texto) && typeof texto[0] === 'string' && /^\s*\+/.test(texto[0])) {
    // `+ {t('…')}` llega como ['+ ', '…']
    const resto = texto[0].replace(/^\s*\+\s*/, '')
    texto = <>{resto}{React.Children.toArray(texto.slice(1))}</>
    if (!iconoFinal) iconoFinal = <Plus size={14} aria-hidden />
  }

  return (
    <button
      {...resto}
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
      ) : iconoFinal ? <span className="uiinde-txt-3">{iconoFinal}</span> : null}
      {texto}
    </button>
  )
}

// ── Input ─────────────────────────────────────────────────────────────────────
// Auditoria 2026-11 (#10): la <label> no estaba asociada al control (sin
// htmlFor/id), asi que el lector de pantalla anunciaba "campo de edicion" sin
// nombre y pulsar la etiqueta no enfocaba. Ahora cada campo genera su id con
// useId (o usa el que se pase) y enlaza ayuda y error con aria-describedby.
export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'className' | 'style' | 'value' | 'type'> {
  label?: React.ReactNode
  value?: string | number | readonly string[]
  type?: string
  /** Solo pinta el asterisco: la validacion es de quien lo usa. */
  required?: boolean
  /** Clases del contenedor (la maqueta base es `ui-field`). */
  className?: string
  /** Clases extra del propio `<input>` (p. ej. `u-mono`). */
  inputClassName?: string
  style?: React.CSSProperties
  hint?: React.ReactNode
  /** Mensaje de error: se pinta bajo el campo y marca aria-invalid. */
  error?: React.ReactNode
  /** Id del control; si no se pasa se genera uno. */
  id?: string
  /** Nombre accesible cuando no hay `label` visible. */
  'aria-label'?: string
  min?: number | string
  max?: number | string
  step?: number | string
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


export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input({ label, value, onChange, placeholder, type = 'text', required, className, inputClassName, style, hint, error, id, 'aria-label': ariaLabel, maxLength, autoFocus, inputMode, disabled, min, max, step, onFocus, onBlur, ...resto }, ref) {
  const { base, idHint, idError, describedBy } = useIdsDeCampo(id, hint, error)
  // 16-11-2026: fecha, fecha y hora u hora → el selector propio del kit (nunca el nativo).
  const modoFecha = type === 'date' ? 'fecha' : type === 'datetime-local' ? 'fechaHora' : type === 'time' ? 'hora' : null
  if (modoFecha) {
    return (
      <div className={className ? `ui-field ${className}` : 'ui-field'} style={style}>
        {label && (
          <label htmlFor={base} id={`${base}-etiqueta`} className="uiinde-estiloetiqueta">
            {label}{required && <span className="u-danger" aria-hidden="true"> *</span>}
          </label>
        )}
        <CampoFecha
          id={base}
          modo={modoFecha}
          value={value == null ? '' : String(value)}
          onChange={v => onChange?.(eventoDeCambio(v, undefined, base))}
          placeholder={placeholder}
          min={min == null ? undefined : String(min)}
          max={max == null ? undefined : String(max)}
          required={required}
          disabled={disabled}
          autoFocus={autoFocus}
          aria-labelledby={label ? `${base}-etiqueta` : undefined}
          aria-label={label ? undefined : ariaLabel}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
        />
        {hint && <div id={idHint} className="u-text3-xs">{hint}</div>}
        {error && <div id={idError} role="alert" className="u-field-error">{error}</div>}
      </div>
    )
  }
  return (
    <div className={className ? `ui-field ${className}` : 'ui-field'} style={style}>
      {label && (
        <label htmlFor={base} id={`${base}-etiqueta`} className="uiinde-estiloetiqueta">
          {label}{required && <span className="u-danger" aria-hidden="true"> *</span>}
        </label>
      )}
      <input className={inputClassName ? `uiinde-box-18 index-sx3 ui-index-e7 ${inputClassName}` : 'uiinde-box-18 index-sx3 ui-index-e7'}
        ref={ref}
        {...resto}
        id={base}
        aria-labelledby={label ? `${base}-etiqueta` : resto['aria-labelledby']}
        aria-label={label ? undefined : ariaLabel}
        type={type} value={value} onChange={onChange} placeholder={placeholder}
        maxLength={maxLength} autoFocus={autoFocus} inputMode={inputMode} disabled={disabled}
        min={min} max={max} step={step}
        required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={resto['aria-describedby'] ?? describedBy}
        style={{ '--ui-index-border': `1px solid ${error ? 'var(--danger-border)' : 'var(--surface-4)'}` } as CSSProperties}
        onFocus={e => {
          e.target.style.borderColor = 'color-mix(in srgb, var(--accent) 50%, transparent)'
          e.target.style.boxShadow = '0 0 0 3px color-mix(in srgb, var(--accent) 8%, transparent)'
          onFocus?.(e)
        }}
        onBlur={e => {
          e.target.style.borderColor = error ? 'var(--danger-border)' : 'var(--surface-4)'
          e.target.style.boxShadow = 'none'
          onBlur?.(e)
        }}
      />
      {hint && <div id={idHint} className="u-text3-xs">{hint}</div>}
      {error && <div id={idError} role="alert" className="u-field-error">{error}</div>}
    </div>
  )
})

// ── Textarea ──────────────────────────────────────────────────────────────────
// Mismo estilo, etiqueta, ayuda, error y aria que Input (migración al kit,
// 20-11-2026: ningún <textarea> suelto fuera de components/ui).
export interface TextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'className' | 'style'> {
  label?: React.ReactNode
  required?: boolean
  /** Clases del contenedor (la maqueta base es `ui-field`). */
  className?: string
  /** Clases extra del propio `<textarea>` (p. ej. `u-mono`). */
  inputClassName?: string
  style?: React.CSSProperties
  hint?: React.ReactNode
  error?: React.ReactNode
  id?: string
  'aria-label'?: string
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea({ label, required, className, inputClassName, style, hint, error, id, 'aria-label': ariaLabel, rows = 3, onFocus, onBlur, ...resto }, ref) {
  const { base, idHint, idError, describedBy } = useIdsDeCampo(id, hint, error)
  return (
    <div className={className ? `ui-field ${className}` : 'ui-field'} style={style}>
      {label && (
        <label htmlFor={base} id={`${base}-etiqueta`} className="uiinde-estiloetiqueta">
          {label}{required && <span className="u-danger" aria-hidden="true"> *</span>}
        </label>
      )}
      <textarea className={inputClassName ? `uiinde-box-18 index-sx3 ui-index-e7 ui-textarea ${inputClassName}` : 'uiinde-box-18 index-sx3 ui-index-e7 ui-textarea'}
        ref={ref}
        rows={rows}
        {...resto}
        id={base}
        aria-labelledby={label ? `${base}-etiqueta` : resto['aria-labelledby']}
        aria-label={label ? undefined : ariaLabel}
        required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={resto['aria-describedby'] ?? describedBy}
        style={{ '--ui-index-border': `1px solid ${error ? 'var(--danger-border)' : 'var(--surface-4)'}` } as CSSProperties}
        onFocus={e => {
          e.target.style.borderColor = 'color-mix(in srgb, var(--accent) 50%, transparent)'
          e.target.style.boxShadow = '0 0 0 3px color-mix(in srgb, var(--accent) 8%, transparent)'
          onFocus?.(e)
        }}
        onBlur={e => {
          e.target.style.borderColor = error ? 'var(--danger-border)' : 'var(--surface-4)'
          e.target.style.boxShadow = 'none'
          onBlur?.(e)
        }}
      />
      {hint && <div id={idHint} className="u-text3-xs">{hint}</div>}
      {error && <div id={idError} role="alert" className="u-field-error">{error}</div>}
    </div>
  )
})

// ── Select ────────────────────────────────────────────────────────────────────
// El unico desplegable de la app (16-11-2026, migracion al kit): `<select>`
// nativo estilizado, 38 px como Input y Button md (32 px con `tamano="sm"`).
// Con `label`/`hint`/`error` va dentro de un campo (`ui-field`); con `suelto`
// es solo el control, para barras de filtros y celdas de tabla.
interface SelectProps {
  label?: React.ReactNode
  value?: string | number
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void
  /** `disabled` deja ver la opción sin poder elegirla (p. ej. una granularidad no admitida). */
  options?: Array<{ value: string | number; label: string; disabled?: boolean }>
  /** Opciones propias (`<option>`, `<optgroup>`) tras las de `options`. */
  children?: React.ReactNode
  /** Clases del contenedor (la maqueta base es `ui-field`); con `suelto`, del `<select>`. */
  className?: string
  style?: React.CSSProperties
  hint?: React.ReactNode
  error?: React.ReactNode
  id?: string
  name?: string
  disabled?: boolean
  required?: boolean
  autoFocus?: boolean
  title?: string
  onBlur?: (e: React.FocusEvent<HTMLSelectElement>) => void
  onKeyDown?: (e: React.KeyboardEvent<HTMLSelectElement>) => void
  /** Nombre accesible cuando no hay `label` visible. */
  'aria-label'?: string
  'aria-describedby'?: string
  /** Texto de la opción vacía inicial («Selecciona…» por defecto); `false`
   *  la quita (cuando siempre hay un valor elegido). */
  placeholder?: string | false
  /** Solo el control, sin el campo con etiqueta (barras, tablas). */
  suelto?: boolean
  tamano?: 'sm' | 'md'
  /** Marcas para tours y pruebas. */
  [atributoData: `data-${string}`]: string | undefined
}

export function Select({ label, value, onChange, options = [], children, className, style, hint, error, id, disabled, required, 'aria-label': ariaLabel, 'aria-describedby': ariaDescribedBy, placeholder, suelto = false, tamano = 'md', ...resto }: SelectProps) {
  const t = useTextoUi()
  const { base, idHint, idError, describedBy } = useIdsDeCampo(id, hint, error)
  const vacio = value === undefined || value === null || value === ''
  const control = (
    <select className={`uiinde-box-19 index-sx3 ui-index-e7 ${vacio ? 'ui-index-m9' : 'ui-index-m8'}${tamano === 'sm' ? ' ui-select--sm' : ''}${suelto ? ' ui-select--suelto' : ''}${suelto && className ? ` ${className}` : ''}`}
      {...resto}
      id={suelto ? id : base}
      value={value} onChange={onChange}
      disabled={disabled} required={required || undefined}
      aria-label={label ? undefined : ariaLabel}
      aria-invalid={error ? true : undefined}
      aria-describedby={[describedBy, ariaDescribedBy].filter(Boolean).join(' ') || undefined}
      style={{ ...(suelto ? style : null), '--ui-index-border': `1px solid ${error ? 'var(--danger-border)' : 'var(--surface-4)'}` } as CSSProperties}
    >
      {placeholder !== false && <option value="">{placeholder ?? t('invoices.select')}</option>}
      {options.map(o => <option key={o.value} value={o.value} disabled={o.disabled || undefined}>{o.label}</option>)}
      {children}
    </select>
  )
  if (suelto) return control
  return (
    <div className={className ? `ui-field ${className}` : 'ui-field'} style={style}>
      {label && (
        <label htmlFor={base} className="uiinde-estiloetiqueta">
          {label}
        </label>
      )}
      {control}
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

// ── Empty state ───────────────────────────────────────────────────────────────
// ── Iconos de los estados vacíos ─────────────────────────────────────────────
// 16-11-2026 (pasada de diseño): los vacíos se pintan SIEMPRE con un icono
// lucide. Antes `icon` aceptaba además un emoji o texto suelto "por
// compatibilidad" y medio producto pasaba un emoji: cada vacío salía
// distinto, con el emoji del sistema operativo y sin seguir el tema. Ahora un
// texto que no sea una de estas claves se ignora y sale el icono neutro.
const EMPTY_ICONS = {
  folder: <Folder size={28} strokeWidth={1.5} aria-hidden />,
  tasks: <ClipboardList size={28} strokeWidth={1.5} aria-hidden />,
  search: <Search size={28} strokeWidth={1.5} aria-hidden />,
  users: <Users size={28} strokeWidth={1.5} aria-hidden />,
  docs: <FileText size={28} strokeWidth={1.5} aria-hidden />,
  chart: <BarChart3 size={28} strokeWidth={1.5} aria-hidden />,
  inbox: <Inbox size={28} strokeWidth={1.5} aria-hidden />,
}

/** Las claves con nombre que acepta `EmptyState`/`DataTable` como `icon`. */
export type ClaveDeIconoVacio = keyof typeof EMPTY_ICONS

/** Un emoji (o cualquier carácter pictográfico) en un texto. */
const RE_PICTOGRAMA = /[\p{Extended_Pictographic}]/u

/** El icono que se pinta: un nodo (lucide) tal cual; una clave conocida, su
 *  icono; cualquier otro texto (emoji, "○", "!") → el icono neutro. */
function iconoDeVacio(icon: React.ReactNode): React.ReactNode {
  if (icon == null || icon === false || icon === '') return EMPTY_ICONS.inbox
  if (typeof icon === 'string') {
    const conocido = EMPTY_ICONS[icon as ClaveDeIconoVacio]
    if (conocido) return conocido
    if (import.meta.env.DEV && RE_PICTOGRAMA.test(icon)) {
      console.warn(`[EmptyState] icono "${icon}" ignorado: usa un icono lucide`)
    }
    return EMPTY_ICONS.inbox
  }
  return icon
}

interface EmptyStateProps {
  /** Un icono lucide (`<Folder size={28} />`) o una clave de `EMPTY_ICONS`.
   *  Los emojis/textos ya no se pintan: salen como el icono neutro. */
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
  const resolvedIcon = svgIcon || iconoDeVacio(icon)

  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden>{resolvedIcon}</div>
      <div className="empty-state-title">{title}</div>
      {description && <div className="empty-state-desc">{description}</div>}
      {(action || (ctaLabel && onCta)) && (
        <div className="uiinde-sp-1">
          {action || (
            <Button icon={<Plus size={15} aria-hidden />} onClick={onCta}>{ctaLabel}</Button>
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
// 16-11-2026 (migracion al kit): `DataTable` y `Table` son `Tabla` con su API
// de siempre. DataTable anade el filtro de texto y la paginacion en cliente.
interface DataTableProps<T> {
  columns: Array<ColumnaDeTabla<T>>
  data?: T[]
  loading?: boolean
  emptyIcon?: React.ReactNode
  emptyTitle?: React.ReactNode
  pageSize?: number
}

export function DataTable<T>({ columns, data = [], loading, emptyIcon = 'inbox', emptyTitle, pageSize = DATA_TABLE_PAGE_SIZE }: DataTableProps<T>) {
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

  return (
    <div>
      {data.length > pageSize && (
        <div className="u-mb-12">
          <input aria-label={t('uikit.filtrar')} value={filter} onChange={e => { setFilter(e.target.value); setPage(0) }}
            placeholder={t('uikit.filtrar')} className="uiinde-box-5" />
        </div>
      )}
      <Tabla<T>
        columnas={columns.map(c => ({ ...c, sortable: c.sortable !== false }))}
        filas={pageData}
        orden={sort}
        onOrden={setSort}
        cargando={loading}
        vacio={{ icono: iconoDeVacio(emptyIcon), titulo: emptyTitle ?? t('uikit.sin_datos') }}
      />
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
  return <Tabla<T> columnas={columns} filas={data} onFila={onRowClick} claveDeFila={(_f, i) => i} />
}

export { useDialogo } from './useDialogo'
export { Drawer } from './Drawer'
