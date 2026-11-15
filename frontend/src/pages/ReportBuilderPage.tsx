/**
 * ReportBuilderPage — No-code parametric report builder
 *
 * Left panel : entity picker (grouped) + column checkboxes (searchable) + filters + sort
 * Right panel: live preview table + export button + save template
 */

import { useState, useCallback, useMemo, useRef, useId } from 'react'
import type { CSSProperties, ChangeEvent, DragEvent, ReactNode } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reportBuilderApi, biReportBuilderV2Api } from '../services/api'
import type { ColumnaDeEntidadBi, EntidadDeInformeBi, EsquemaDeInformes, PlantillaDeInforme, VistaPreviaDeInforme, VistaPreviaDePresetBiV2 } from '../services/api/tipos-bi'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BarChart2 } from 'lucide-react'
import { localeActivo } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { Table } from '../components/ui'
import { useToast } from '../context/ToastContext'
import useMediaQuery from '../hooks/useMediaQuery'
import { STALE_DEFAULT_MS } from '../constants/timings'
import { REPORT_BUILDER_ROW_LIMIT } from '../constants/pagination'
import './ReportBuilderPage.css'


type ColumnDef = ColumnaDeEntidadBi
type EntityDef = EntidadDeInformeBi
type OperatorDef = EsquemaDeInformes['operators'][string]
type ReportFilter = { column: string; operator: string; value: string }
type ReportSort = { column: string; direction: string }
/** La vista previa, o una vacía marcada con `error` si la consulta falla. */
type PreviewResult = VistaPreviaDeInforme & { error?: boolean }

const EMPTY_FILTER: ReportFilter = { column: '', operator: 'eq', value: '' }
const NULL_OPS = new Set(['is_null', 'is_not_null'])

function useSchema() {
  return useQuery({
    queryKey: ['report-schema'],
    queryFn: () => reportBuilderApi.schema().then(r => r.data),
    staleTime: Infinity,
  })
}

// ── Entity picker grouped by category ────────────────────────────────────
function EntityPicker({ entities, groups, value, onChange }: { entities: Record<string, EntityDef>; groups: Record<string, string>; value: string; onChange: (e: ChangeEvent<HTMLSelectElement>) => void }) {
  const traducir = useAppT()
  // Build { groupKey: [{ key, label }] }
  const byGroup = useMemo(() => {
    const map: Record<string, { key: string; label: string }[]> = {}
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
    <select className="rb-fs" aria-label={traducir('constructor_informes_ui.entidad')} value={value} onChange={onChange}>
      <option value="">{traducir('constructor_informes_ui.selecciona_entidad')}</option>
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
function ColumnPanel({ entityDef, selected, onToggle, onSelectAll, onDeselectAll, onReorder }: { entityDef: EntityDef | null; selected: string[]; onToggle: (key: string) => void; onSelectAll: () => void; onDeselectAll: () => void; onReorder: (order: string[]) => void }) {
  const traducir = useAppT()
  const [search, setSearch] = useState('')
  const cols: Record<string, ColumnDef> = useMemo(() => entityDef?.columns || {}, [entityDef])
  const dragItem = useRef<number | null>(null)
  const dragOver = useRef<number | null>(null)

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    return Object.entries(cols).filter(([, col]) =>
      !q || col.label.toLowerCase().includes(q)
    )
  }, [cols, search])

  const _allVisible = filtered.every(([k]) => selected.includes(k))

  // Drag-to-reorder selected columns
  const handleDragStart = (e: DragEvent, idx: number) => {
    dragItem.current = idx
    e.dataTransfer.effectAllowed = 'move'
  }
  const handleDragOver = (e: DragEvent, idx: number) => {
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
      <div className="rb-box">
        <input className="rb-fs rb-input" aria-label={traducir('constructor_informes_ui.buscar_campos')}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={traducir('constructor_informes_ui.buscar_campos')}
        />
        <span className="rb-box-muted">🔍</span>
        {search && (
          <button className="rb-btn-base" type="button" aria-label={traducir('constructor_informes_ui.limpiar_busqueda')}
            onClick={() => setSearch('')}>✕</button>
        )}
      </div>

      {/* Select all / none */}
      <div className="rb-row">
        <button className="rb-btn-xs" onClick={onSelectAll}>
          {traducir('reportbuilder.seleccionar_todos')}
        </button>
        <span className="rb-text-xs">·</span>
        <button className="rb-btn-xs-2" onClick={onDeselectAll}>
          {traducir('constructor_informes_ui.limpiar')}
        </button>
        <span className="rb-text-xs-2">
          {selected.length}/{Object.keys(cols).length}
        </span>
      </div>

      {/* Column list */}
      <div className="rb-stack">
        {filtered.length === 0 && (
          <div className="rb-state">{traducir('reportbuilder.sin_resultados')}</div>
        )}
        {filtered.map(([key, col]) => (
          <label className="rb-label" key={key} style={{ '--rb-label-background': selected.includes(key) ? 'var(--accent-muted)' : 'transparent' } as CSSProperties}>
            <input className="rb-input-2"
              type="checkbox"
              checked={selected.includes(key)}
              aria-label={col.label}
              onChange={() => onToggle(key)}
            />
            <span className="rb-box-2" style={{ '--rb-box-2-color': selected.includes(key) ? 'var(--text-1)' : 'var(--text-2)' } as CSSProperties}>{col.label}</span>
            <span className="rb-card">{col.type}</span>
          </label>
        ))}
      </div>

      {/* Drag-to-reorder selected columns */}
      {selected.length > 1 && (
        <div className="rb-text">
          <div className="rb-text-2xs-strong">
            {traducir('reportbuilder.orden_de_columnas_arrastra_para_reordenar')}
          </div>
          <div className="rb-stack-2">
            {selected.map((key, idx) => (
              <div className="rb-row-2"
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
              >
                <span className="rb-text-sm">⠿</span>
                <span className="rb-box-3">{cols[key]?.label || key}</span>
                <span className="rb-text-2xs">{idx + 1}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Filter row ─────────────────────────────────────────────────────────────
function FilterRow({ filter, index, entityDef, operators, onChange, onRemove }: { filter: ReportFilter; index: number; entityDef: EntityDef | null; operators: Record<string, OperatorDef>; onChange: (index: number, val: ReportFilter) => void; onRemove: (index: number) => void }) {
  const traducir = useAppT()
  const cols: Record<string, ColumnDef> = entityDef?.columns || {}
  const set = (k: string) => (e: ChangeEvent<HTMLSelectElement | HTMLInputElement>) => onChange(index, { ...filter, [k]: e.target.value })
  const needsValue = !NULL_OPS.has(filter.operator)
  return (
    <div className="rb-row-3">
      <select className="rb-fs rb-input-3" aria-label={traducir('constructor_informes_ui.campo_filtro')} value={filter.column} onChange={set('column')}>
        <option value="">{traducir('constructor_informes_ui.campo')}</option>
        {Object.entries(cols).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
      </select>
      <select className="rb-fs rb-input-4" aria-label={traducir('constructor_informes_ui.operador')} value={filter.operator} onChange={set('operator')}>
        {Object.entries(operators || {}).map(([k, o]) => <option key={k} value={k}>{o.label}</option>)}
      </select>
      {needsValue ? (
        <input className="rb-fs rb-input-5"
          aria-label={traducir('reportbuilder.valor_del_filtro')}
          value={filter.value}
          onChange={set('value')}
          placeholder={traducir('reportbuilder.valor_del_filtro')}
        />
      ) : (
        <div className="u-flex1" />
      )}
      <button className="rb-btn-md" type="button" aria-label={traducir('constructor_informes_ui.quitar_filtro')} title={traducir('constructor_informes_ui.quitar_filtro')} onClick={() => onRemove(index)}>✕</button>
    </div>
  )
}

// ── Preview table ──────────────────────────────────────────────────────────
function PreviewTable({ rows, columns, entityDef }: { rows?: Record<string, unknown>[]; columns: string[]; entityDef: EntityDef | null }) {
  const traducir = useAppT()
  const colDef: Record<string, ColumnDef> = entityDef?.columns || {}
  if (!rows || rows.length === 0) {
    return (
      <div className="rb-state-2">
        {traducir('reportbuilder.configura_la_consulta_y_pulsa')} <strong className="rb-text-info">{traducir('constructor_informes_ui.previsualizar')}</strong>
      </div>
    )
  }

  return (
    <div className="u-scroll-x">
      <Table
        data={rows}
        columns={columns.map(c => ({
          key: c,
          label: colDef[c]?.label || c,
          render: (_v: never, row: Record<string, unknown>) => (
            <span className="rb-cell-base">
              {row[c] === null || row[c] === undefined ? <span className="rb-text-2">—</span> :
               typeof row[c] === 'boolean' ? (row[c] ? '✔' : '✘') :
               String(row[c])}
            </span>
          ),
        }))}
      />
    </div>
  )
}

// ── BI presets tab (Report Builder v2) ─────────────────────────────────────

function BiPresetsTab() {
  const traducir = useAppT()
  const [selected, setSelected] = useState('finance_revenue_by_client')
  const [previewData, setPreview] = useState<VistaPreviaDePresetBiV2 | null>(null)
  // APIListResponse: llega como lista (antes se leía `.items` y no salía ningún preset).
  const { data: items = [] } = useQuery({
    queryKey: ['rbv2-presets'],
    queryFn: () => biReportBuilderV2Api.listPresets().then(r => r.data).catch(() => []),
    staleTime: STALE_DEFAULT_MS,
  })

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
      a.download = res.data.filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (_) { /* ignore */ }
  }

  return (
    <div className="rb-card-2">
      <div className="rb-row-4">
        <span className="rb-text-strong">{traducir('constructor_informes_ui.presets_bi')}</span>
        <span className="u-text3-xs">{traducir('constructor_informes_ui.n_presets', { n: items.length })}</span>
      </div>
      <div className="rb-box-4">
        <div className="rb-row-5">
          {items.slice(0, 16).map(p => (
            <button className="rb-btn-xs-3" type="button" aria-pressed={selected === p.id} key={p.id} onClick={() => setSelected(p.id)}
              style={{ '--rb-btn-xs-3-border': `1.5px solid ${selected === p.id ? 'var(--accent)' : 'var(--surface-4)'}`, '--rb-btn-xs-3-background': selected === p.id ? 'var(--accent-muted)' : 'transparent', '--rb-btn-xs-3-color': selected === p.id ? 'var(--accent)' : 'var(--text-2)', '--rb-btn-xs-3-font-weight': selected === p.id ? '700' : '400' } as CSSProperties}>
              {p.name}
            </button>
          ))}
          {items.length > 16 && <span className="rb-box-muted-2">+{items.length - 16} {traducir('reportbuilder.mas')}</span>}
        </div>
        <div className="rb-row-6">
          <button className="rb-btn-sm" onClick={runPreview}>
            {traducir('constructor_informes_ui.vista_previa')}
          </button>
          <button className="rb-btn-sm-2" onClick={exportJson}>
            {traducir('constructor_informes_ui.exportar_json')}
          </button>
        </div>
        {previewData && (
          <div className="u-scroll-x">
            <table className="u-table-sm">
              <thead>
                <tr className="rb-tr">
                  {previewData.columns.map(c => (
                    <th className="rb-th" key={c}>{c.replace(/_/g, ' ')}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewData.rows.map((row, ri) => (
                  <tr key={ri} className="u-border-b">
                    {previewData.columns.map(c => <td className="rb-td" key={c}>{(row[c] ?? '—') as ReactNode}</td>)}
                  </tr>
                ))}
                {!previewData.rows.length && (
                  <tr><td className="rb-td-muted" colSpan={previewData.columns.length || 1}>{traducir('reportbuilder.sin_datos_para_este_preset')}</td></tr>
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
  const traducir = useAppT()
  const idGrupo = useId()
  const toast = useToast()
  const narrow = useMediaQuery('(max-width: 900px)')
  const t = useAppT()
  const { data: schema } = useSchema()
  const qc = useQueryClient()

  const [entity,    setEntity]    = useState('')
  const [columns,   setColumns]   = useState<string[]>([])
  const [filters,   setFilters]   = useState<ReportFilter[]>([])
  const [sort,      setSort]      = useState<ReportSort>({ column: '', direction: 'asc' })
  const [preview,   setPreview]   = useState<PreviewResult | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [tplName,   setTplName]   = useState('')
  const [savingTpl, setSavingTpl] = useState(false)
  const [activeTab, setTab]       = useState('builder')

  const entities: Record<string, EntityDef>  = schema?.entities  || {}
  const operators: Record<string, OperatorDef> = schema?.operators || {}
  const groups: Record<string, string>    = schema?.groups    || {}
  const entityDef = entity ? entities[entity] : null

  const toggleColumn = useCallback((col: string) => {
    setColumns(prev => prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col])
  }, [])

  const selectAllColumns = useCallback(() => {
    setColumns(Object.keys(entityDef?.columns || {}))
  }, [entityDef])

  const deselectAllColumns = useCallback(() => setColumns([]), [])

  const reorderColumns = useCallback((newOrder: string[]) => setColumns(newOrder), [])

  const changeEntity = (e: ChangeEvent<HTMLSelectElement>) => {
    setEntity(e.target.value)
    setColumns([])
    setFilters([])
    setSort({ column: '', direction: 'asc' })
    setPreview(null)
  }

  const addFilter    = () => setFilters(f => [...f, { ...EMPTY_FILTER }])
  const changeFilter = (i: number, val: ReportFilter) => setFilters(f => f.map((x, idx) => idx === i ? val : x))
  const removeFilter = (i: number) => setFilters(f => f.filter((_, idx) => idx !== i))

  const buildQuery = () => ({
    entity,
    columns: columns.length > 0 ? columns : Object.keys(entityDef?.columns || {}),
    filters: filters.filter(f => f.column && f.operator),
    sort: sort.column ? sort : null,
    limit: REPORT_BUILDER_ROW_LIMIT,
  })

  const runPreview = async () => {
    if (!entity) return
    setLoading(true)
    try {
      const res = await reportBuilderApi.preview(buildQuery())
      setPreview(res.data)
    } catch {
      setPreview({ rows: [], count: 0, truncated: false, error: true })
    } finally {
      setLoading(false)
    }
  }

  const exportCSV = async () => {
    if (!entity) return
    const q = buildQuery()
    const res = await reportBuilderApi.export(q, { responseType: 'blob' })
    // Revisión 2026-11: la exportación trae todo hasta REPORT_EXPORT_MAX_ROWS;
    // si la fuente tiene más, se dice (antes se cortaba en 2.000 en silencio).
    const total = Number(res.headers['x-total-count'] ?? 0)
    const filas = Number(res.headers['x-page-size'] ?? 0)
    if (total > filas && filas > 0) toast.warning(traducir('reportbuilder.csv_parcial', { filas: filas.toLocaleString(localeActivo()), total: total.toLocaleString(localeActivo()) }))
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
      await qc.invalidateQueries({ queryKey: ['report-templates'] })
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
    mutationFn: (id: PlantillaDeInforme['id']) => reportBuilderApi.deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report-templates'] }),
  })

  const loadTemplate = (tpl: PlantillaDeInforme) => {
    const q = tpl.query
    setEntity(q.entity)
    setColumns(q.columns)
    setFilters(q.filters.map(f => ({ column: f.column, operator: f.operator, value: f.value == null ? '' : String(f.value) })))
    setSort(q.sort || { column: '', direction: 'asc' })
    setPreview(null)
    setTab('builder')
  }

  const resolvedColumns = columns.length > 0 ? columns : Object.keys(entityDef?.columns || {})

  return (
    <PageShell className="rb-shell">
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('report_builder.title')}
        subtitle={t('report_builder.subtitle')}
      showListExport={false}
      />

      {/* Tabs */}
      <div className="rb-row-7">
        {['builder', 'templates', 'presets'].map(t => (
          <button className="rb-btn-base-2" type="button" aria-pressed={activeTab === t} key={t} onClick={() => setTab(t)} style={{ '--rb-btn-base-2-background': activeTab === t ? 'var(--accent-glow)' : 'none', '--rb-btn-base-2-border': `1px solid ${activeTab === t ? 'var(--info)' : 'var(--surface-5)'}`, '--rb-btn-base-2-color': activeTab === t ? 'var(--info)' : 'var(--text-2)' } as CSSProperties}>
            {t === 'builder' ? traducir('constructor_informes_ui.tab_constructor')
              : t === 'templates' ? traducir('constructor_informes_ui.tab_plantillas', { n: templates.length })
              : traducir('constructor_informes_ui.tab_presets')}
          </button>
        ))}
      </div>

      {activeTab === 'presets' ? (
        <BiPresetsTab />
      ) : activeTab === 'templates' ? (
        <div className="u-stack-10">
          {templates.length === 0 ? (
            <div className="rb-state-3">
              {traducir('reportbuilder.no_hay_plantillas_guardadas_crea_un_informe')}
            </div>
          ) : templates.map(t => (
            <div className="rb-row-8" key={t.id}>
              <div className="u-flex1-min0">
                <div className="rb-text-md">{t.name}</div>
                <div className="u-text2-xs-mt2">
                  {entities[t.query.entity]?.label || t.query.entity}
                  {' · '}{traducir('constructor_informes_ui.n_columnas', { n: t.query.columns.length })}
                  {' · '}{traducir('constructor_informes_ui.n_filtros', { n: t.query.filters.length })}
                </div>
              </div>
              <button className="rb-btn-sm-3" onClick={() => loadTemplate(t)}>
                {traducir('constructor_informes_ui.cargar')}
              </button>
              <button className="rb-btn-sm-4" onClick={() => { openConfirmGlobal({ message: traducir('constructor_informes_ui.eliminar_plantilla_confirm'), onConfirm: () => deleteTpl(t.id), danger: true }) }}>
                {traducir('common.delete')}
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="rb-grid" style={{ '--rb-grid-grid-template-columns': narrow ? 'minmax(0, 1fr)' : '300px minmax(0, 1fr)' } as CSSProperties}>
          {/* ── Left panel ── */}
          <div className="rb-stack-3">

            {/* Entity selector */}
            <div>
              <label className="rb-ls">{traducir('reportbuilder.entidad_de_datos')}</label>
              <EntityPicker entities={entities} groups={groups} value={entity} onChange={changeEntity} />
              {entityDef && (
                <div className="rb-text-xs-3">
                  {traducir('constructor_informes_ui.n_campos', { n: Object.keys(entityDef.columns).length })}
                </div>
              )}
            </div>

            {entityDef && (
              <>
                {/* Column selector */}
                <div role="group" aria-labelledby={`${idGrupo}-campos`}>
                  <span className="rb-ls" id={`${idGrupo}-campos`}>{traducir('constructor_informes_ui.campos_incluir')}</span>
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
                <div role="group" aria-labelledby={`${idGrupo}-filtros`}>
                  <div className="rb-row-9">
                    <span className="rb-ls rb-text-3" id={`${idGrupo}-filtros`}>{traducir('constructor_informes_ui.filtros')}</span>
                    <button className="rb-btn-sm-5" onClick={addFilter}>
                      {traducir('reportbuilder.anadir')}
                    </button>
                  </div>
                  {filters.length === 0 && (
                    <div className="rb-state-4">{traducir('reportbuilder.sin_filtros')}</div>
                  )}
                  {filters.map((f, i) => (
                    <FilterRow key={i} filter={f} index={i} entityDef={entityDef}
                      operators={operators} onChange={changeFilter} onRemove={removeFilter} />
                  ))}
                </div>

                {/* Sort */}
                <div>
                  <label className="rb-ls">{traducir('reportbuilder.ordenar_por')}</label>
                  <div className="u-row-6">
                    <select className="rb-fs rb-input-6" aria-label={traducir('constructor_informes_ui.orden_campo')}
                      value={sort.column}
                      onChange={e => setSort(s => ({ ...s, column: e.target.value }))}>
                      <option value="">{traducir('reportbuilder.sin_orden')}</option>
                      {Object.entries(entityDef.columns).map(([k, c]) =>
                        <option key={k} value={k}>{c.label}</option>
                      )}
                    </select>
                    <select className="rb-fs rb-input-7" aria-label={traducir('constructor_informes_ui.orden_direccion')}
                      value={sort.direction}
                      onChange={e => setSort(s => ({ ...s, direction: e.target.value }))}>
                      <option value="asc">{traducir('constructor_informes_ui.asc')}</option>
                      <option value="desc">{traducir('constructor_informes_ui.desc')}</option>
                    </select>
                  </div>
                </div>
              </>
            )}

            <button className="rb-btn-base-3"
              onClick={runPreview}
              disabled={!entity || loading}
              style={{ '--rb-btn-base-3-background': entity ? 'var(--accent)' : 'var(--surface-4)', '--rb-btn-base-3-color': entity ? 'var(--info)' : 'var(--surface-5)', '--rb-btn-base-3-cursor': entity ? 'pointer' : 'not-allowed' } as CSSProperties}>
              {loading ? traducir('constructor_informes_ui.consultando') : traducir('constructor_informes_ui.previsualizar_btn')}
            </button>
          </div>

          {/* ── Right panel ── */}
          <div className="rb-stack-4">
            {/* Toolbar */}
            <div className="u-wrap-center-8">
              {preview && (
                <span className="rb-box-muted-3">
                  {preview.count === 1 ? traducir('constructor_informes_ui.una_fila') : traducir('constructor_informes_ui.n_filas', { n: preview.count })}
                  {preview.truncated ? traducir('constructor_informes_ui.truncado') : ''}
                  {preview.error ? traducir('constructor_informes_ui.error_consulta') : ''}
                </span>
              )}
              <button className="rb-btn-sm-6"
                onClick={exportCSV}
                disabled={!entity}
                style={{ '--rb-btn-sm-6-background': entity ? 'var(--success-bg)' : 'var(--surface-4)', '--rb-btn-sm-6-border': `1px solid ${entity ? 'var(--success-border)' : 'var(--surface-4)'}`, '--rb-btn-sm-6-color': entity ? 'var(--success)' : 'var(--text-3)', '--rb-btn-sm-6-cursor': entity ? 'pointer' : 'not-allowed' } as CSSProperties}>
                {traducir('constructor_informes_ui.exportar_csv')}
              </button>
              <input className="rb-fs rb-input-8"
                aria-label={traducir('reportbuilder.nombre_de_la_plantilla')}
                value={tplName}
                onChange={e => setTplName(e.target.value)}
                placeholder={traducir('reportbuilder.nombre_de_la_plantilla')}
              />
              <button className="rb-btn-sm-7"
                onClick={saveTemplate}
                disabled={!tplName.trim() || !entity || savingTpl}
                style={{ '--rb-btn-sm-7-background': tplName.trim() && entity ? 'var(--accent)' : 'var(--surface-4)', '--rb-btn-sm-7-color': tplName.trim() && entity ? 'var(--info)' : 'var(--surface-5)' } as CSSProperties}>
                {savingTpl ? traducir('constructor_informes_ui.guardando') : traducir('constructor_informes_ui.guardar_plantilla')}
              </button>
            </div>

            {/* Preview table */}
            <div className="rb-card-3">
              <PreviewTable rows={preview?.rows} columns={resolvedColumns} entityDef={entityDef} />
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}

