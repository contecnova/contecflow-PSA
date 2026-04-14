/**
 * ReportBuilderPage — No-code parametric report builder
 *
 * Left panel : entity picker (grouped) + column checkboxes (searchable) + filters + sort
 * Right panel: live preview table + export button + save template
 */

import { useState, useCallback, useMemo } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width: '100%', background: '#2d3748', border: '1px solid #4a5568', borderRadius: 8, padding: '8px 12px', color: '#e2e8f0', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: '#718096', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const EMPTY_FILTER = { column: '', operator: 'eq', value: '' }
const NULL_OPS = new Set(['is_null', 'is_not_null'])

function useSchema() {
  return useQuery({
    queryKey: ['report-schema'],
    queryFn: () => api.get('/reports/schema').then(r => r.data),
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

// ── Column panel with search + select-all ─────────────────────────────────
function ColumnPanel({ entityDef, selected, onToggle, onSelectAll, onDeselectAll }) {
  const [search, setSearch] = useState('')
  const cols = useMemo(() => entityDef?.columns || {}, [entityDef])

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    return Object.entries(cols).filter(([, col]) =>
      !q || col.label.toLowerCase().includes(q)
    )
  }, [cols, search])

  const _allVisible = filtered.every(([k]) => selected.includes(k))

  return (
    <div>
      {/* Search box */}
      <div style={{ position: 'relative', marginBottom: 8 }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Buscar campo…"
          style={{ ...fs, paddingLeft: 28, fontSize: 12 }}
        />
        <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: '#718096', fontSize: 13 }}>🔍</span>
        {search && (
          <button
            onClick={() => setSearch('')}
            style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#718096', cursor: 'pointer', fontSize: 13 }}>✕</button>
        )}
      </div>

      {/* Select all / none */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
        <button onClick={onSelectAll}
          style={{ background: 'none', border: 'none', color: '#90cdf4', fontSize: 11, cursor: 'pointer', padding: 0, fontFamily: 'inherit' }}>
          Seleccionar todos
        </button>
        <span style={{ color: '#4a5568', fontSize: 11 }}>·</span>
        <button onClick={onDeselectAll}
          style={{ background: 'none', border: 'none', color: '#718096', fontSize: 11, cursor: 'pointer', padding: 0, fontFamily: 'inherit' }}>
          Limpiar
        </button>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#4a5568' }}>
          {selected.length}/{Object.keys(cols).length}
        </span>
      </div>

      {/* Column list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 320, overflowY: 'auto', paddingRight: 2 }}>
        {filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: 12, color: '#4a5568', fontSize: 12 }}>Sin resultados</div>
        )}
        {filtered.map(([key, col]) => (
          <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '3px 4px', borderRadius: 4, background: selected.includes(key) ? '#1e3a5a' : 'transparent' }}>
            <input
              type="checkbox"
              checked={selected.includes(key)}
              onChange={() => onToggle(key)}
              style={{ accentColor: '#63b3ed', width: 13, height: 13, flexShrink: 0 }}
            />
            <span style={{ fontSize: 12, color: selected.includes(key) ? '#e2e8f0' : '#a0aec0', flex: 1 }}>{col.label}</span>
            <span style={{ fontSize: 9, color: '#4a5568', background: '#2d3748', borderRadius: 3, padding: '1px 4px', flexShrink: 0 }}>{col.type}</span>
          </label>
        ))}
      </div>
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
      <select value={filter.column} onChange={set('column')} style={{ ...fs, flex: '0 0 120px', fontSize: 11 }}>
        <option value="">Campo…</option>
        {Object.entries(cols).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
      </select>
      <select value={filter.operator} onChange={set('operator')} style={{ ...fs, flex: '0 0 110px', fontSize: 11 }}>
        {Object.entries(operators || {}).map(([k, o]) => <option key={k} value={k}>{o.label}</option>)}
      </select>
      {needsValue ? (
        <input
          value={filter.value}
          onChange={set('value')}
          placeholder="Valor…"
          style={{ ...fs, flex: 1, fontSize: 11 }}
        />
      ) : (
        <div style={{ flex: 1 }} />
      )}
      <button onClick={() => onRemove(index)}
        style={{ background: 'none', border: 'none', color: '#718096', cursor: 'pointer', fontSize: 14, flexShrink: 0 }}>✕</button>
    </div>
  )
}

// ── Preview table ──────────────────────────────────────────────────────────
function PreviewTable({ rows, columns, entityDef }) {
  const colDef = entityDef?.columns || {}
  if (!rows || rows.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 48, color: '#4a5568', fontSize: 13 }}>
        Configura la consulta y pulsa <strong style={{ color: '#90cdf4' }}>Previsualizar</strong>
      </div>
    )
  }
  const cellBase = { padding: '7px 10px', fontSize: 12, borderBottom: '1px solid #1e2d45', color: '#e2e8f0', whiteSpace: 'nowrap' }
  const thStyle  = { ...cellBase, fontWeight: 700, fontSize: 10, color: '#718096', textTransform: 'uppercase', background: '#1a202c' }

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
              onMouseEnter={e => e.currentTarget.style.background = '#2d3748'}
              onMouseLeave={e => e.currentTarget.style.background = ''}>
              {columns.map(c => (
                <td key={c} style={cellBase}>
                  {row[c] === null || row[c] === undefined ? <span style={{ color: '#4a5568' }}>—</span> :
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
      const res = await api.post('/reports/preview', buildQuery())
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
    const res = await api.post('/reports/export', q, { responseType: 'blob' })
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
      await api.post('/reports/templates', { name: tplName.trim(), query: buildQuery() })
      await qc.invalidateQueries(['report-templates'])
      setTplName('')
    } finally {
      setSavingTpl(false)
    }
  }

  const { data: templates = [] } = useQuery({
    queryKey: ['report-templates'],
    queryFn: () => api.get('/reports/templates').then(r => r.data),
  })

  const { mutate: deleteTpl } = useMutation({
    mutationFn: (id) => api.delete(`/reports/templates/${id}`),
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
    <div style={{ padding: 32, maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title={t('report_builder.title')}
        subtitle="Crea informes sin código: elige entidad, campos, filtros y exporta a CSV"
      />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {['builder', 'templates'].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: activeTab === t ? '#2b4a7a' : 'none',
            border: `1px solid ${activeTab === t ? '#63b3ed' : '#4a5568'}`,
            borderRadius: 8, padding: '6px 16px',
            color: activeTab === t ? '#90cdf4' : '#718096',
            cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
          }}>
            {t === 'builder' ? '🔧 Constructor' : `📁 Plantillas (${templates.length})`}
          </button>
        ))}
      </div>

      {activeTab === 'templates' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {templates.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 48, color: '#4a5568', fontSize: 14 }}>
              No hay plantillas guardadas. Crea un informe y guárdalo.
            </div>
          ) : templates.map(t => (
            <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: '12px 16px' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, color: '#e2e8f0', fontWeight: 600 }}>{t.name}</div>
                <div style={{ fontSize: 11, color: '#718096', marginTop: 2 }}>
                  {entities[t.query?.entity]?.label || t.query?.entity}
                  {' · '}{(t.query?.columns || []).length} columnas
                  {' · '}{(t.query?.filters || []).length} filtros
                </div>
              </div>
              <button onClick={() => loadTemplate(t)}
                style={{ background: '#2b4a7a', border: 'none', borderRadius: 6, color: '#90cdf4', padding: '6px 14px', cursor: 'pointer', fontSize: 12 }}>
                Cargar
              </button>
              <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar plantilla?', onConfirm: () => deleteTpl(t.id), danger: true }) }}
                style={{ background: 'none', border: 'none', color: '#718096', cursor: 'pointer', fontSize: 12 }}>
                Eliminar
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20, alignItems: 'start' }}>
          {/* ── Left panel ── */}
          <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 18, display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* Entity selector */}
            <div>
              <label style={ls}>Entidad de datos</label>
              <EntityPicker entities={entities} groups={groups} value={entity} onChange={changeEntity} />
              {entityDef && (
                <div style={{ marginTop: 6, fontSize: 11, color: '#4a5568' }}>
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
                  />
                </div>

                {/* Filters */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <label style={{ ...ls, marginBottom: 0 }}>Filtros</label>
                    <button onClick={addFilter}
                      style={{ background: 'none', border: 'none', color: '#90cdf4', cursor: 'pointer', fontSize: 12 }}>
                      + Añadir
                    </button>
                  </div>
                  {filters.length === 0 && (
                    <div style={{ fontSize: 11, color: '#4a5568', textAlign: 'center', padding: '6px 0' }}>Sin filtros</div>
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
                      style={{ ...fs, flex: 1, fontSize: 12 }}>
                      <option value="">Sin orden</option>
                      {Object.entries(entityDef.columns).map(([k, c]) =>
                        <option key={k} value={k}>{c.label}</option>
                      )}
                    </select>
                    <select
                      value={sort.direction}
                      onChange={e => setSort(s => ({ ...s, direction: e.target.value }))}
                      style={{ ...fs, width: 72, fontSize: 12 }}>
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
                background: entity ? '#2b4a7a' : '#2d3748',
                border: 'none', borderRadius: 8,
                color: entity ? '#90cdf4' : '#4a5568',
                padding: '10px 0', cursor: entity ? 'pointer' : 'not-allowed',
                fontWeight: 700, fontSize: 13, fontFamily: 'inherit',
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
                <span style={{ fontSize: 12, color: '#718096', flex: 1, minWidth: 120 }}>
                  {preview.count} fila{preview.count !== 1 ? 's' : ''}
                  {preview.truncated ? ' (máx. 500 en previsualización)' : ''}
                  {preview.error ? ' — error en la consulta' : ''}
                </span>
              )}
              <button
                onClick={exportCSV}
                disabled={!entity}
                style={{
                  background: entity ? '#276227' : '#2d3748', border: 'none', borderRadius: 8,
                  color: entity ? '#68d391' : '#4a5568',
                  padding: '8px 16px', cursor: entity ? 'pointer' : 'not-allowed',
                  fontSize: 12, fontFamily: 'inherit',
                }}>
                ⬇ Exportar CSV
              </button>
              <input
                value={tplName}
                onChange={e => setTplName(e.target.value)}
                placeholder="Nombre de plantilla…"
                style={{ ...fs, width: 190 }}
              />
              <button
                onClick={saveTemplate}
                disabled={!tplName.trim() || !entity || savingTpl}
                style={{
                  background: tplName.trim() && entity ? '#2b4a7a' : '#2d3748',
                  border: 'none', borderRadius: 8,
                  color: tplName.trim() && entity ? '#90cdf4' : '#4a5568',
                  padding: '8px 14px', cursor: 'pointer',
                  fontSize: 12, fontFamily: 'inherit', whiteSpace: 'nowrap',
                }}>
                {savingTpl ? 'Guardando…' : '💾 Guardar plantilla'}
              </button>
            </div>

            {/* Preview table */}
            <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, overflow: 'hidden', minHeight: 200 }}>
              <PreviewTable rows={preview?.rows} columns={resolvedColumns} entityDef={entityDef} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

