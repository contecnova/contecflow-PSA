/**
 * TableControls.tsx
 * Reusable components and hook for sortable table headers and column filters.
 * Usage:
 *   const { sort, setSort, sortedData } = useSort(data, defaultKey)
 *   <SortableTH col="name" sort={sort} onSort={setSort}>Nombre</SortableTH>
 */
import { useState, useMemo, useCallback } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import './TableControls.css'
import { useTextoUi } from './useTextoUi'

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

/** Valor de una clave en una fila cualquiera (la fila es generica). */
function campo(fila: unknown, clave: string): unknown {
  return fila && typeof fila === 'object' ? (fila as Record<string, unknown>)[clave] : undefined
}

// ── Hook ─────────────────────────────────────────────────────────────────────
// Auditoria 2026-11 (#39): exigia `T extends Record<string, unknown>` y las
// interfaces del dominio no tienen indice implicito, asi que cada pantalla
// pasaba los datos con `as unknown as Record<...>[]` y los recuperaba con otro
// cast. La fila es generica; el acceso dinamico por clave se resuelve aqui.
export function useSort<T>(
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
      let av: unknown = campo(a, sort.key)
      let bv: unknown = campo(b, sort.key)
      // handle nested e.g. "assignee.full_name"
      if (sort.key.includes('.')) {
        const parts = sort.key.split('.')
        av = parts.reduce<unknown>((o, k) => campo(o, k), a)
        bv = parts.reduce<unknown>((o, k) => campo(o, k), b)
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

/**
 * Valor de `aria-sort` para la cabecera `<th>` que envuelve a `SortableTH`.
 * Auditoria 2026-11 (#45): aria-sort solo vale en columnheader/rowheader; en el
 * <button> era invalido y los lectores lo ignoraban. Va en la <th>.
 */
export function ariaSort(sort: SortState | undefined, col: string): 'ascending' | 'descending' | 'none' {
  return sort?.key === col ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'
}

// ── SortableTH ────────────────────────────────────────────────────────────────
// Es el BOTON de ordenar; si la tabla es una <table>, envuelvelo en
// <th aria-sort={ariaSort(sort, col)}>. En las tablas hechas con <div> en grid no
// hay cabecera de columna a la que ponerselo: el estado va en el aria-label.
export function SortableTH({ col, sort, onSort, children, style = {}, align = 'left' }: SortableTHProps) {
  const isActive = sort?.key === col
  const dir: SortDir = sort?.dir ?? 'asc'
  const t = useTextoUi()
  const nombre = typeof children === 'string' ? children : col
  // Estado actual (solo si esta columna ordena) y lo que hará el clic.
  const estado = isActive ? t(dir === 'asc' ? 'uikit.orden_actual_asc' : 'uikit.orden_actual_desc') : ''
  const accion = t(isActive && dir === 'asc' ? 'uikit.ordenar_desc' : 'uikit.ordenar_asc')
  const etiqueta = estado ? `${nombre}, ${estado}; ${accion}` : `${nombre}, ${accion}`
  return (
    <button
      type="button"
      onClick={() => onSort(col)}
      aria-label={etiqueta}
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
    <svg width="8" height="10" viewBox="0 0 8 10" fill="none" className="uitablcont-box-1">
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
  const t = useTextoUi()
  const icons: Record<string, { icon: string; label: string }> = {
    list:   { icon: '☰', label: t('uikit.vista_lista') },
    grid:   { icon: '⊞', label: t('uikit.vista_tarjetas') },
    kanban: { icon: '⧉', label: t('uikit.vista_kanban') },
    gantt:  { icon: '▬', label: t('uikit.vista_gantt') },
    table:  { icon: '⊟', label: t('uikit.vista_tabla') },
  }
  return (
    <div className="uitablcont-row-1">
      {views.map((v) => {
        const def = icons[v] || { icon: v, label: v }
        const active = view === v
        return (
          <button type="button" aria-pressed={active} className={`uitablcont-box-7 ${active ? 'table-controls-m1' : 'table-controls-m2'}`} key={v} onClick={() => onChange(v)} title={def.label}>
            {def.icon} <span className="uitablcont-box-2">{def.label}</span>
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
export function SearchInput({ value, onChange, placeholder: placeholderProp, style = {} }: SearchInputProps) {
  const t = useTextoUi()
  const placeholder = placeholderProp ?? t('uikit.buscar')
  return (
    <div style={{ position: 'relative', ...style }}>
      <span className="uitablcont-box-3">🔍</span>
      <input value={value} onChange={(e) => onChange(e.target.value)}
        aria-label={placeholder}
        placeholder={placeholder}
        className="uitablcont-box-4" />
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
  const t = useTextoUi()
  const active = Object.entries(filters).filter(([, v]) => v)
  if (active.length === 0) return null
  return (
    <div className="uitablcont-row-2">
      <span className="uitablcont-txt-1">{t('uikit.filtros')}</span>
      {active.map(([key, val]) => (
        <span key={key} className="uitablcont-row-3">
          {String(val)}
          <button type="button" onClick={() => onClear(key)} className="uitablcont-box-5" aria-label={t('uikit.quitar_filtro', { valor: String(val) })}>×</button>
        </span>
      ))}
      <button type="button" onClick={onClearAll} className="uitablcont-box-6">
        {t('uikit.limpiar_todo')}
      </button>
    </div>
  )
}
