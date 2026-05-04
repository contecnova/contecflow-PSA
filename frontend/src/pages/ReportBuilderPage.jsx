/**
 * ReportBuilderPage — No-code parametric report builder
 *
 * Left panel : entity picker (grouped) + column checkboxes (searchable) + filters + sort
 * Right panel: live preview table + export button + save template
 */

import { useState, useCallback, useMemo, useRef } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reportBuilderApi, biReportBuilderV2Api } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BarChart2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width: '100%', background: 'var(--surface-4)', border: '1px solid var(--surface-5)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const EMPTY_FILTER = { column: '', operator: 'eq', value: '' }
const NULL_OPS = new Set(['is_null', 'is_not_null'])

function useSchema() {
  return useQuery({
    queryKey: ['report-schema'],
    queryFn: () => reportBuilderApi.schema().then(r => r.data),
    staleTime: Infinity,
  })
}

// ── Entity picker grouped by category ────────────────────────────────────
function EntityPicker({ entities, groups, value, onChange }) {
  // Build { groupKey: [{ key, label }] }
  const byGroup = useMemo(() => {
    const map = {}
    Object.entries(entities).forEach(([k, e]) => {
      const g = e.group || 'otros'
      if (!map[g]) map[g] = []
      map[g].push({ key: k, label: e.label })
    })
    return map
  }, [entities])

  const groupOrder = Object.keys(groups || {})
  const sortedGroups = [
    ...groupOrder.filter(g => byGroup[g]),
    ...Object.keys(byGroup).filter(g => !groupOrder.includes(g)),
  ]

  return (
    <select value={value} onChange={onChange} style={fs}>
      <option value="">Selecciona entidad…</option>
      {sortedGroups.map(gk => (
        <optgroup key={gk} label={groups?.[gk] || gk}>
          {(byGroup[gk] || []).map(({ key, label }) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}

// ── Column panel with search + select-all + drag-to-reorder ──────────────────
function ColumnPanel({ entityDef, selected, onToggle, onSelectAll, onDeselectAll, onReorder }) {
  const [search, setSearch] = useState('')
  const cols = useMemo(() => entityDef?.columns || {}, [entityDef])
  const dragItem = useRef(null)
  const dragOver = useRef(null)

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    return Object.entries(cols).filter(([, col]) =>
      !q || col.label.toLowerCase().includes(q)
    )
  }, [cols, search])

  const _allVisible = filtered.every(([k]) => selected.includes(k))

  // Drag-to-reorder selected columns
  const handleDragStart = (e, idx) => {
    dragItem.current = idx
    e.dataTransfer.effectAllowed = 'move'
  }
  const handleDragOver = (e, idx) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    dragOver.current = idx
  }
  const handleDrop = () => {
    if (dragItem.current === null || dragOver.current === null) return
    if (dragItem.current === dragOver.current) return
    const reordered = [...selected]
    const [dragged] = reordered.splice(dragItem.current, 1)
    reordered.splice(dragOver.current, 0, dragged)
    onReorder(reordered)
    dragItem.current = null
    dragOver.current = null
  }

  return (
    <div>
      {/* Search box */}
      <div style={{ position: 'relative', marginBottom: 8 }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Buscar campos..."
          style={{ ...fs, paddingLeft: 28, fontSize: "var(--text-sm)" }}
        />
        <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-2)', fontSize: "var(--text-base)" }}>🔍</span>
        {search && (
          <button
            onClick={() => setSearch('')}
            style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-base)" }}>✕</button>
        )}
      </div>

      {/* Select all / none */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
        <button onClick={onSelectAll}
          style={{ background: 'none', border: 'none', color: 'var(--info)', fontSize: "var(--text-xs)", cursor: 'pointer', padding: 0, fontFamily: 'inherit' }}>
          Seleccionar todos
        </button>
        <span style={{ color: 'var(--surface-5)', fontSize: "var(--text-xs)" }}>·</span>
        <button onClick={onDeselectAll}
          style={{ background: 'none', border: 'none', color: 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', padding: 0, fontFamily: 'inherit' }}>
          Limpiar
        </button>
        <span style={{ marginLeft: 'auto', fontSize: "var(--text-xs)", color: 'var(--surface-5)' }}>
          {selected.length}/{Object.keys(cols).length}
        </span>
      </div>

      {/* Column list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 220, overflowY: 'auto', paddingRight: 2 }}>
        {filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: 12, color: 'var(--surface-5)', fontSize: "var(--text-sm)" }}>Sin resultados</div>
        )}
        {filtered.map(([key, col]) => (
          <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '3px 4px', borderRadius: 4, background: selected.includes(key) ? 'var(--accent-muted)' : 'transparent' }}>
            <input
              type="checkbox"
              checked={selected.includes(key)}
              onChange={() => onToggle(key)}
              style={{ accentColor: 'var(--info)', width: 13, height: 13, flexShrink: 0 }}
            />
            <span style={{ fontSize: "var(--text-sm)", color: selected.includes(key) ? 'var(--text-1)' : 'var(--text-2)', flex: 1 }}>{col.label}</span>
            <span style={{ fontSize: "var(--text-3xs)", color: 'var(--surface-5)', background: 'var(--surface-4)', borderRadius: 3, padding: '1px 4px', flexShrink: 0 }}>{col.type}</span>
          </label>
        ))}
      </div>

      {/* Drag-to-reorder selected columns */}
      {selected.length > 1 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--surface-5)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
            Orden de columnas (arrastra para reordenar)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {selected.map((key, idx) => (
              <div
                key={key}
                draggable
                role="button"
                tabIndex={0}
                onDragStart={e => handleDragStart(e, idx)}
                onDragOver={e => handleDragOver(e, idx)}
                onDrop={handleDrop}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowUp' && idx > 0) {
                    e.preventDefault()
                    const reordered = [...selected]
                    ;[reordered[idx - 1], reordered[idx]] = [reordered[idx], reordered[idx - 1]]
                    onReorder(reordered)
                  }
                  if (e.key === 'ArrowDown' && idx < selected.length - 1) {
                    e.preventDefault()
                    const reordered = [...selected]
                    ;[reordered[idx], reordered[idx + 1]] = [reordered[idx + 1], reordered[idx]]
                    onReorder(reordered)
                  }
                }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  background: 'var(--surface-4)', border: '1px solid var(--surface-5)',
                  borderRadius: 5, padding: '4px 8px', cursor: 'grab',
                  fontSize: "var(--text-xs)", color: 'var(--text-1)',
                  userSelect: 'none',
                }}
              >
                <span style={{ color: 'var(--surface-5)', fontSize: "var(--text-sm)" }}>⠿</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cols[key]?.label || key}</span>
                <span style={{ fontSize: "var(--text-2xs)", color: 'var(--surface-5)' }}>{idx + 1}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Filter row ─────────────────────────────────────────────────────────────
function FilterRow({ filter, index, entityDef, operators, onChange, onRemove }) {
  const cols = entityDef?.columns || {}
  const set = (k) => (e) => onChange(index, { ...filter, [k]: e.target.value })
  const needsValue = !NULL_OPS.has(filter.operator)
  return (
    <div style={{ display: 'flex', gap: 5, alignItems: 'center', marginBottom: 5 }}>
      <select value={filter.column} onChange={set('column')} style={{ ...fs, flex: '0 0 120px', fontSize: "var(--text-xs)" }}>
        <option value="">Campo…</option>
        {Object.entries(cols).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
      </select>
      <select value={filter.operator} onChange={set('operator')} style={{ ...fs, flex: '0 0 110px', fontSize: "var(--text-xs)" }}>
        {Object.entries(operators || {}).map(([k, o]) => <option key={k} value={k}>{o.label}</option>)}
      </select>
      {needsValue ? (
        <input
          value={filter.value}
          onChange={set('value')}
          placeholder="Valor del filtro..."
          style={{ ...fs, flex: 1, fontSize: "var(--text-xs)" }}
        />
      ) : (
        <div style={{ flex: 1 }} />
      )}
      <button onClick={() => onRemove(index)}
        style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-md)", flexShrink: 0 }}>✕</button>
    </div>
  )
}

// ── Preview table ──────────────────────────────────────────────────────────
function PreviewTable({ rows, columns, entityDef }) {
  const colDef = entityDef?.columns || {}
  if (!rows || rows.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 48, color: 'var(--surface-5)', fontSize: "var(--text-base)" }}>
        Configura la consulta y pulsa <strong style={{ color: 'var(--info)' }}>Previsualizar</strong>
      </div>
    )
  }
  const cellBase = { padding: '7px 10px', fontSize: "var(--text-sm)", borderBottom: '1px solid var(--surface-4)', color: 'var(--text-1)', whiteSpace: 'nowrap' }
  const thStyle  = { ...cellBase, fontWeight: 700, fontSize: "var(--text-2xs)", color: 'var(--text-2)', textTransform: 'uppercase', background: 'var(--surface-2)' }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {columns.map(c => <th key={c} style={thStyle}>{colDef[c]?.label || c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-4)'}
              onMouseLeave={e => e.currentTarget.style.background = ''}>
              {columns.map(c => (
                <td key={c} style={cellBase}>
                  {row[c] === null || row[c] === undefined ? <span style={{ color: 'var(--surface-5)' }}>—</span> :
                   typeof row[c] === 'boolean' ? (row[c] ? '✔' : '✘') :
                   String(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── BI presets tab (Report Builder v2) ─────────────────────────────────────
function BiPresetsTab() {
  const [selected, setSelected] = useState('finance_revenue_by_client')
  const [previewData, setPreview] = useState(null)
  const { data: presets } = useQuery({
    queryKey: ['rbv2-presets'],
    queryFn: () => biReportBuilderV2Api.listPresets({ grouped: false }).then(r => r.data).catch(() => ({ items: [] })),
    staleTime: 60_000,
  })
  const items = presets?.items || []

  async function runPreview() {
    try { const res = await biReportBuilderV2Api.preview(selected, 10); setPreview(res.data) } catch (_) { /* ignore */ }
  }
  async function exportJson() {
    try {
      const res = await biReportBuilderV2Api.export(selected, 'json')
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = res.data.filename || 'report.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch (_) { /* ignore */ }
  }

  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: '1rem' }}>Presets BI</span>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{items.length} presets disponibles</span>
      </div>
      <div style={{ padding: '18px 20px' }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
          {items.slice(0, 16).map(p => (
            <button key={p.id} onClick={() => setSelected(p.id)}
              style={{
                padding: '5px 14px', borderRadius: 20, fontSize: 'var(--text-xs)', cursor: 'pointer', fontFamily: 'inherit',
                border: `1.5px solid ${selected === p.id ? 'var(--accent)' : 'var(--surface-4)'}`,
                background: selected === p.id ? 'var(--accent-muted)' : 'transparent',
                color: selected === p.id ? 'var(--accent)' : 'var(--text-2)',
                fontWeight: selected === p.id ? 700 : 400,
              }}>
              {p.name}
            </button>
          ))}
          {items.length > 16 && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', alignSelf: 'center' }}>+{items.length - 16} más</span>}
        </div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
          <button onClick={runPreview}
            style={{ padding: '7px 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' }}>
            Vista previa
          </button>
          <button onClick={exportJson}
            style={{ padding: '7px 16px', borderRadius: 8, background: 'var(--success)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit' }}>
            Exportar JSON
          </button>
        </div>
        {previewData && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
              <thead>
                <tr style={{ background: 'var(--surface-3)' }}>
                  {(previewData.columns || []).map(c => (
                    <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-2)', fontWeight: 700, fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--surface-4)' }}>{c.replace(/_/g, ' ')}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(previewData.rows || []).map((row, ri) => (
                  <tr key={ri} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                    {(previewData.columns || []).map(c => <td key={c} style={{ padding: '8px 12px', color: 'var(--text-1)' }}>{row[c] ?? '—'}</td>)}
                  </tr>
                ))}
                {!(previewData.rows || []).length && (
                  <tr><td colSpan={(previewData.columns || []).length || 1} style={{ padding: 16, textAlign: 'center', color: 'var(--text-3)' }}>Sin datos para este preset</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function ReportBuilderPage() {
  const t = useAppT()
  const { data: schema } = useSchema()
  const qc = useQueryClient()

  const [entity,    setEntity]    = useState('')
  const [columns,   setColumns]   = useState([])
  const [filters,   setFilters]   = useState([])
  const [sort,      setSort]      = useState({ column: '', direction: 'asc' })
  const [preview,   setPreview]   = useState(null)
  const [loading,   setLoading]   = useState(false)
  const [tplName,   setTplName]   = useState('')
  const [savingTpl, setSavingTpl] = useState(false)
  const [activeTab, setTab]       = useState('builder')

  const entities  = schema?.entities  || {}
  const operators = schema?.operators || {}
  const groups    = schema?.groups    || {}
  const entityDef = entity ? entities[entity] : null

  const toggleColumn = useCallback((col) => {
    setColumns(prev => prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col])
  }, [])

  const selectAllColumns = useCallback(() => {
    setColumns(Object.keys(entityDef?.columns || {}))
  }, [entityDef])

  const deselectAllColumns = useCallback(() => setColumns([]), [])

  const reorderColumns = useCallback((newOrder) => setColumns(newOrder), [])

  const changeEntity = (e) => {
    setEntity(e.target.value)
    setColumns([])
    setFilters([])
    setSort({ column: '', direction: 'asc' })
    setPreview(null)
  }

  const addFilter    = () => setFilters(f => [...f, { ...EMPTY_FILTER }])
  const changeFilter = (i, val) => setFilters(f => f.map((x, idx) => idx === i ? val : x))
  const removeFilter = (i) => setFilters(f => f.filter((_, idx) => idx !== i))

  const buildQuery = () => ({
    entity,
    columns: columns.length > 0 ? columns : Object.keys(entityDef?.columns || {}),
    filters: filters.filter(f => f.column && f.operator),
    sort: sort.column ? sort : null,
    limit: 500,
  })

  const runPreview = async () => {
    if (!entity) return
    setLoading(true)
    try {
      const res = await reportBuilderApi.preview(buildQuery())
      setPreview(res.data)
    } catch {
      setPreview({ rows: [], count: 0, error: true })
    } finally {
      setLoading(false)
    }
  }

  const exportCSV = async () => {
    if (!entity) return
    const q = buildQuery()
    const res = await reportBuilderApi.export(q, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${entity}_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const saveTemplate = async () => {
    if (!tplName.trim() || !entity) return
    setSavingTpl(true)
    try {
      await reportBuilderApi.saveTemplate({ name: tplName.trim(), query: buildQuery() })
      await qc.invalidateQueries(['report-templates'])
      setTplName('')
    } finally {
      setSavingTpl(false)
    }
  }

  const { data: templates = [] } = useQuery({
    queryKey: ['report-templates'],
    queryFn: () => reportBuilderApi.templates().then(r => r.data),
  })

  const { mutate: deleteTpl } = useMutation({
    mutationFn: (id) => reportBuilderApi.deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries(['report-templates']),
  })

  const loadTemplate = (tpl) => {
    const q = tpl.query
    setEntity(q.entity)
    setColumns(q.columns || [])
    setFilters(q.filters || [])
    setSort(q.sort || { column: '', direction: 'asc' })
    setPreview(null)
    setTab('builder')
  }

  const resolvedColumns = columns.length > 0 ? columns : Object.keys(entityDef?.columns || {})

  return (
    <PageShell style={{ maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('report_builder.title')}
        subtitle={t('report_builder.subtitle')}
      />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {['builder', 'templates', 'presets'].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: activeTab === t ? 'var(--accent-glow)' : 'none',
            border: `1px solid ${activeTab === t ? 'var(--info)' : 'var(--surface-5)'}`,
            borderRadius: 8, padding: '6px 16px',
            color: activeTab === t ? 'var(--info)' : 'var(--text-2)',
            cursor: 'pointer', fontSize: "var(--text-base)", fontFamily: 'inherit',
          }}>
            {t === 'builder' ? '🔧 Constructor'
              : t === 'templates' ? `📁 Plantillas (${templates.length})`
              : '⚡ Presets BI'}
          </button>
        ))}
      </div>

      {activeTab === 'presets' ? (
        <BiPresetsTab />
      ) : activeTab === 'templates' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {templates.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 48, color: 'var(--surface-5)', fontSize: "var(--text-md)" }}>
              No hay plantillas guardadas. Crea un informe y guárdalo.
            </div>
          ) : templates.map(t => (
            <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 12, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 16px' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "var(--text-md)", color: 'var(--text-1)', fontWeight: 600 }}>{t.name}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>
                  {entities[t.query?.entity]?.label || t.query?.entity}
                  {' · '}{(t.query?.columns || []).length} columnas
                  {' · '}{(t.query?.filters || []).length} filtros
                </div>
              </div>
              <button onClick={() => loadTemplate(t)}
                style={{ background: 'var(--accent-glow)', border: 'none', borderRadius: 6, color: 'var(--info)', padding: '6px 14px', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
                Cargar
              </button>
              <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar plantilla?', onConfirm: () => deleteTpl(t.id), danger: true }) }}
                style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
                Eliminar
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20, alignItems: 'start' }}>
          {/* ── Left panel ── */}
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 18, display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* Entity selector */}
            <div>
              <label style={ls}>Entidad de datos</label>
              <EntityPicker entities={entities} groups={groups} value={entity} onChange={changeEntity} />
              {entityDef && (
                <div style={{ marginTop: 6, fontSize: "var(--text-xs)", color: 'var(--surface-5)' }}>
                  {Object.keys(entityDef.columns).length} campos disponibles
                </div>
              )}
            </div>

            {entityDef && (
              <>
                {/* Column selector */}
                <div>
                  <label style={ls}>Campos a incluir</label>
                  <ColumnPanel
                    entityDef={entityDef}
                    selected={columns}
                    onToggle={toggleColumn}
                    onSelectAll={selectAllColumns}
                    onDeselectAll={deselectAllColumns}
                    onReorder={reorderColumns}
                  />
                </div>

                {/* Filters */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <label style={{ ...ls, marginBottom: 0 }}>Filtros</label>
                    <button onClick={addFilter}
                      style={{ background: 'none', border: 'none', color: 'var(--info)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
                      + Añadir
                    </button>
                  </div>
                  {filters.length === 0 && (
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--surface-5)', textAlign: 'center', padding: '6px 0' }}>Sin filtros</div>
                  )}
                  {filters.map((f, i) => (
                    <FilterRow key={i} filter={f} index={i} entityDef={entityDef}
                      operators={operators} onChange={changeFilter} onRemove={removeFilter} />
                  ))}
                </div>

                {/* Sort */}
                <div>
                  <label style={ls}>Ordenar por</label>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <select
                      value={sort.column}
                      onChange={e => setSort(s => ({ ...s, column: e.target.value }))}
                      style={{ ...fs, flex: 1, fontSize: "var(--text-sm)" }}>
                      <option value="">Sin orden</option>
                      {Object.entries(entityDef.columns).map(([k, c]) =>
                        <option key={k} value={k}>{c.label}</option>
                      )}
                    </select>
                    <select
                      value={sort.direction}
                      onChange={e => setSort(s => ({ ...s, direction: e.target.value }))}
                      style={{ ...fs, width: 72, fontSize: "var(--text-sm)" }}>
                      <option value="asc">↑ Asc</option>
                      <option value="desc">↓ Desc</option>
                    </select>
                  </div>
                </div>
              </>
            )}

            <button
              onClick={runPreview}
              disabled={!entity || loading}
              style={{
                background: entity ? 'var(--accent)' : 'var(--surface-4)',
                border: 'none', borderRadius: 8,
                color: entity ? 'var(--info)' : 'var(--surface-5)',
                padding: '10px 0', cursor: entity ? 'pointer' : 'not-allowed',
                fontWeight: 700, fontSize: "var(--text-base)", fontFamily: 'inherit',
                transition: 'opacity 0.15s',
              }}>
              {loading ? 'Consultando…' : '▶ Previsualizar'}
            </button>
          </div>

          {/* ── Right panel ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* Toolbar */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              {preview && (
                <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', flex: 1, minWidth: 120 }}>
                  {preview.count} fila{preview.count !== 1 ? 's' : ''}
                  {preview.truncated ? ' (máx. 500 en previsualización)' : ''}
                  {preview.error ? ' — error en la consulta' : ''}
                </span>
              )}
              <button
                onClick={exportCSV}
                disabled={!entity}
                style={{
                  background: entity ? 'var(--success-bg)' : 'var(--surface-4)',
                  border: `1px solid ${entity ? 'var(--success-border)' : 'var(--surface-4)'}`, borderRadius: 8,
                  color: entity ? 'var(--success)' : 'var(--text-3)',
                  padding: '8px 16px', cursor: entity ? 'pointer' : 'not-allowed',
                  fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit',
                }}>
                ⬇ Exportar CSV
              </button>
              <input
                value={tplName}
                onChange={e => setTplName(e.target.value)}
                placeholder="Nombre de la plantilla..."
                style={{ ...fs, width: 190 }}
              />
              <button
                onClick={saveTemplate}
                disabled={!tplName.trim() || !entity || savingTpl}
                style={{
                  background: tplName.trim() && entity ? 'var(--accent)' : 'var(--surface-4)',
                  border: 'none', borderRadius: 8,
                  color: tplName.trim() && entity ? 'var(--info)' : 'var(--surface-5)',
                  padding: '8px 14px', cursor: 'pointer',
                  fontSize: "var(--text-sm)", fontFamily: 'inherit', whiteSpace: 'nowrap',
                }}>
                {savingTpl ? 'Guardando…' : '💾 Guardar plantilla'}
              </button>
            </div>

            {/* Preview table */}
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, overflow: 'hidden', minHeight: 200 }}>
              <PreviewTable rows={preview?.rows} columns={resolvedColumns} entityDef={entityDef} />
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}

