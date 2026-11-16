/**
 * ReportBuilderPage — No-code parametric report builder
 *
 * Left panel : entity picker (grouped) + column checkboxes (searchable) + filters + sort
 * Right panel: live preview table + export button + save template
 *
 * 16-11-2026: pasada de diseño. Pestañas con el componente Tabs e iconos
 * lucide (antes botones propios con emojis y color `--info`); botones
 * del kit (antes propios con emojis y, en oscuro, los desactivados con
 * el texto en `--surface-5`, casi invisible); campos `ds-input` (antes grises
 * propios); vacíos con EmptyState; sin ancho máximo centrado; textos de tipo
 * de columna y de ayuda con tokens de texto legibles (antes tokens de fondo).
 */

import { useState, useCallback, useMemo, useRef, useId } from 'react'
import type { ChangeEvent, DragEvent, ReactNode } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reportBuilderApi, biReportBuilderV2Api } from '../services/api'
import type { ColumnaDeEntidadBi, EntidadDeInformeBi, EsquemaDeInformes, PlantillaDeInforme, VistaPreviaDeInforme, VistaPreviaDePresetBiV2 } from '../services/api/tipos-bi'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  BarChart2, Wrench, FolderOpen, Zap, Search, X, Play, Download, Save, Plus, GripVertical,
  Check, Minus, FileDown, Table2, FileStack, Trash2, Upload,
} from 'lucide-react'
import { localeActivo } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { Button, Card, EmptyState, Table, Tabs } from '../components/ui'
import { useToast } from '../context/ToastContext'
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
function EntityPicker({ id, entities, groups, value, onChange }: { id: string; entities: Record<string, EntityDef>; groups: Record<string, string>; value: string; onChange: (e: ChangeEvent<HTMLSelectElement>) => void }) {
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
    <select id={id} className="ds-input" value={value} onChange={onChange}>
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
    <div className="u-stack-8">
      {/* Search box */}
      <div className="rb-buscar">
        <Search size={14} className="rb-buscar__icono" aria-hidden />
        <input className="ds-input rb-buscar__campo" aria-label={traducir('constructor_informes_ui.buscar_campos')}
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={traducir('constructor_informes_ui.buscar_campos')}
        />
        {search && (
          <button className="rb-buscar__limpiar" type="button" aria-label={traducir('constructor_informes_ui.limpiar_busqueda')}
            onClick={() => setSearch('')}><X size={13} aria-hidden /></button>
        )}
      </div>

      {/* Select all / none */}
      <div className="rb-seleccion">
        <Button size="xs" variant="ghost" onClick={onSelectAll}>{traducir('reportbuilder.seleccionar_todos')}</Button>
        <Button size="xs" variant="ghost" onClick={onDeselectAll}>{traducir('constructor_informes_ui.limpiar')}</Button>
        <span className="rb-contador">{selected.length}/{Object.keys(cols).length}</span>
      </div>

      {/* Column list */}
      <div className="rb-columnas">
        {filtered.length === 0 && (
          <div className="rb-nota rb-nota--centro">{traducir('reportbuilder.sin_resultados')}</div>
        )}
        {filtered.map(([key, col]) => {
          const marcada = selected.includes(key)
          return (
            <label className={`rb-columna${marcada ? ' rb-columna--marcada' : ''}`} key={key}>
              <input className="rb-check"
                type="checkbox"
                checked={marcada}
                onChange={() => onToggle(key)}
              />
              <span className="rb-columna__nombre">{col.label}</span>
              <span className="rb-columna__tipo">{col.type}</span>
            </label>
          )
        })}
      </div>

      {/* Drag-to-reorder selected columns */}
      {selected.length > 1 && (
        <div className="u-stack-6">
          <div className="ds-eyebrow">
            {traducir('reportbuilder.orden_de_columnas_arrastra_para_reordenar')}
          </div>
          <div className="rb-orden">
            {selected.map((key, idx) => (
              <div className="rb-orden__item"
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
                <GripVertical size={13} className="rb-orden__asa" aria-hidden />
                <span className="rb-orden__nombre">{cols[key]?.label || key}</span>
                <span className="rb-orden__n">{idx + 1}</span>
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
    <div className="rb-filtro">
      <div className="rb-filtro__campos">
        <select className="ds-input" aria-label={traducir('constructor_informes_ui.campo_filtro')} value={filter.column} onChange={set('column')}>
          <option value="">{traducir('constructor_informes_ui.campo')}</option>
          {Object.entries(cols).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
        </select>
        <select className="ds-input" aria-label={traducir('constructor_informes_ui.operador')} value={filter.operator} onChange={set('operator')}>
          {Object.entries(operators || {}).map(([k, o]) => <option key={k} value={k}>{o.label}</option>)}
        </select>
        {needsValue && (
          <input className="ds-input"
            aria-label={traducir('reportbuilder.valor_del_filtro')}
            value={filter.value}
            onChange={set('value')}
            placeholder={traducir('reportbuilder.valor_del_filtro')}
          />
        )}
      </div>
      <button className="rb-icono" type="button" aria-label={traducir('constructor_informes_ui.quitar_filtro')} title={traducir('constructor_informes_ui.quitar_filtro')} onClick={() => onRemove(index)}><X size={14} aria-hidden /></button>
    </div>
  )
}

// ── Preview table ──────────────────────────────────────────────────────────
function PreviewTable({ rows, columns, entityDef }: { rows?: Record<string, unknown>[]; columns: string[]; entityDef: EntityDef | null }) {
  const traducir = useAppT()
  const colDef: Record<string, ColumnDef> = entityDef?.columns || {}
  if (!rows || rows.length === 0) {
    return (
      <EmptyState icon={<Table2 size={28} />} title={traducir('constructor_informes_ui.sin_vista_previa')}
        description={traducir('constructor_informes_ui.sin_vista_previa_desc')} />
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
            <span className="rb-celda">
              {row[c] === null || row[c] === undefined ? <span className="rb-celda--vacia">—</span> :
               typeof row[c] === 'boolean' ? (row[c]
                 ? <><Check size={13} className="rb-si" aria-hidden /><span className="u-sr-only">{traducir('common.yes')}</span></>
                 : <><Minus size={13} className="rb-no" aria-hidden /><span className="u-sr-only">{traducir('common.no')}</span></>) :
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
    <Card>
      <div className="rb-presets__cabecera">
        <span className="rb-titulo">{traducir('constructor_informes_ui.presets_bi')}</span>
        <span className="u-text3-xs">{traducir('constructor_informes_ui.n_presets', { n: items.length })}</span>
      </div>
      {items.length === 0 ? (
        <EmptyState icon={<Zap size={28} />} title={traducir('constructor_informes_ui.sin_presets')} />
      ) : (
        <>
          <div className="rb-presets">
            {items.slice(0, 16).map(p => (
              <button className={`rb-preset${selected === p.id ? ' rb-preset--activo' : ''}`} type="button" aria-pressed={selected === p.id} key={p.id} onClick={() => setSelected(p.id)}>
                {p.name}
              </button>
            ))}
            {items.length > 16 && <span className="rb-nota">+{items.length - 16} {traducir('reportbuilder.mas')}</span>}
          </div>
          <div className="u-wrap-8">
            <Button size="sm" icon={<Play size={13} />} onClick={runPreview}>
              {traducir('constructor_informes_ui.vista_previa')}
            </Button>
            <Button size="sm" variant="secondary" icon={<FileDown size={13} />} onClick={exportJson}>
              {traducir('constructor_informes_ui.exportar_json')}
            </Button>
          </div>
        </>
      )}
      {previewData && (
        <div className="u-scroll-x">
          <table className="rb-tabla">
            <thead>
              <tr>
                {previewData.columns.map(c => (
                  <th className="rb-th" key={c}>{c.replace(/_/g, ' ')}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {previewData.rows.map((row, ri) => (
                <tr key={ri} className="rb-tr">
                  {previewData.columns.map(c => <td className="rb-td" key={c}>{(row[c] ?? '—') as ReactNode}</td>)}
                </tr>
              ))}
              {!previewData.rows.length && (
                <tr><td className="rb-td rb-td--vacia" colSpan={previewData.columns.length || 1}>{traducir('reportbuilder.sin_datos_para_este_preset')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function ReportBuilderPage() {
  const traducir = useAppT()
  const idGrupo = useId()
  const toast = useToast()
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
    <PageShell>
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('nav.report_builder')}
        subtitle={t('report_builder.subtitle')}
        showListExport={false}
      />

      <div className="u-stack-16">
      <Tabs
        ariaLabel={t('nav.report_builder')}
        active={activeTab}
        onChange={setTab}
        items={[
          { id: 'builder', label: traducir('constructor_informes_ui.tab_constructor'), icon: <Wrench size={14} /> },
          { id: 'templates', label: traducir('constructor_informes_ui.tab_plantillas', { n: templates.length }), icon: <FolderOpen size={14} /> },
          { id: 'presets', label: traducir('constructor_informes_ui.tab_presets'), icon: <Zap size={14} /> },
        ]}
      />

      {activeTab === 'presets' ? (
        <BiPresetsTab />
      ) : activeTab === 'templates' ? (
        templates.length === 0 ? (
          <EmptyState icon={<FileStack size={28} />} title={traducir('constructor_informes_ui.sin_plantillas')}
            description={traducir('reportbuilder.no_hay_plantillas_guardadas_crea_un_informe')}
            action={<Button icon={<Wrench size={14} />} onClick={() => setTab('builder')}>{traducir('constructor_informes_ui.ir_al_constructor')}</Button>} />
        ) : (
        <div className="u-stack-8">
          {templates.map(tpl => (
            <Card className="rb-plantilla" key={tpl.id}>
              <div className="u-flex1-min0">
                <div className="rb-plantilla__nombre">{tpl.name}</div>
                <div className="u-text2-xs-mt2">
                  {entities[tpl.query.entity]?.label || tpl.query.entity}
                  {' · '}{traducir('constructor_informes_ui.n_columnas', { n: tpl.query.columns.length })}
                  {' · '}{traducir('constructor_informes_ui.n_filtros', { n: tpl.query.filters.length })}
                </div>
              </div>
              <div className="u-wrap-8">
                <Button size="sm" variant="secondary" icon={<Upload size={13} />} onClick={() => loadTemplate(tpl)}>
                  {traducir('constructor_informes_ui.cargar')}
                </Button>
                <Button size="sm" variant="danger" icon={<Trash2 size={13} />} onClick={() => { openConfirmGlobal({ message: traducir('constructor_informes_ui.eliminar_plantilla_confirm'), onConfirm: () => deleteTpl(tpl.id), danger: true }) }}>
                  {traducir('common.delete')}
                </Button>
              </div>
            </Card>
          ))}
        </div>
        )
      ) : (
        <div className="rb-grid">
          {/* ── Left panel ── */}
          <Card className="rb-panel">

            {/* Entity selector */}
            <div className="ui-field">
              <label className="uiinde-estiloetiqueta" htmlFor={`${idGrupo}-entidad`}>{traducir('reportbuilder.entidad_de_datos')}</label>
              <EntityPicker id={`${idGrupo}-entidad`} entities={entities} groups={groups} value={entity} onChange={changeEntity} />
              {entityDef && (
                <div className="rb-nota">
                  {traducir('constructor_informes_ui.n_campos', { n: Object.keys(entityDef.columns).length })}
                </div>
              )}
            </div>

            {entityDef && (
              <>
                {/* Column selector */}
                <div role="group" aria-labelledby={`${idGrupo}-campos`} className="u-stack-6">
                  <span className="uiinde-estiloetiqueta" id={`${idGrupo}-campos`}>{traducir('constructor_informes_ui.campos_incluir')}</span>
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
                <div role="group" aria-labelledby={`${idGrupo}-filtros`} className="u-stack-8">
                  <div className="rb-filtros__cabecera">
                    <span className="uiinde-estiloetiqueta" id={`${idGrupo}-filtros`}>{traducir('constructor_informes_ui.filtros')}</span>
                    <Button size="xs" variant="secondary" icon={<Plus size={12} />} onClick={addFilter}>
                      {traducir('reportbuilder.anadir')}
                    </Button>
                  </div>
                  {filters.length === 0 && (
                    <div className="rb-nota">{traducir('reportbuilder.sin_filtros')}</div>
                  )}
                  {filters.map((f, i) => (
                    <FilterRow key={i} filter={f} index={i} entityDef={entityDef}
                      operators={operators} onChange={changeFilter} onRemove={removeFilter} />
                  ))}
                </div>

                {/* Sort */}
                <div className="ui-field">
                  <label className="uiinde-estiloetiqueta" htmlFor={`${idGrupo}-orden`}>{traducir('reportbuilder.ordenar_por')}</label>
                  <div className="rb-orden-campos">
                    <select id={`${idGrupo}-orden`} className="ds-input"
                      value={sort.column}
                      onChange={e => setSort(s => ({ ...s, column: e.target.value }))}>
                      <option value="">{traducir('reportbuilder.sin_orden')}</option>
                      {Object.entries(entityDef.columns).map(([k, c]) =>
                        <option key={k} value={k}>{c.label}</option>
                      )}
                    </select>
                    <select className="ds-input" aria-label={traducir('constructor_informes_ui.orden_direccion')}
                      value={sort.direction}
                      onChange={e => setSort(s => ({ ...s, direction: e.target.value }))}>
                      <option value="asc">{traducir('constructor_informes_ui.asc')}</option>
                      <option value="desc">{traducir('constructor_informes_ui.desc')}</option>
                    </select>
                  </div>
                </div>
              </>
            )}

            <Button icon={<Play size={14} />} onClick={runPreview} disabled={!entity} loading={loading}>
              {loading ? traducir('constructor_informes_ui.consultando') : traducir('constructor_informes_ui.previsualizar_btn')}
            </Button>
          </Card>

          {/* ── Right panel ── */}
          <div className="rb-derecha">
            {/* Toolbar */}
            <div className="rb-barra">
              {preview && (
                <span className={`rb-resultado${preview.error ? ' rb-resultado--error' : ''}`}>
                  {preview.count === 1 ? traducir('constructor_informes_ui.una_fila') : traducir('constructor_informes_ui.n_filas', { n: preview.count })}
                  {preview.truncated ? traducir('constructor_informes_ui.truncado') : ''}
                  {preview.error ? traducir('constructor_informes_ui.error_consulta') : ''}
                </span>
              )}
              <div className="rb-barra__acciones">
                <Button variant="secondary" icon={<Download size={14} />} onClick={exportCSV} disabled={!entity}>
                  {traducir('constructor_informes_ui.exportar_csv')}
                </Button>
                <input className="ds-input rb-nombre-plantilla"
                  aria-label={traducir('reportbuilder.nombre_de_la_plantilla')}
                  value={tplName}
                  onChange={e => setTplName(e.target.value)}
                  placeholder={traducir('reportbuilder.nombre_de_la_plantilla')}
                />
                <Button variant="secondary" icon={<Save size={14} />} onClick={saveTemplate}
                  disabled={!tplName.trim() || !entity} loading={savingTpl}>
                  {savingTpl ? traducir('constructor_informes_ui.guardando') : traducir('constructor_informes_ui.guardar_plantilla')}
                </Button>
              </div>
            </div>

            {/* Preview table */}
            <Card className="rb-vista">
              <PreviewTable rows={preview?.rows} columns={resolvedColumns} entityDef={entityDef} />
            </Card>
          </div>
        </div>
      )}
      </div>
    </PageShell>
  )
}
