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
      className={`uitool${dense ? ' uitool--dense' : ''}${className ? ` ${className}` : ''}`}
      style={style}
    >
      {children ?? (
        <>
          {left && (
            <div className="uitool-row-2">
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
