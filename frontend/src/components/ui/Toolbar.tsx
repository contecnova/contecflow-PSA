import type { CSSProperties, ReactNode } from 'react'

/**
 * Toolbar — barra de filtros + acciones para páginas tipo lista.
 */
export interface ToolbarProps {
  left?: ReactNode
  right?: ReactNode
  children?: ReactNode
  dense?: boolean
  style?: CSSProperties
  className?: string
}

export default function Toolbar({ left, right, children, dense = false, style, className }: ToolbarProps) {
  return (
    <div
      role="toolbar"
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: dense ? 8 : 12,
        flexWrap: 'wrap',
        marginBottom: dense ? 12 : 16,
        ...(style || {}),
      }}
    >
      {children ?? (
        <>
          {left && (
            <div style={{ display: 'flex', alignItems: 'center', gap: dense ? 6 : 8, flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
              {left}
            </div>
          )}
          {right && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, marginLeft: 'auto' }}>
              {right}
            </div>
          )}
        </>
      )}
    </div>
  )
}
