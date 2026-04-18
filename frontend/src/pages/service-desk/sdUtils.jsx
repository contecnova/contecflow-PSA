/**
 * Shared constants, styles, and tiny presentational components
 * used across all ServiceDesk sub-modules.
 */
import { useState, useEffect } from 'react'
import { COLOR } from '../../constants/theme'

// ── Priority / Status maps ─────────────────────────────────────────────────────
export const PRIORITY_COLOR = {
  p1_critical: COLOR.danger,
  p2_high:     '#fb923c',
  p3_medium:   COLOR.warning,
  p4_low:      COLOR.text2,
}
export const PRIORITY_LABEL = {
  p1_critical: 'P1 Crítico', p2_high: 'P2 Alto',
  p3_medium: 'P3 Medio', p4_low: 'P4 Bajo',
}
export const STATUS_COLOR = {
  new: COLOR.accent, assigned: COLOR.accent, in_progress: '#38bdf8',
  pending_client: COLOR.warning, pending_third: COLOR.warning,
  resolved: COLOR.success, closed: COLOR.text2, cancelled: COLOR.text3,
}

// ── Common inline style objects ────────────────────────────────────────────────
export const INPUT_STYLE = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '9px 13px',
  color: 'var(--text-1)',
  fontSize: 13,
  outline: 'none',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
}
export const LABEL_STYLE = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-2)',
  display: 'block',
  marginBottom: 5,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
}

// ── Formatters ─────────────────────────────────────────────────────────────────
export function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('es-ES', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}
export function fmtMinutes(m) {
  if (!m) return '—'
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60), min = Math.round(m % 60)
  return min > 0 ? `${h}h ${min}m` : `${h}h`
}

// ── Tiny badge components ──────────────────────────────────────────────────────
export function PBadge({ v }) {
  const color = PRIORITY_COLOR[v] || COLOR.text2
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, color,
      padding: '2px 7px', borderRadius: 4,
      border: `1px solid ${color}30`, background: `${color}12`,
      whiteSpace: 'nowrap',
    }}>
      {PRIORITY_LABEL[v] || v}
    </span>
  )
}
export function SBadge({ v }) {
  const color = STATUS_COLOR[v] || COLOR.text2
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, color,
      padding: '2px 8px', borderRadius: 4,
      background: `${color}15`, whiteSpace: 'nowrap',
    }}>
      {v?.replace(/_/g, ' ')}
    </span>
  )
}

// ── useWindowWidth ─────────────────────────────────────────────────────────────
export function useWindowWidth() {
  const [width, setWidth] = useState(
    typeof window !== 'undefined' ? window.innerWidth : 1280,
  )
  useEffect(() => {
    const handler = () => setWidth(window.innerWidth)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return width
}
