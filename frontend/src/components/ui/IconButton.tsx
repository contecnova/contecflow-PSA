import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react'

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  ariaLabel: string
  title?: string
  children: ReactNode
  style?: CSSProperties
  type?: 'button' | 'submit' | 'reset'
}

export default function IconButton({
  ariaLabel,
  title,
  children,
  style = {},
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
      style={{
        background: 'transparent',
        border: '1px solid transparent',
        borderRadius: 6,
        padding: 6,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        lineHeight: 0,
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  )
}
