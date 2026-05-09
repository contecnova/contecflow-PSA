/**
 * <StatusBadge> — pill semántica para estados libres (no presets).
 *
 * Diferente de <Badge label="approved"/> (que mapea valores conocidos).  Aquí
 * eliges la "tonalidad" (kind) y el texto, útil para estados específicos del
 * dominio o ad-hoc:
 *
 *   <StatusBadge kind="success">Activo</StatusBadge>
 *   <StatusBadge kind="warning" dot>Pendiente</StatusBadge>
 *   <StatusBadge kind="accent" outline>Premium</StatusBadge>
 *
 * `dot` añade un punto de estado · `outline` usa fondo transparente.
 */
export default function StatusBadge({
  kind = 'neutral',  // neutral | success | warning | danger | info | accent | purple
  dot = false,
  outline = false,
  children,
  className = '',
}) {
  const kindClass = kind === 'neutral' ? '' : ` ds-pill--${kind}`
  return (
    <span className={`ds-pill${kindClass}${outline ? ' ds-pill--outline' : ''} ${className}`.trim()}>
      {dot && <span className={`ds-status-dot ds-status-dot--${kind === 'neutral' ? '' : kind}`} />}
      {children}
    </span>
  )
}
