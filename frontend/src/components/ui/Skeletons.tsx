import './Skeletons.css'
import { px } from '../../utils/estilos'
import type { CSSProperties } from 'react'
/**
 * Skeletons — pre-built per-page skeleton screens.
 * All use CSS classes from index.css: .skeleton-line, .skeleton-rect, .skeleton-circle
 */

export interface SkeletonRowsProps {
  count?: number
  cols?: number
}

/* ── Generic row skeleton ────────────────────────────────────────────────────── */
export function SkeletonRows({ count = 5, cols = 4 }: SkeletonRowsProps) {
  return (
    <div className="uiskel-stack-1">
      {Array.from({ length: count }).map((_, i) => (
        <div className="uiskel-grid-9 skeletons-e1" key={i} style={{ '--skeletons-grid-template-columns': `2.5fr ${Array(cols - 1).fill('1fr').join(' ')}` } as CSSProperties}>
          <div className="uiskel-stack-2">
            <div className="skeleton-line skeletons-e2" style={{ '--skeletons-width': `${55 + (i * 13) % 35}%` } as CSSProperties} />
            <div className="skeleton-line uiskel-box-1" />
          </div>
          {Array.from({ length: cols - 1 }).map((_, j) => (
            <div key={j} className="skeleton-line skeletons-e3" style={{ '--skeletons-width': `${40 + (j * 17) % 40}%`, '--skeletons-animation-delay': `${(i + j) * 0.04}s` } as CSSProperties} />
          ))}
        </div>
      ))}
    </div>
  )
}

/* ── Dashboard skeleton ──────────────────────────────────────────────────────── */
export function SkeletonDashboard() {
  return (
    <div className="uiskel-sp-1">
      {/* Header */}
      <div className="uiskel-sp-2">
        <div className="skeleton-line uiskel-box-2" />
        <div className="skeleton-line uiskel-box-3" />
      </div>
      {/* KPI row */}
      <div className="uiskel-grid-1">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton-rect uiskel-box-19 skeletons-e4" style={{ '--skeletons-animation-delay': `${i * 0.06}s` } as CSSProperties} />
        ))}
      </div>
      {/* Row of 3 cards */}
      <div className="uiskel-grid-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="skeleton-rect uiskel-box-20 skeletons-e4" style={{ '--skeletons-animation-delay': `${0.3 + i * 0.07}s` } as CSSProperties} />
        ))}
      </div>
      {/* Row of 2 tall cards */}
      <div className="uiskel-grid-3">
        <div className="skeleton-rect uiskel-box-4" />
        <div className="skeleton-rect uiskel-box-5" />
      </div>
    </div>
  )
}

export interface SkeletonTableProps {
  title?: boolean
  filters?: boolean
  rows?: number
}

/* ── Table page skeleton (Tasks, Resources, etc.) ──────────────────────────── */
export function SkeletonTable({ title = true, filters = true, rows = 8 }: SkeletonTableProps) {
  return (
    <div className="uiskel-sp-3">
      {title && (
        <div className="uiskel-sp-4">
          <div className="skeleton-line uiskel-box-6" />
          <div className="skeleton-line uiskel-box-7" />
        </div>
      )}
      {filters && (
        <div className="uiskel-row-1">
          {[140, 110, 120, 90].map((w, i) => (
            <div key={i} className="skeleton-rect uiskel-box-21 skeletons-e2" style={{ '--skeletons-width': px(w) } as CSSProperties} />
          ))}
          <div className="skeleton-rect uiskel-box-8" />
        </div>
      )}
      {/* Table header */}
      <div className="uiskel-box-9">
        <div className="uiskel-grid-4">
          {['60%','45%','50%','70%','55%','45%'].map((w, i) => (
            <div key={i} className="skeleton-line uiskel-box-22 skeletons-e2" style={{ '--skeletons-width': px(w) } as CSSProperties} />
          ))}
        </div>
        <SkeletonRows count={rows} cols={6} />
      </div>
    </div>
  )
}

/* ── Projects list skeleton ──────────────────────────────────────────────────── */
export function SkeletonProjects() {
  return (
    <div className="uiskel-sp-3">
      <div className="uiskel-row-2">
        <div>
          <div className="skeleton-line uiskel-box-10" />
          <div className="skeleton-line uiskel-box-11" />
        </div>
        <div className="skeleton-rect uiskel-box-12" />
      </div>
      <div className="uiskel-grid-5">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="skeleton-rect uiskel-box-23 skeletons-e4" style={{ '--skeletons-animation-delay': `${i * 0.04}s` } as CSSProperties} />
        ))}
      </div>
    </div>
  )
}

export interface SkeletonGanttProps {
  rows?: number
}

/* ── Gantt skeleton ────────────────────────────────────────────────────────── */
export function SkeletonGantt({ rows = 10 }: SkeletonGanttProps) {
  return (
    <div className="uiskel-sp-5">
      <div className="uiskel-row-3">
        <div className="skeleton-line uiskel-box-13" />
        <div className="uiskel-row-4">
          {[80, 80, 100].map((w, i) => <div key={i} className="skeleton-rect uiskel-box-24 skeletons-e2" style={{ '--skeletons-width': px(w) } as CSSProperties} />)}
        </div>
      </div>
      <div className="uiskel-grid-6">
        <div>
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="uiskel-row-5">
              <div className="skeleton-line skeletons-e3" style={{ '--skeletons-width': `${50 + (i * 19) % 40}%`, '--skeletons-animation-delay': `${i * 0.03}s` } as CSSProperties} />
            </div>
          ))}
        </div>
        <div className="uiskel-box-14">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="uiskel-row-6">
              <div className="skeleton-rect uiskel-box-25 skeletons-e5" style={{ '--skeletons-margin-left': `${(i * 37) % 45}%`, '--skeletons-width': `${15 + (i * 23) % 35}%`, '--skeletons-animation-delay': `${i * 0.04}s` } as CSSProperties} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Service-desk skeleton ────────────────────────────────────────────────── */
export function SkeletonServiceDesk() {
  return (
    <div className="uiskel-sp-6">
      <div className="uiskel-row-7">
        <div className="skeleton-line uiskel-box-15" />
        <div className="uiskel-row-8">
          {[120, 90, 130].map((w, i) => <div key={i} className="skeleton-rect uiskel-box-24 skeletons-e2" style={{ '--skeletons-width': px(w) } as CSSProperties} />)}
        </div>
      </div>
      <div className="uiskel-grid-7">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton-rect uiskel-box-26 skeletons-e4" style={{ '--skeletons-animation-delay': `${i * 0.06}s` } as CSSProperties} />
        ))}
      </div>
      <SkeletonTable title={false} filters={false} rows={8} />
    </div>
  )
}

/* ── Finance / analytics skeleton ────────────────────────────────────────── */
export function SkeletonFinance() {
  return (
    <div className="uiskel-sp-7">
      <div className="u-mb-20">
        <div className="skeleton-line uiskel-box-6" />
        <div className="skeleton-line uiskel-box-16" />
      </div>
      <div className="uiskel-grid-7">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton-rect uiskel-box-27 skeletons-e4" style={{ '--skeletons-animation-delay': `${i * 0.06}s` } as CSSProperties} />
        ))}
      </div>
      <div className="uiskel-grid-8">
        <div className="skeleton-rect uiskel-box-17" />
        <div className="skeleton-rect uiskel-box-18" />
      </div>
    </div>
  )
}
