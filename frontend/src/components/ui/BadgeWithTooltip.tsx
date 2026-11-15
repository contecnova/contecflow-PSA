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
  const commonStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    fontSize: 'var(--text-2xs)',
    padding: '2px 8px',
    borderRadius: 20,
    background: alpha(color, '20'),
    color,
    fontWeight: 700,
    cursor: onClick ? 'pointer' : 'default',
    border: onClick ? `1px solid ${color}` : undefined,
    userSelect: 'none',
  }

  if (onClick) {
    return (
      <button
        type="button"
        title={tooltip}
        onClick={onClick}
        style={{ ...commonStyle, fontFamily: 'inherit' }}
      >
        {icon && <span className="u-sm">{icon}</span>}
        {label}
        <span className="uibawito-box-1" style={{ color: color }}>ⓘ</span>
      </button>
    )
  }

  return (
    <span title={tooltip} style={commonStyle}>
      {icon && <span className="u-sm">{icon}</span>}
      {label}
      <span className="uibawito-box-1" style={{ color: color }}>ⓘ</span>
    </span>
  )
}
