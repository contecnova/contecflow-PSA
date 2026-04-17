import { CHART } from '../../constants/theme'
import React from 'react'
import { X } from 'lucide-react'

export {
  ClientSelect, UserSelect, ProjectSelect,
  SprintSelect, EpicSelect, ContractSelect,
  MilestoneSelect, TaskSelect,
  AssetSelect, LicenseSelect, VendorSelect,
  TicketSelect, ProblemSelect, SubcontractorSelect,
} from './EntitySelect'

export { useSort, SortableTH, ViewToggle, FilterSelect, SearchInput, ActiveFilters } from './TableControls'

// ── Badge ─────────────────────────────────────────────────────────────────────
/** Human-readable labels for common status/priority enum values. */
const BADGE_DISPLAY = {
  // Task / project statuses
  in_progress:  'In Progress',
  todo:         'To Do',
  backlog:      'Backlog',
  done:         'Done',
  blocked:      'Blocked',
  review:       'In Review',
  in_review:    'In Review',
  planning:     'Planning',
  active:       'Active',
  paused:       'Paused',
  closed:       'Closed',
  cancelled:    'Cancelled',
  on_hold:      'On Hold',
  // Priority
  low:          'Low',
  medium:       'Medium',
  high:         'High',
  critical:     'Critical',
  p1_critical:  'P1 Critical',
  p2_high:      'P2 High',
  p3_medium:    'P3 Medium',
  p4_low:       'P4 Low',
  // Deliverables
  planned:      'Planned',
  delivered:    'Delivered',
  accepted:     'Accepted',
  rejected:     'Rejected',
  // Approvals / expenses
  draft:        'Draft',
  submitted:    'Submitted',
  approved:     'Approved',
  pending:      'Pending',
  // Risk
  identified:   'Identified',
  analyzing:    'Analyzing',
  mitigating:   'Mitigating',
  monitoring:   'Monitoring',
  materialized: 'Materialized',
  // Service desk
  open:         'Open',
  new:          'New',
  resolved:     'Resolved',
  // Tickets support level
  l1: 'L1', l2: 'L2', l3: 'L3',
  // Boolean-like
  normal:       'Normal',
}

/** Convert snake_case to Title Case as fallback for unknown values. */
function humanize(str) {
  if (!str) return str
  return String(str).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function Badge({ label, display, _color }) {
  const presets = {
    low:         { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    medium:      { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    high:        { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    critical:    { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    p1_critical: { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    p2_high:     { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    p3_medium:   { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    p4_low:      { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    active:      { bg: 'var(--accent-muted)', text: 'var(--accent)', border: 'rgba(79,142,247,0.25)' },
    planning:    { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
    paused:      { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    closed:      { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    done:        { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    accepted:    { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    approved:    { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    cancelled:   { bg: 'var(--surface-3)',   text: 'var(--text-3)',   border: 'var(--surface-4)' },
    in_progress: { bg: 'var(--accent-muted)', text: 'var(--accent)', border: 'rgba(79,142,247,0.25)' },
    in_review:   { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    blocked:     { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    rejected:    { bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    materialized:{ bg: 'var(--danger-bg)',   text: 'var(--danger)',   border: 'var(--danger-border)' },
    review:      { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    todo:        { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
    backlog:     { bg: 'var(--surface-3)',   text: 'var(--text-3)',   border: 'var(--surface-4)' },
    draft:       { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
    submitted:   { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    pending:     { bg: 'var(--warning-bg)',  text: 'var(--warning)',  border: 'var(--warning-border)' },
    resolved:    { bg: 'var(--success-bg)',  text: 'var(--success)',  border: 'var(--success-border)' },
    normal:      { bg: 'var(--surface-3)',   text: 'var(--text-2)',   border: 'var(--surface-4)' },
  }
  const c = presets[label] || presets.normal
  const shown = display || BADGE_DISPLAY[label] || humanize(label)
  return (
    <span
      style={{
        fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 'var(--radius-full)',
        background: c.bg, color: c.text, border: `1px solid ${c.border}`,
        textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap',
        display: 'inline-block',
      }}
      aria-label={shown}
    >
      {shown}
    </span>
  )
}

// ── LoadBar ───────────────────────────────────────────────────────────────────
export function LoadBar({ value, max = 100, height = 5, label }) {
  const pct   = Math.min((value / max) * 100, 100)
  const color = value > max ? 'var(--danger)' : value / max > 0.85 ? 'var(--warning)' : 'var(--success)'
  return (
    <div role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={max}
      aria-label={label || `${Math.round(pct)}%`}
      style={{ background: 'var(--surface-4)', borderRadius: 'var(--radius-full)', height, overflow: 'hidden' }}>
      <div style={{
        width: `${pct}%`, height: '100%', background: color,
        borderRadius: 'var(--radius-full)', transition: 'width 0.5s ease',
      }} />
    </div>
  )
}

// ── Avatar ────────────────────────────────────────────────────────────────────
export function Avatar({ name = '', size = 34, url }) {
  const initials = name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()
  const palettes = [
    ['var(--accent)', 'rgba(26,58,110,0.8)'], ['var(--success)', 'rgba(15,70,50,0.8)'], ['var(--warning)', 'rgba(107,62,0,0.8)'],
    ['var(--danger)', 'rgba(92,26,26,0.9)'], ['var(--purple)', 'rgba(59,31,110,0.9)'], [CHART.sky, 'var(--surface-5)'],
  ]
  const [from, to] = palettes[name.charCodeAt(0) % palettes.length]
  return url ? (
    <img src={url} alt={name} style={{ width: size, height: size, borderRadius: '50%', objectFit: 'cover' }} />
  ) : (
    <div
      role="img"
      aria-label={name || 'Usuario'}
      style={{
      width: size, height: size, borderRadius: '50%', display: 'flex', flexShrink: 0,
      alignItems: 'center', justifyContent: 'center', fontSize: Math.round(size * 0.36),
      fontWeight: 700, background: `linear-gradient(145deg, ${from}, ${to})`,
      color: '#fff', letterSpacing: '0.02em',
    }}>
      {initials || '?'}
    </div>
  )
}

// ── Card ──────────────────────────────────────────────────────────────────────
export function Card({ children, style = {}, accent, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: 'var(--surface-2)',
        border: `1px solid ${accent ? 'rgba(79,142,247,0.25)' : 'var(--surface-4)'}`,
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-6)',
        boxShadow: accent ? 'var(--shadow-accent)' : 'none',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'border-color 0.15s, box-shadow 0.15s',
        ...style,
      }}
      onMouseEnter={onClick ? e => {
        e.currentTarget.style.borderColor = accent ? 'rgba(79,142,247,0.4)' : 'var(--surface-5)'
        e.currentTarget.style.boxShadow = 'var(--shadow-md)'
      } : undefined}
      onMouseLeave={onClick ? e => {
        e.currentTarget.style.borderColor = accent ? 'rgba(79,142,247,0.25)' : 'var(--surface-4)'
        e.currentTarget.style.boxShadow = accent ? 'var(--shadow-accent)' : 'none'
      } : undefined}
    >
      {children}
    </div>
  )
}

// ── KPI Card ──────────────────────────────────────────────────────────────────
export function KpiCard({ icon, label, value, sub, accent, danger, warning, trend }) {
  const valueColor = danger ? 'var(--danger)' : warning ? 'var(--warning)' : accent ? 'var(--accent)' : 'var(--text-1)'
  const trendColor = trend > 0 ? 'var(--success)' : trend < 0 ? 'var(--danger)' : 'var(--text-3)'
  return (
    <Card accent={accent} style={{ flex: 1, minWidth: 140 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-3)' }}>
        <div style={{ fontSize: 20 }}>{icon}</div>
        {trend !== undefined && (
          <span style={{ fontSize: 11, fontWeight: 600, color: trendColor }}>
            {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'} {Math.abs(trend)}%
          </span>
        )}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 26, fontWeight: 700,
        color: valueColor, letterSpacing: '-0.02em', lineHeight: 1, marginBottom: 6,
      }}>
        {value}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 500 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>{sub}</div>}
    </Card>
  )
}

// ── Button ────────────────────────────────────────────────────────────────────
export function Button({ children, onClick, variant = 'primary', size = 'md', disabled, loading, icon, style = {}, type }) {
  const variants = {
    primary:   {
      background: 'var(--accent)',
      color: '#fff',
      border: 'none',
      boxShadow: '0 1px 3px rgba(79,142,247,0.3)',
    },
    secondary: {
      background: 'var(--surface-3)',
      color: 'var(--text-1)',
      border: '1px solid var(--surface-4)',
    },
    danger:    {
      background: 'var(--danger-bg)',
      color: 'var(--danger)',
      border: '1px solid var(--danger-border)',
    },
    ghost:     {
      background: 'transparent',
      color: 'var(--accent)',
      border: '1px solid rgba(79,142,247,0.25)',
    },
    subtle:    {
      background: 'var(--accent-muted)',
      color: 'var(--accent)',
      border: '1px solid rgba(79,142,247,0.15)',
    },
  }
  const sizes = {
    xs: { fontSize: 11, padding: '4px 10px',  borderRadius: 'var(--radius-sm)', gap: 4 },
    sm: { fontSize: 12, padding: '6px 14px',  borderRadius: 'var(--radius-md)', gap: 5 },
    md: { fontSize: 13, padding: '8px 18px',  borderRadius: 'var(--radius-md)', gap: 6 },
    lg: { fontSize: 14, padding: '11px 24px', borderRadius: 'var(--radius-lg)', gap: 7 },
  }
  const v = variants[variant] || variants.primary
  const s = sizes[size] || sizes.md
  const isDisabled = disabled || loading

  return (
    <button
      type={type || 'button'}
      onClick={isDisabled ? undefined : onClick}
      aria-disabled={isDisabled || undefined}
      aria-busy={loading || undefined}
      disabled={isDisabled}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: s.gap,
        fontFamily: 'var(--font-sans)', fontWeight: 600,
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        opacity: isDisabled ? 0.5 : 1,
        transition: 'opacity 0.15s, transform 0.1s, background 0.15s',
        whiteSpace: 'nowrap',
        ...v, ...s, ...style,
      }}
      onMouseEnter={e => { if (!isDisabled) e.currentTarget.style.opacity = '0.85' }}
      onMouseLeave={e => { if (!isDisabled) e.currentTarget.style.opacity = '1' }}
      onMouseDown={e => { if (!isDisabled) e.currentTarget.style.transform = 'scale(0.97)' }}
      onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)' }}
    >
      {loading ? (
        <span style={{
          display: 'inline-block', width: 12, height: 12,
          border: '2px solid currentColor', borderTopColor: 'transparent',
          borderRadius: '50%', animation: 'spin 0.65s linear infinite',
        }} />
      ) : icon ? <span style={{ fontSize: '1em', lineHeight: 1 }}>{icon}</span> : null}
      {children}
    </button>
  )
}

// ── Input ─────────────────────────────────────────────────────────────────────
export function Input({ label, value, onChange, placeholder, type = 'text', required, style = {}, hint }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
      {label && (
        <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          {label}{required && <span style={{ color: 'var(--danger)' }}> *</span>}
        </label>
      )}
      <input
        type={type} value={value} onChange={onChange} placeholder={placeholder}
        style={{
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 'var(--radius-md)', padding: '9px 13px',
          color: 'var(--text-1)', fontSize: 13, outline: 'none',
          fontFamily: 'var(--font-sans)', width: '100%',
          transition: 'border-color 0.15s, box-shadow 0.15s',
        }}
        onFocus={e => {
          e.target.style.borderColor = 'rgba(79,142,247,0.5)'
          e.target.style.boxShadow = '0 0 0 3px rgba(79,142,247,0.08)'
        }}
        onBlur={e => {
          e.target.style.borderColor = 'var(--surface-4)'
          e.target.style.boxShadow = 'none'
        }}
      />
      {hint && <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{hint}</div>}
    </div>
  )
}

// ── Select ────────────────────────────────────────────────────────────────────
export function Select({ label, value, onChange, options = [], style = {} }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
      {label && (
        <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          {label}
        </label>
      )}
      <select
        value={value} onChange={onChange}
        style={{
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 'var(--radius-md)', padding: '9px 13px',
          color: value ? 'var(--text-1)' : 'var(--text-3)', fontSize: 13,
          outline: 'none', fontFamily: 'var(--font-sans)', cursor: 'pointer', width: '100%',
        }}
      >
        <option value="">Seleccionar...</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

// ── Spinner ───────────────────────────────────────────────────────────────────
export function Spinner({ size = 22, color = 'var(--accent)', label = 'Cargando...' }) {
  return (
    <div role="status" aria-label={label} style={{
      width: size, height: size, borderRadius: '50%',
      border: `2px solid var(--surface-4)`, borderTopColor: color,
      animation: 'spin 0.65s linear infinite', flexShrink: 0,
    }} />
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────
// ── Predefined SVG icons for empty states ────────────────────────────────────
const EMPTY_ICONS = {
  folder: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V7z"/>
    </svg>
  ),
  tasks: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="14" rx="2"/>
      <path d="M8 10h8M8 14h5"/>
    </svg>
  ),
  search: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>
    </svg>
  ),
  users: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="7" r="3"/><path d="M3 20c0-4 3-6 6-6s6 2 6 6"/>
      <circle cx="17" cy="8" r="2"/><path d="M21 20c0-3-1.5-5-4-5"/>
    </svg>
  ),
  docs: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"/><polyline points="14 2 14 8 20 8"/>
      <line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/>
    </svg>
  ),
  chart: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
    </svg>
  ),
  inbox: (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>
      <path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/>
    </svg>
  ),
}

export function EmptyState({ icon, svgIcon, title, description, action, ctaLabel, onCta }) {
  // svgIcon: explicit SVG node
  // icon: named key from EMPTY_ICONS dict, OR emoji/text string (backward-compat)
  const resolvedIcon = svgIcon
    ? svgIcon
    : (EMPTY_ICONS[icon] || (
        icon
          ? <span style={{ fontSize: 26 }}>{icon}</span>
          : <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01" strokeLinecap="round"/>
            </svg>
      ))

  return (
    <div className="empty-state">
      <div className="empty-state-icon">{resolvedIcon}</div>
      <div className="empty-state-title">{title}</div>
      {description && <div className="empty-state-desc">{description}</div>}
      {(action || (ctaLabel && onCta)) && (
        <div style={{ marginTop: 8 }}>
          {action || (
            <button className="btn-primary" onClick={onCta}
              style={{ fontSize: 13, padding: '8px 20px' }}>
              {ctaLabel}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Modal ─────────────────────────────────────────────────────────────────────
export function Modal({ open, onClose, title, children, width = 520, subtitle }) {
  const dialogRef = React.useRef(null)
  const onCloseRef = React.useRef(onClose)
  React.useEffect(() => { onCloseRef.current = onClose })

  // Focus trap: keep keyboard navigation inside the modal while open
  React.useEffect(() => {
    if (!open) return
    const el = dialogRef.current
    if (!el) return
    const focusable = el.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    const first = focusable[0]
    const last  = focusable[focusable.length - 1]
    const prev  = document.activeElement

    if (first) first.focus()

    const trap = (e) => {
      if (e.key !== 'Tab') return
      if (focusable.length === 0) { e.preventDefault(); return }
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus() }
      } else {
        if (document.activeElement === last)  { e.preventDefault(); first?.focus() }
      }
    }
    const esc = (e) => { if (e.key === 'Escape') onCloseRef.current() }

    el.addEventListener('keydown', trap)
    document.addEventListener('keydown', esc)
    return () => {
      el.removeEventListener('keydown', trap)
      document.removeEventListener('keydown', esc)
      prev?.focus()
    }
  }, [open])

  if (!open) return null
  return (
    <div
      onClick={onClose}
      role="presentation"
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(8,12,20,0.85)',
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 24,
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--surface-4)',
          borderRadius: 'var(--radius-xl)',
          width: '100%', maxWidth: width, maxHeight: '90vh', overflow: 'auto',
          padding: 28, animation: 'fadeUp 0.2s ease',
          boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 22 }}>
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-1)' }}>{title}</h2>
            {subtitle && <p style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 3 }}>{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="Cerrar"
            style={{
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 'var(--radius-sm)', color: 'var(--text-2)',
              cursor: 'pointer', width: 28, height: 28, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              flexShrink: 0, marginLeft: 12, marginTop: 2,
            }}
          ><X size={14} aria-hidden="true" /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── DataTable ─────────────────────────────────────────────────────────────────
export function DataTable({ columns, data = [], loading, emptyIcon = '○', emptyTitle = 'Sin datos', pageSize = 15 }) {
  const [sort, setSort] = React.useState({ col: null, dir: 'asc' })
  const [page, setPage] = React.useState(0)
  const [filter, setFilter] = React.useState('')

  const filtered = filter
    ? data.filter(row => Object.values(row).some(v => String(v || '').toLowerCase().includes(filter.toLowerCase())))
    : data
  const sorted = sort.col
    ? [...filtered].sort((a, b) => {
        const cmp = String(a[sort.col] || '').localeCompare(String(b[sort.col] || ''), undefined, { numeric: true })
        return sort.dir === 'asc' ? cmp : -cmp
      })
    : filtered
  const pages    = Math.max(1, Math.ceil(sorted.length / pageSize))
  const pageData = sorted.slice(page * pageSize, (page + 1) * pageSize)
  const toggleSort = (col) => setSort(s => s.col === col ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: 'asc' })

  const btnBase = {
    background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 'var(--radius-sm)', color: 'var(--text-1)',
    padding: '4px 10px', cursor: 'pointer', fontSize: 12, fontFamily: 'var(--font-sans)',
  }

  return (
    <div>
      {data.length > pageSize && (
        <div style={{ marginBottom: 12 }}>
          <input value={filter} onChange={e => { setFilter(e.target.value); setPage(0) }}
            placeholder="Filtrar..." style={{
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
              borderRadius: 'var(--radius-md)', padding: '7px 12px',
              color: 'var(--text-1)', fontSize: 12, outline: 'none',
              fontFamily: 'var(--font-sans)', width: 220,
            }} />
        </div>
      )}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
              {columns.map(col => (
                <th key={col.key} onClick={() => col.sortable !== false && toggleSort(col.key)}
                  style={{
                    textAlign: 'left', padding: '10px 14px', fontSize: 11, fontWeight: 600,
                    color: sort.col === col.key ? 'var(--accent)' : 'var(--text-2)',
                    textTransform: 'uppercase', letterSpacing: '0.07em', whiteSpace: 'nowrap',
                    cursor: col.sortable !== false ? 'pointer' : 'default',
                    userSelect: 'none',
                  }}>
                  {col.label}
                  {sort.col === col.key && <span style={{ marginLeft: 4, opacity: 0.7 }}>{sort.dir === 'asc' ? '↑' : '↓'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length} style={{ textAlign: 'center', padding: 32 }}>
                <div style={{ display: 'flex', justifyContent: 'center' }}><Spinner /></div>
              </td></tr>
            ) : pageData.length === 0 ? (
              <tr><td colSpan={columns.length}>
                <EmptyState icon={emptyIcon} title={emptyTitle} />
              </td></tr>
            ) : pageData.map((row, i) => (
              <tr key={row.id || i}
                style={{ borderBottom: '1px solid var(--surface-4)', transition: 'background 0.1s' }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                {columns.map(col => (
                  <td key={col.key} style={{ padding: '11px 14px', color: 'var(--text-1)', ...col.style }}>
                    {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'flex-end', marginTop: 14 }}>
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{sorted.length} registros</span>
          <button onClick={() => setPage(p => Math.max(0, p-1))} disabled={page === 0} style={{ ...btnBase, opacity: page === 0 ? 0.4 : 1, cursor: page === 0 ? 'not-allowed' : 'pointer' }}>‹</button>
          <span style={{ fontSize: 12, color: 'var(--text-2)', minWidth: 60, textAlign: 'center' }}>{page+1} / {pages}</span>
          <button onClick={() => setPage(p => Math.min(pages-1, p+1))} disabled={page === pages-1} style={{ ...btnBase, opacity: page === pages-1 ? 0.4 : 1, cursor: page === pages-1 ? 'not-allowed' : 'pointer' }}>›</button>
        </div>
      )}
    </div>
  )
}

// ── Table simple ──────────────────────────────────────────────────────────────
export function Table({ columns, data, onRowClick }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
            {columns.map(col => (
              <th key={col.key} style={{
                padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 600,
                color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', whiteSpace: 'nowrap',
              }}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} onClick={() => onRowClick?.(row)} style={{
              borderBottom: '1px solid var(--surface-4)',
              cursor: onRowClick ? 'pointer' : 'default', transition: 'background 0.1s',
            }}
              onMouseEnter={e => onRowClick && (e.currentTarget.style.background = 'var(--surface-3)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              {columns.map(col => (
                <td key={col.key} style={{ padding: '11px 14px', color: 'var(--text-1)' }}>
                  {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
