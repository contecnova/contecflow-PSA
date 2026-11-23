/**
 * Piezas de control del kit (16-11-2026): barra de filtros, chip de filtro,
 * control segmentado y zona pulsable sin aspecto de botón.
 *
 * Con ellas y `Button` / `IconButton` ninguna pantalla necesita un `<button>`
 * propio (regla `contec/sin-boton-nativo`).
 */
import type { CSSProperties, KeyboardEvent, MouseEvent, ReactNode } from 'react'
import { X } from 'lucide-react'
import { conParametros, useTextoUi } from './useTextoUi'
import './Controles.css'

// ── BarraDeFiltros ───────────────────────────────────────────────────────────

export interface BarraDeFiltrosProps {
  /** Búsqueda, selects, chips… (a la izquierda, con salto de línea). */
  children: ReactNode
  /** Acciones a la derecha (botones), tras el espaciador. */
  acciones?: ReactNode
  /** Nombre accesible del grupo de filtros. */
  'aria-label'?: string
  className?: string
}

/** La barra de filtros bajo la cabecera de una página (`ds-toolbar`). */
export function BarraDeFiltros({ children, acciones, 'aria-label': ariaLabel, className }: BarraDeFiltrosProps) {
  const t = useTextoUi()
  return (
    <div role="group" aria-label={ariaLabel ?? t('uikit.barra_de_filtros')} className={`ds-toolbar ui-barra-filtros${className ? ` ${className}` : ''}`}>
      {children}
      {acciones && <><div className="ds-toolbar__spacer" /><div className="ui-barra-filtros__acciones">{acciones}</div></>}
    </div>
  )
}

// ── FiltrosDeLista ───────────────────────────────────────────────────────────

export interface FiltrosDeListaProps {
  /** El `Buscador`: siempre a todo el ancho. */
  buscador?: ReactNode
  /** Un `Segmentado` (filtro de 2–4 opciones cortas): a todo el ancho, botones iguales. */
  segmentado?: ReactNode
  /** El resto de filtros (`SelectRico`/`Select`): rejilla de 2 columnas iguales. */
  children?: ReactNode
  'aria-label'?: string
  className?: string
}

/**
 * Filtros de una lista en una columna o panel estrecho (23-11-2026). Ningún
 * control se come a los demás: el buscador a todo el ancho, el segmentado a
 * todo el ancho con botones iguales y los desplegables de dos en dos. Nunca
 * tres o más desplegables en una fila que no tenga ancho para su texto más
 * largo. En una barra ancha bajo la cabecera se usa `BarraDeFiltros`.
 */
export function FiltrosDeLista({ buscador, segmentado, children, 'aria-label': ariaLabel, className }: FiltrosDeListaProps) {
  const t = useTextoUi()
  return (
    <div role="group" aria-label={ariaLabel ?? t('uikit.barra_de_filtros')} className={`ui-filtros-lista${className ? ` ${className}` : ''}`}>
      {buscador}
      {segmentado && <div className="ui-filtros-lista__segmentado">{segmentado}</div>}
      {children && <div className="ui-filtros-lista__rejilla">{children}</div>}
    </div>
  )
}

// ── Chip ─────────────────────────────────────────────────────────────────────

export interface ChipProps {
  children: ReactNode
  /** Filtro activo (`aria-pressed`). */
  activo?: boolean
  /** Alterna el filtro. Sin él (y sin `onQuitar`) es una etiqueta estática. */
  onClick?: () => void
  /** Pinta una X para quitar el filtro. */
  onQuitar?: () => void
  icon?: ReactNode
  /** Contador a la derecha. */
  cuenta?: number
  /** Color de un dato (categoría, etiqueta): fondo y borde se derivan de él. */
  color?: string
  disabled?: boolean
  title?: string
  className?: string
}

/** Chip de filtro o etiqueta de texto libre (sin mayúsculas). */
export function Chip({ children, activo = false, onClick, onQuitar, icon, cuenta, color, disabled, title, className }: ChipProps) {
  const t = useTextoUi()
  const clases = `ui-chip${activo ? ' ui-chip--activo' : ''}${color ? ' ui-chip--color' : ''}${className ? ` ${className}` : ''}`
  const estilo = color ? ({ '--chip-color': color } as CSSProperties) : undefined
  const textoChip = typeof children === 'string' || typeof children === 'number' ? String(children) : ''
  const interior = <>{icon && <span className="ui-chip__icono" aria-hidden>{icon}</span>}{children}{cuenta != null && <span className="ui-chip__cuenta">{cuenta}</span>}</>
  if (!onClick && !onQuitar) return <span className={clases} style={estilo} title={title}>{interior}</span>
  return (
    <span className={`${clases} ui-chip--accion`} style={estilo}>
      {onClick
        ? <button type="button" className="ui-chip__boton" aria-pressed={activo} onClick={onClick} disabled={disabled} title={title}>{interior}</button>
        : <span className="ui-chip__boton" title={title}>{interior}</span>}
      {onQuitar && (
        <button type="button" className="ui-chip__quitar" onClick={onQuitar} disabled={disabled}
          aria-label={conParametros(t('uikit.quitar_filtro', { valor: textoChip }), { valor: textoChip })}>
          <X size={12} aria-hidden />
        </button>
      )}
    </span>
  )
}

// ── Segmentado ───────────────────────────────────────────────────────────────

export interface OpcionSegmentada {
  valor: string
  etiqueta: ReactNode
  icon?: ReactNode
  /** Nombre accesible cuando la opción es solo icono. */
  'aria-label'?: string
  disabled?: boolean
}

export interface SegmentadoProps {
  opciones: OpcionSegmentada[]
  valor: string
  onChange: (valor: string) => void
  'aria-label': string
  className?: string
}

/** Elección entre 2–5 vistas o modos (`ds-segmented`). Para pestañas con contenido, `Tabs`. */
export function Segmentado({ opciones, valor, onChange, 'aria-label': ariaLabel, className }: SegmentadoProps) {
  return (
    <div className={`ds-segmented${className ? ` ${className}` : ''}`} role="group" aria-label={ariaLabel}>
      {opciones.map(o => (
        <button key={o.valor} type="button" aria-pressed={o.valor === valor} aria-label={o['aria-label']}
          disabled={o.disabled} onClick={() => onChange(o.valor)}>
          {o.icon && <span className="ui-segmentado__icono" aria-hidden>{o.icon}</span>}
          {o.etiqueta}
        </button>
      ))}
    </div>
  )
}

// ── Pulsable ─────────────────────────────────────────────────────────────────

export interface PulsableProps {
  children: ReactNode
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void
  onKeyDown?: (e: KeyboardEvent<HTMLButtonElement>) => void
  onDoubleClick?: (e: MouseEvent<HTMLButtonElement>) => void
  disabled?: boolean
  title?: string
  className?: string
  /** Variables CSS (`'--x': valor`) que consume la clase. */
  style?: CSSProperties
  type?: 'button' | 'submit'
  'aria-label'?: string
  'aria-pressed'?: boolean
  'aria-expanded'?: boolean
  'aria-controls'?: string
  'aria-current'?: boolean | 'page' | 'step' | 'true' | 'false'
  'aria-haspopup'?: boolean | 'menu' | 'listbox' | 'dialog'
  /** Papel ARIA cuando no es un botón simple: elemento de menú, opción de lista… */
  role?: 'menuitem' | 'menuitemradio' | 'menuitemcheckbox' | 'option' | 'tab' | 'radio' | 'switch' | 'listitem'
  'aria-selected'?: boolean
  'aria-checked'?: boolean
  /** Marcas para tours y pruebas. */
  [atributoData: `data-${string}`]: string | undefined
}

/**
 * Zona pulsable sin aspecto de botón: una tarjeta, un elemento de lista o un
 * enlace de texto que hace una acción. Quita el aspecto nativo (fondo, borde,
 * relleno), hereda la tipografía y conserva el foco visible. El aspecto lo da
 * la clase que se pase. Si parece un botón, es `Button`; si es solo icono,
 * `IconButton`.
 */
export function Pulsable({ children, className, type = 'button', ...resto }: PulsableProps) {
  return <button type={type} className={`ui-pulsable${className ? ` ${className}` : ''}`} {...resto}>{children}</button>
}
