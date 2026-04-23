/**
 * TableControls.jsx
 * Reusable components and hook for sortable table headers and column filters.
 * Usage:
 *   const { sort, setSort, sortedData } = useSort(data, defaultKey)
 *   <SortableTH col="name" sort={sort} onSort={setSort}>Nombre</SortableTH>
 */
import { useState, useMemo, useCallback } from 'react'

// ── Hook ─────────────────────────────────────────────────────────────────────
export function useSort(data = [], defaultKey = '', defaultDir = 'asc') {
  const [sort, setSort] = useState({ key: defaultKey, dir: defaultDir })

  const toggleSort = useCallback((key) => {
    setSort(prev =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' }
    )
  }, [])

  const sortedData = useMemo(() => {
    if (!sort.key || !Array.isArray(data)) return data
    return [...data].sort((a, b) => {
      let av = a[sort.key]
      let bv = b[sort.key]
      // handle nested e.g. "assignee.full_name"
      if (sort.key.includes('.')) {
        const parts = sort.key.split('.')
        av = parts.reduce((o, k) => o?.[k], a)
        bv = parts.reduce((o, k) => o?.[k], b)
      }
      if (av == null) return 1
      if (bv == null) return -1
      const cmp = typeof av === 'string'
        ? av.localeCompare(bv, undefined, { sensitivity: 'base' })
        : av < bv ? -1 : av > bv ? 1 : 0
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }, [data, sort.key, sort.dir])

  return { sort, setSort: toggleSort, sortedData }
}

// ── SortableTH ────────────────────────────────────────────────────────────────
export function SortableTH({ col, sort, onSort, children, style = {}, align = 'left' }) {
  const isActive = sort?.key === col
  const dir = sort?.dir ?? 'asc'

  return (
    <button
      type="button"
      onClick={() => onSort(col)}
      style={{
        display: 'flex', alignItems: 'center', gap: 4,
        justifyContent: align === 'right' ? 'flex-end' : 'flex-start',
        cursor: 'pointer', userSelect: 'none',
        color: isActive ? 'var(--accent)' : 'var(--text-2)',
        fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em',
        transition: 'color 0.15s',
        background: 'none', border: 'none', padding: 0, fontFamily: 'inherit',
        ...style,
      }}
      onMouseEnter={e => { if (!isActive) e.currentTarget.style.color = 'var(--text-1)' }}
      onMouseLeave={e => { if (!isActive) e.currentTarget.style.color = 'var(--text-2)' }}
    >
      {children}
      <SortArrow active={isActive} dir={dir} />
    </button>
  )
}

function SortArrow({ active, dir }) {
  if (!active) return (
    <svg width="8" height="10" viewBox="0 0 8 10" fill="none" style={{ opacity: 0.3 }}>
      <path d="M4 0L7 3.5H1L4 0Z" fill="currentColor"/>
      <path d="M4 10L1 6.5H7L4 10Z" fill="currentColor"/>
    </svg>
  )
  if (dir === 'asc') return (
    <svg width="8" height="10" viewBox="0 0 8 10" fill="none">
      <path d="M4 0L7 3.5H1L4 0Z" fill="var(--accent)"/>
      <path d="M4 10L1 6.5H7L4 10Z" fill="var(--accent)" opacity="0.3"/>
    </svg>
  )
  return (
    <svg width="8" height="10" viewBox="0 0 8 10" fill="none">
      <path d="M4 0L7 3.5H1L4 0Z" fill="var(--accent)" opacity="0.3"/>
      <path d="M4 10L1 6.5H7L4 10Z" fill="var(--accent)"/>
    </svg>
  )
}

// ── ViewToggle ────────────────────────────────────────────────────────────────
export function ViewToggle({ view, onChange, views = ['list', 'grid'] }) {
  const icons = {
    list:   { icon: '☰', label: 'Lista' },
    grid:   { icon: '⊞', label: 'Tarjetas' },
    kanban: { icon: '⧉', label: 'Kanban' },
    gantt:  { icon: '▬', label: 'Gantt' },
    table:  { icon: '⊟', label: 'Tabla' },
  }
  return (
    <div style={{ display: 'flex', border: '1px solid #1e2d45', borderRadius: 8, overflow: 'hidden' }}>
      {views.map(v => {
        const def = icons[v] || { icon: v, label: v }
        const active = view === v
        return (
          <button key={v} onClick={() => onChange(v)} title={def.label}
            style={{
              padding: '6px 12px', background: active ? 'var(--accent-muted)' : 'transparent',
              border: 'none', borderRight: '1px solid #1e2d45',
              color: active ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600,
              transition: 'all 0.15s',
            }}>
            {def.icon} <span style={{ fontSize: 11, marginLeft: 3 }}>{def.label}</span>
          </button>
        )
      })}
    </div>
  )
}

// ── InlineFilter ──────────────────────────────────────────────────────────────
// A compact select that shows a colored indicator when active
export function FilterSelect({ value, onChange, options, placeholder, style = {} }) {
  const active = Boolean(value)
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      style={{
        background: active ? 'var(--accent-muted)' : 'var(--surface-2)',
        border: `1px solid ${active ? 'var(--accent-glow)' : '#1e2d45'}`,
        borderRadius: 8, padding: '8px 12px',
        color: active ? 'var(--accent)' : 'var(--text-1)',
        fontSize: 12, outline: 'none', fontFamily: 'inherit', cursor: 'pointer',
        fontWeight: active ? 600 : 400,
        ...style,
      }}>
      <option value="">{placeholder}</option>
      {options.map(o => (
        <option key={o.value ?? o} value={o.value ?? o}>
          {o.label ?? o}
        </option>
      ))}
    </select>
  )
}

// ── SearchInput ───────────────────────────────────────────────────────────────
export function SearchInput({ value, onChange, placeholder = 'Buscar...', style = {} }) {
  return (
    <div style={{ position: 'relative', ...style }}>
      <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', fontSize: 13, pointerEvents: 'none' }}>🔍</span>
      <input value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width: '100%', background: 'var(--surface-2)', border: '1px solid #1e2d45',
          borderRadius: 8, padding: '8px 12px 8px 32px',
          color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit',
          boxSizing: 'border-box',
        }} />
    </div>
  )
}

// ── ActiveFilters ──────────────────────────────────────────────────────────────
// Shows chips of active filters with X to clear each
export function ActiveFilters({ filters, onClear, onClearAll }) {
  const active = Object.entries(filters).filter(([, v]) => v)
  if (active.length === 0) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
      <span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>Filtros:</span>
      {active.map(([key, val]) => (
        <span key={key} style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)',
          borderRadius: 20, padding: '2px 8px 2px 10px',
          fontSize: 11, color: 'var(--accent)', fontWeight: 600,
        }}>
          {val}
          <button onClick={() => onClear(key)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', padding: '0 0 0 2px', fontSize: 13, lineHeight: 1 }}>×</button>
        </span>
      ))}
      <button onClick={onClearAll} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', fontSize: 11, padding: '2px 6px', borderRadius: 20, textDecoration: 'underline' }}>
        Limpiar todo
      </button>
    </div>
  )
}
