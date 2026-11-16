import type { CSSProperties } from 'react'
import { GitPullRequestArrow, Lightbulb } from 'lucide-react'
import './FRCRIcons.css'

export interface IconProps {
  style?: CSSProperties
}

/**
 * Icon for Feature Request (FR)
 */
export function IconFR({ style }: IconProps) {
  return <span className="frcr-icono" style={style} aria-hidden><Lightbulb size={14} /></span>
}

/**
 * Icon for Change Request (CR)
 */
export function IconCR({ style }: IconProps) {
  return <span className="frcr-icono" style={style} aria-hidden><GitPullRequestArrow size={14} /></span>
}
