import type { CSSProperties, ReactNode } from 'react'

/**
 * <StatusBadge> — pill semántica para estados libres (no presets).
 *
 * Diferente de <Badge label="approved"/> (que mapea valores conocidos).
 *
 *   <StatusBadge kind="success">Activo</StatusBadge>
 *   <StatusBadge kind="warning" dot>Pendiente</StatusBadge>
 *   <StatusBadge kind="accent" outline>Premium</StatusBadge>
 *   <StatusBadge color="var(--orange)">P2</StatusBadge>      // color libre
 *   <StatusBadge kind="info" caps={false}>Texto normal</StatusBadge>
 *
 * Es el badge compartido: las pantallas no deben definir el suyo. Si el color
 * sale de un dato (config de estado, color de una categoría), `color` admite
 * cualquier color CSS —`var(--x)` o hex— y fondo y borde se derivan de él.
 */
export type StatusBadgeKind = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'accent' | 'purple' | 'orange'

export interface StatusBadgeProps {
  kind?: StatusBadgeKind
  /** Color libre (prevalece sobre `kind`). Fondo y borde se derivan de él. */
  color?: string
  dot?: boolean
  outline?: boolean
  /** `false` quita las mayúsculas y el espaciado de letra. */
  caps?: boolean
  title?: string
  children?: ReactNode
  className?: string
  style?: CSSProperties
}

export default function StatusBadge({
  kind = 'neutral',
  color,
  dot = false,
  outline = false,
  caps = true,
  title,
  children,
  className = '',
  style,
}: StatusBadgeProps) {
  const kindClass = color ? ' ds-pill--custom' : kind === 'neutral' ? '' : ` ds-pill--${kind}`
  const estilo = color ? ({ '--pill-color': color, ...style } as CSSProperties) : style
  return (
    <span
      className={`ds-pill${kindClass}${outline ? ' ds-pill--outline' : ''}${caps ? '' : ' ds-pill--nocaps'} ${className}`.trim()}
      style={estilo}
      title={title}
    >
      {dot && <span className={`ds-status-dot${color ? ' ds-status-dot--custom' : kind === 'neutral' ? '' : ` ds-status-dot--${kind}`}`} />}
      {children}
    </span>
  )
}
