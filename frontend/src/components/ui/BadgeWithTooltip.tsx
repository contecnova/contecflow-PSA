import type { CSSProperties, MouseEvent, ReactNode } from 'react'
import { alpha } from '../../constants/theme'
import './BadgeWithTooltip.css'

/**
 * Badge with tooltip (hover for info)
 */
export interface BadgeWithTooltipProps {
  label: ReactNode
  color?: string
  tooltip?: string
  icon?: ReactNode
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void
}

export function BadgeWithTooltip({
  label,
  color = 'var(--text-3)',
  tooltip,
  icon,
  onClick,
}: BadgeWithTooltipProps) {
  // Color del dato: la clase lo consume (fondo = el mismo color con alfa 20, como antes).
  const vars = { '--badge-with-tooltip-color': color, '--badge-with-tooltip-fondo': alpha(color, '20') } as CSSProperties

  if (onClick) {
    return (
      <button
        type="button"
        title={tooltip}
        onClick={onClick}
        className="badge-with-tooltip badge-with-tooltip--click"
        style={vars}
      >
        {icon && <span className="u-sm">{icon}</span>}
        {label}
        <span className="uibawito-box-1 badge-with-tooltip-e1" style={{ '--badge-with-tooltip-color': color } as CSSProperties}>ⓘ</span>
      </button>
    )
  }

  return (
    <span title={tooltip} className="badge-with-tooltip" style={vars}>
      {icon && <span className="u-sm">{icon}</span>}
      {label}
      <span className="uibawito-box-1 badge-with-tooltip-e1" style={{ '--badge-with-tooltip-color': color } as CSSProperties}>ⓘ</span>
    </span>
  )
}
