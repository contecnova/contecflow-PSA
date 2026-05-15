/**
 * TableControls.tsx
 * Reusable components and hook for sortable table headers and column filters.
 * Usage:
 *   const { sort, setSort, sortedData } = useSort(data, defaultKey)
 *   <SortableTH col="name" sort={sort} onSort={setSort}>Nombre</SortableTH>
 */
import { useState, useMemo, useCallback } from 'react'
import type { CSSProperties, ReactNode } from 'react'

export type SortDir = 'asc' | 'desc'

export interface SortState {
  key: string
  dir: SortDir
}

export interface UseSortResult<T> {
  sort: SortState
  setSort: (key: string) => void
  sortedData: T[]
}

// ── Hook ─────────────────────────────────────────────────────────────────────
export function useSort<T extends Record<string, unknown>>(
  data: T[] = [],
  defaultKey: string = '',
  defaultDir: SortDir = 'asc',
): UseSortResult<T> {
  const [sort, setSort] = useState<SortState>({ key: defaultKey, dir: defaultDir })

  const toggleSort = useCallback((key: string) => {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' }
    )
  }, [])

  const sortedData = useMemo<T[]>(() => {
    if (!sort.key || !Array.isArray(data)) return data
    return [...data].sort((a, b) => {
      let av: unknown = a[sort.key]
      let bv: unknown = b[sort.key]
      // handle nested e.g. "assignee.full_name"
      if (sort.key.includes('.')) {
        const parts = sort.key.split('.')
        av = parts.reduce<unknown>((o, k) => (o as Record<string, unknown> | null | undefined)?.[k], a)
        bv = parts.reduce<unknown>((o, k) => (o as Record<string, unknown> | null | undefined)?.[k], b)
      }
      if (av == null) return 1
      if (bv == null) return -1
      const cmp = typeof av === 'string'
        ? av.localeCompare(String(bv), undefined, { sensitivity: 'base' })
        : (av as number) < (bv as number) ? -1 : (av as number) > (bv as number) ? 1 : 0
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }, [data, sort.key, sort.dir])

  return { sort, setSort: toggleSort, sortedData }
}

export interface SortableTHProps {
  col: string
  sort?: SortState
  onSort: (col: string) => void
  children?: ReactNode
  style?: CSSProperties
  align?: 'left' | 'right'
}

// ── SortableTH ────────────────────────────────────────────────────────────────
export function SortableTH({ col, sort, onSort, children, style = {}, align = 'left' }: SortableTHProps) {
  const isActive = sort?.key === col
  const dir: SortDir = sort?.dir ?? 'asc'
  return (
    <button
      type="button"
      onClick={() => onSort(col)}
      aria-sort={isActive ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      aria-label={`${typeof children === 'string' ? children : col}, ordenar ${isActive ? (dir === 'asc' ? 'descendente' : 'ascendente') : 'ascendente'}`}
      style={{
        display: 'flex', alignItems: 'center', gap: 4,
        justifyContent: align === 'right' ? 'flex-end' : 'flex-start',
        cursor: 'pointer', userSelect: 'none',
        color: isActive ? 'var(--accent)' : 'var(--text-2)',
        fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.07em',
        transition: 'color 0.15s',
        background: 'none', border: 'none', padding: 0, fontFamily: 'inherit',
        ...style,
      }}
      onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.color = 'var(--text-1)' }}
      onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.color = 'var(--text-2)' }}
    >
      {children}
      <SortArrow active={isActive} dir={dir} />
    </button>
  )
}

interface SortArrowProps {
  active: boolean
  dir: SortDir
}

function SortArrow({ active, dir }: SortArrowProps) {
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

export type ViewName = 'list' | 'grid' | 'kanban' | 'gantt' | 'table' | string

export interface ViewToggleProps {
  view: ViewName
  onChange: (view: ViewName) => void
  views?: ViewName[]
}

// ── ViewToggle ────────────────────────────────────────────────────────────────
export function ViewToggle({ view, onChange, views = ['list', 'grid'] }: ViewToggleProps) {
  const icons: Record<string, { icon: string; label: string }> = {
    list:   { icon: '☰', label: 'Lista' },
    grid:   { icon: '⊞', label: 'Tarjetas' },
    kanban: { icon: '⧉', label: 'Kanban' },
    gantt:  { icon: '▬', label: 'Gantt' },
    table:  { icon: '⊟', label: 'Tabla' },
  }
  return (
    <div style={{ display: 'flex', border: '1px solid var(--surface-4)', borderRadius: 8, overflow: 'hidden' }}>
      {views.map((v) => {
        const def = icons[v] || { icon: v, label: v }
        const active = view === v
        return (
          <button key={v} onClick={() => onChange(v)} title={def.label}
            style={{
              padding: '6px 12px', background: active ? 'var(--accent-muted)' : 'transparent',
              border: 'none', borderRight: '1px solid var(--surface-4)',
              color: active ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 'var(--text-base)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600,
              transition: 'all 0.15s',
            }}>
            {def.icon} <span style={{ fontSize: 'var(--text-xs)', marginLeft: 3 }}>{def.label}</span>
          </button>
        )
      })}
    </div>
  )
}

export interface FilterSelectOption {
  value: string
  label: string
}

export interface FilterSelectProps {
  value: string
  onChange: (value: string) => void
  options: Array<FilterSelectOption | string>
  placeholder?: string
  style?: CSSProperties
}

// ── InlineFilter ──────────────────────────────────────────────────────────────
// A compact select that shows a colored indicator when active
export function FilterSelect({ value, onChange, options, placeholder, style = {} }: FilterSelectProps) {
  const active = Boolean(value)
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      style={{
        background: active ? 'var(--accent-muted)' : 'var(--surface-2)',
        border: `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}`,
        borderRadius: 8, padding: '8px 12px',
        color: active ? 'var(--accent)' : 'var(--text-1)',
        fontSize: 'var(--text-sm)', outline: 'none', fontFamily: 'inherit', cursor: 'pointer',
        fontWeight: active ? 600 : 400,
        ...style,
      }}>
      <option value="">{placeholder}</option>
      {options.map((o) => {
        const optValue = typeof o === 'string' ? o : o.value
        const optLabel = typeof o === 'string' ? o : (o.label ?? o.value)
        return (
          <option key={optValue} value={optValue}>
            {optLabel}
          </option>
        )
      })}
    </select>
  )
}

export interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  style?: CSSProperties
}

// ── SearchInput ───────────────────────────────────────────────────────────────
export function SearchInput({ value, onChange, placeholder = 'Buscar...', style = {} }: SearchInputProps) {
  return (
    <div style={{ position: 'relative', ...style }}>
      <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', fontSize: 'var(--text-base)', pointerEvents: 'none' }}>🔍</span>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width: '100%', background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '8px 12px 8px 32px',
          color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none', fontFamily: 'inherit',
          boxSizing: 'border-box',
        }} />
    </div>
  )
}

export interface ActiveFiltersProps {
  filters: Record<string, unknown>
  onClear: (key: string) => void
  onClearAll: () => void
}

// ── ActiveFilters ──────────────────────────────────────────────────────────────
// Shows chips of active filters with X to clear each
export function ActiveFilters({ filters, onClear, onClearAll }: ActiveFiltersProps) {
  const active = Object.entries(filters).filter(([, v]) => v)
  if (active.length === 0) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', fontWeight: 600 }}>Filtros:</span>
      {active.map(([key, val]) => (
        <span key={key} style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)',
          borderRadius: 20, padding: '2px 8px 2px 10px',
          fontSize: 'var(--text-xs)', color: 'var(--accent)', fontWeight: 600,
        }}>
          {String(val)}
          <button onClick={() => onClear(key)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', padding: '0 0 0 2px', fontSize: 'var(--text-base)', lineHeight: 1 }}>×</button>
        </span>
      ))}
      <button onClick={onClearAll} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', fontSize: 'var(--text-xs)', padding: '2px 6px', borderRadius: 20, textDecoration: 'underline' }}>
        Limpiar todo
      </button>
    </div>
  )
}
