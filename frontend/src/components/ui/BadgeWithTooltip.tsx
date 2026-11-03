import type { CSSProperties, MouseEvent, ReactNode } from 'react'
import { alpha } from '../../constants/theme'

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
        {icon && <span style={{ fontSize: 'var(--text-sm)' }}>{icon}</span>}
        {label}
        <span style={{ marginLeft: 4, color: color, opacity: 0.7 }}>ⓘ</span>
      </button>
    )
  }

  return (
    <span title={tooltip} style={commonStyle}>
      {icon && <span style={{ fontSize: 'var(--text-sm)' }}>{icon}</span>}
      {label}
      <span style={{ marginLeft: 4, color: color, opacity: 0.7 }}>ⓘ</span>
    </span>
  )
}
