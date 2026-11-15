import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react'
import './IconButton.css'

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  ariaLabel: string
  title?: string
  children: ReactNode
  /** Clases extra (se suman a `icon-button`). */
  className?: string
  style?: CSSProperties
  type?: 'button' | 'submit' | 'reset'
}

export default function IconButton({
  ariaLabel,
  title,
  children,
  className,
  style,
  type = 'button',
  ...rest
}: IconButtonProps) {
  if (import.meta.env.DEV && !ariaLabel) {
    throw new Error('IconButton requires an ariaLabel prop for accessibility.')
  }

  return (
    <button
      type={type}
      aria-label={ariaLabel}
      title={title || ariaLabel}
      className={className ? `icon-button ${className}` : 'icon-button'}
      style={style}
      {...rest}
    >
      {children}
    </button>
  )
}
