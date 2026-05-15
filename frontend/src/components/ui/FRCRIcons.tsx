import type { CSSProperties } from 'react'

export interface IconProps {
  style?: CSSProperties
}

/**
 * Icon for Feature Request (FR)
 */
export function IconFR({ style }: IconProps) {
  return <span style={{ ...style, fontSize: 'var(--text-md)', marginRight: 2 }}>💡</span>
}

/**
 * Icon for Change Request (CR)
 */
export function IconCR({ style }: IconProps) {
  return <span style={{ ...style, fontSize: 'var(--text-md)', marginRight: 2 }}>🔀</span>
}
