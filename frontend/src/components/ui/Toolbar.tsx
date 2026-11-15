import type { CSSProperties, ReactNode } from 'react'
import './Toolbar.css'

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
            <div className="uitool-row-2" style={{ gap: dense ? 6 : 8 }}>
              {left}
            </div>
          )}
          {right && (
            <div className="uitool-row-1">
              {right}
            </div>
          )}
        </>
      )}
    </div>
  )
}
