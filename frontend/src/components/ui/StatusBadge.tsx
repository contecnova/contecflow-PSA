import type { ReactNode } from 'react'

/**
 * <StatusBadge> — pill semántica para estados libres (no presets).
 *
 * Diferente de <Badge label="approved"/> (que mapea valores conocidos).
 *
 *   <StatusBadge kind="success">Activo</StatusBadge>
 *   <StatusBadge kind="warning" dot>Pendiente</StatusBadge>
 *   <StatusBadge kind="accent" outline>Premium</StatusBadge>
 */
export type StatusBadgeKind = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'accent' | 'purple'

export interface StatusBadgeProps {
  kind?: StatusBadgeKind
  dot?: boolean
  outline?: boolean
  children?: ReactNode
  className?: string
}

export default function StatusBadge({
  kind = 'neutral',
  dot = false,
  outline = false,
  children,
  className = '',
}: StatusBadgeProps) {
  const kindClass = kind === 'neutral' ? '' : ` ds-pill--${kind}`
  return (
    <span className={`ds-pill${kindClass}${outline ? ' ds-pill--outline' : ''} ${className}`.trim()}>
      {dot && <span className={`ds-status-dot ds-status-dot--${kind === 'neutral' ? '' : kind}`} />}
      {children}
    </span>
  )
}
