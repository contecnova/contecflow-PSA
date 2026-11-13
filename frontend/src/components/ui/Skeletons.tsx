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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{
          display: 'grid',
          gridTemplateColumns: `2.5fr ${Array(cols - 1).fill('1fr').join(' ')}`,
          gap: 16, padding: '14px 20px',
          borderBottom: '1px solid var(--surface-3)',
          alignItems: 'center',
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <div className="skeleton-line" style={{ width: `${55 + (i * 13) % 35}%` }} />
            <div className="skeleton-line" style={{ height: 10, width: '35%', opacity: 0.6 }} />
          </div>
          {Array.from({ length: cols - 1 }).map((_, j) => (
            <div key={j} className="skeleton-line" style={{ width: `${40 + (j * 17) % 40}%`, animationDelay: `${(i + j) * 0.04}s` }} />
          ))}
        </div>
      ))}
    </div>
  )
}

/* ── Dashboard skeleton ──────────────────────────────────────────────────────── */
export function SkeletonDashboard() {
  return (
    <div style={{ padding: 32 }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div className="skeleton-line" style={{ width: 160, height: 24, marginBottom: 8 }} />
        <div className="skeleton-line" style={{ width: 280, height: 12, opacity: 0.6 }} />
      </div>
      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 12, marginBottom: 20 }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton-rect" style={{ height: 88, animationDelay: `${i * 0.06}s` }} />
        ))}
      </div>
      {/* Row of 3 cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 16 }}>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="skeleton-rect" style={{ height: 220, animationDelay: `${0.3 + i * 0.07}s` }} />
        ))}
      </div>
      {/* Row of 2 tall cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <div className="skeleton-rect" style={{ height: 260, animationDelay: '0.5s' }} />
        <div className="skeleton-rect" style={{ height: 260, animationDelay: '0.57s' }} />
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
    <div style={{ padding: '28px 32px' }}>
      {title && (
        <div style={{ marginBottom: 24 }}>
          <div className="skeleton-line" style={{ width: 200, height: 22, marginBottom: 8 }} />
          <div className="skeleton-line" style={{ width: 360, height: 12, opacity: 0.6 }} />
        </div>
      )}
      {filters && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 18 }}>
          {[140, 110, 120, 90].map((w, i) => (
            <div key={i} className="skeleton-rect" style={{ width: w, height: 34 }} />
          ))}
          <div className="skeleton-rect" style={{ marginLeft: 'auto', width: 130, height: 34 }} />
        </div>
      )}
      {/* Table header */}
      <div style={{ background: 'var(--surface-2)', borderRadius: 12, overflow: 'hidden',
        border: '1px solid var(--surface-3)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2.5fr 1.5fr 1fr 80px 100px 100px',
          gap: 16, padding: '10px 20px', borderBottom: '1px solid var(--surface-3)' }}>
          {['60%','45%','50%','70%','55%','45%'].map((w, i) => (
            <div key={i} className="skeleton-line" style={{ width: w, height: 10 }} />
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
    <div style={{ padding: '28px 32px' }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div className="skeleton-line" style={{ width: 180, height: 22, marginBottom: 8 }} />
          <div className="skeleton-line" style={{ width: 300, height: 12, opacity: 0.6 }} />
        </div>
        <div className="skeleton-rect" style={{ width: 140, height: 36 }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="skeleton-rect" style={{ height: 180, animationDelay: `${i * 0.04}s` }} />
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
    <div style={{ padding: '24px 28px' }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
        <div className="skeleton-line" style={{ width: 180, height: 22 }} />
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {[80, 80, 100].map((w, i) => <div key={i} className="skeleton-rect" style={{ width: w, height: 32 }} />)}
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', border: '1px solid var(--surface-3)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
        <div>
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} style={{ padding: '12px 16px', borderBottom: '1px solid var(--surface-3)', height: 44, display: 'flex', alignItems: 'center' }}>
              <div className="skeleton-line" style={{ width: `${50 + (i * 19) % 40}%`, animationDelay: `${i * 0.03}s` }} />
            </div>
          ))}
        </div>
        <div style={{ background: 'var(--surface-1)' }}>
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} style={{ padding: '12px 16px', borderBottom: '1px solid var(--surface-3)', height: 44, display: 'flex', alignItems: 'center', gap: 8 }}>
              <div className="skeleton-rect" style={{ marginLeft: `${(i * 37) % 45}%`, width: `${15 + (i * 23) % 35}%`, height: 20, animationDelay: `${i * 0.04}s` }} />
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
    <div style={{ padding: '20px 28px' }}>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center' }}>
        <div className="skeleton-line" style={{ width: 160, height: 22 }} />
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {[120, 90, 130].map((w, i) => <div key={i} className="skeleton-rect" style={{ width: w, height: 32 }} />)}
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton-rect" style={{ height: 80, animationDelay: `${i * 0.06}s` }} />
        ))}
      </div>
      <SkeletonTable title={false} filters={false} rows={8} />
    </div>
  )
}

/* ── Finance / analytics skeleton ────────────────────────────────────────── */
export function SkeletonFinance() {
  return (
    <div style={{ padding: '24px 32px' }}>
      <div className="u-mb-20">
        <div className="skeleton-line" style={{ width: 200, height: 22, marginBottom: 8 }} />
        <div className="skeleton-line" style={{ width: 340, height: 12, opacity: 0.6 }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton-rect" style={{ height: 92, animationDelay: `${i * 0.06}s` }} />
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 16 }}>
        <div className="skeleton-rect" style={{ height: 280 }} />
        <div className="skeleton-rect" style={{ height: 280, animationDelay: '0.2s' }} />
      </div>
    </div>
  )
}
