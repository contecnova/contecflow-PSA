import React from 'react'

/**
 * Badge with tooltip (hover for info)
 * Props:
 * - label: string
 * - color: string
 * - tooltip: string
 * - icon: string (optional)
 * - onClick: function (optional)
 */
export function BadgeWithTooltip({ label, color = '#7a8aaa', tooltip, icon, onClick }) {
  return (
    <span
      title={tooltip}
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 10,
        padding: '2px 8px',
        borderRadius: 20,
        background: color + '20',
        color,
        fontWeight: 700,
        cursor: onClick ? 'pointer' : 'default',
        border: onClick ? `1px solid ${color}` : undefined,
        userSelect: 'none',
      }}
    >
      {icon && <span style={{ fontSize: 12 }}>{icon}</span>}
      {label}
      <span style={{ marginLeft: 4, color: color, opacity: 0.7 }}>ⓘ</span>
    </span>
  )
}
