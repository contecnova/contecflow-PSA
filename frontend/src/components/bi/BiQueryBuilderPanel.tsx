/**
 * BiQueryBuilderPanel.jsx — Self-service visual query builder (no-SQL).
 *
 * Tabs:
 *   builder  — pick dataset / fields / filters / aggregations visually
 *   saved    — list + run saved queries
 *   results  — last execution result as table
 */
import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biQueryBuilderApi } from '../../services/api'
import type { ConsultaGuardadaBi, ResultadoDeConsultaBi } from '../../services/api/tipos-bi'
import { useAppLang } from '../../i18n/AppLangContext'
import { Button, EmptyState, IconButton, Table, Tabs, Select, Input } from '../ui'
import { FolderOpen, Hammer, Play, Plus, Save, Table2, Trash2, X } from 'lucide-react'
import { fmtNumber } from '../../utils/helpers'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import './BiQueryBuilderPanel.css'
import { confirmar } from '../../context/ConfirmContext'



/** Estado del formulario: un filtro con el valor tal cual se teclea. */
interface FilterEntry {
  field: string
  operator: string
  value: string
}

/** Estado del formulario: una agregación (el alias lo pone el servidor si falta). */
interface AggregationEntry {
  func: string
  field: string
  alias?: string
}

const errorMessage = (e: unknown, fallback: string): string => {
  return (e as { message?: string })?.message || fallback
}

// Operadores y agregaciones salen del esquema del servidor (`operators`, `aggregations`).
const OPERADOR_POR_DEFECTO = 'eq'
const NULL_OPS = new Set(['is_null', 'is_not_null'])

export default function BiQueryBuilderPanel() {
  const idCampo = React.useId()
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const [tab, setTab] = useState<string>('builder')
  const [results, setResults] = useState<ResultadoDeConsultaBi | null>(null)
  const [execError, setExecError] = useState<string | null>(null)

  // ── Schema ────────────────────────────────────────────────────────────────
  const { data: schema } = useQuery({
    queryKey: ['bi-qb-schema'],
    queryFn: () => biQueryBuilderApi.getSchema({}).then((r) => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const datasets = useMemo(() => schema?.datasets ?? [], [schema])
  const operadores = schema?.operators ?? {}
  const agregaciones = schema?.aggregations ?? []

  // ── Saved queries ─────────────────────────────────────────────────────────
  const { data: savedData } = useQuery({
    queryKey: ['bi-qb-queries'],
    queryFn: () => biQueryBuilderApi.listQueries().then((r) => r.data),
  })
  const savedQueries = savedData?.items ?? []

  // ── Builder state ─────────────────────────────────────────────────────────
  const [dataset, setDataset] = useState<string>('')
  const [selectedFields, setSelectedFields] = useState<string[]>([])
  const [filters, setFilters] = useState<FilterEntry[]>([{ field: '', operator: OPERADOR_POR_DEFECTO, value: '' }])
  const [groupBy, setGroupBy] = useState<string[]>([])
  const [aggregations, setAggregations] = useState<AggregationEntry[]>([])
  const [sortBy, setSortBy] = useState<string>('')
  const [sortDir, setSortDir] = useState<string>('desc')
  const [limit, setLimit] = useState<number>(100)
  const [queryName, setQueryName] = useState<string>('')

  const currentDatasetMeta = useMemo(() => datasets.find(d => d.name === dataset), [datasets, dataset])
  const availableFields = currentDatasetMeta?.fields ?? []

  // ── Mutations ─────────────────────────────────────────────────────────────
  const saveMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => biQueryBuilderApi.saveQuery(payload).then((r) => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bi-qb-queries'] }); setQueryName('') },
  })

  const previewMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => biQueryBuilderApi.previewQuery(payload).then((r) => r.data),
    onSuccess: (data) => { setResults(data); setTab('results') },
    onError: (e) => setExecError(errorMessage(e, traducir('biquerybuilder.error_ejecutar'))),
  })

  const execSavedMut = useMutation({
    mutationFn: (id: string) => biQueryBuilderApi.executeQuery(id).then((r) => r.data),
    onSuccess: (data) => { setResults(data); setTab('results') },
    onError: (e) => setExecError(errorMessage(e, traducir('biquerybuilder.error_ejecutar'))),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => biQueryBuilderApi.deleteQuery(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-qb-queries'] }),
  })

  function buildPayload() {
    return {
      dataset,
      fields: selectedFields,
      filters: filters
        .filter(f => f.field)
        .map((f) => ({
          ...f,
          value: NULL_OPS.has(f.operator) ? null : f.value,
        })),
      group_by: groupBy,
      aggregations: aggregations.filter(a => a.field && a.func),
      sort_by: sortBy || null,
      sort_dir: sortDir,
      limit,
    }
  }

  function handleRunBuilder() {
    if (!dataset) return
    setExecError(null)
    previewMut.mutate(buildPayload())
  }

  function handleSaveBuilder() {
    if (!dataset || !queryName.trim()) return
    const body = {
      name: queryName.trim(),
      ...buildPayload(),
    }
    saveMut.mutate(body)
  }

  function loadSavedQuery(q: ConsultaGuardadaBi) {
    setDataset(q.dataset)
    setSelectedFields(q.fields)
    // El servidor guarda el operador normalizado (`eq`, `neq`...): las claves de `operators`.
    setFilters(q.filters.map((f) => ({
      field: f.field,
      operator: f.operator,
      value: f.value == null ? '' : String(f.value),
    })))
    setGroupBy(q.group_by)
    setAggregations(q.aggregations)
    setSortBy(q.sort_by || '')
    setSortDir(q.sort_dir)
    setLimit(q.limit)
    setQueryName(q.name)
    setTab('builder')
  }

  function toggleField(f: string) {
    setSelectedFields(prev => prev.includes(f) ? prev.filter(x => x !== f) : [...prev, f])
  }

  function toggleGroupBy(f: string) {
    setGroupBy(prev => prev.includes(f) ? prev.filter(x => x !== f) : [...prev, f])
  }

  function addAgg() {
    setAggregations(prev => [...prev, { field: availableFields[0]?.name ?? '', func: 'count', alias: '' }])
  }

  function updateAgg(i: number, key: keyof AggregationEntry, val: string) {
    setAggregations(prev => prev.map((a, idx) => idx === i ? { ...a, [key]: val } : a))
  }

  function addFilter() {
    setFilters(prev => [...prev, { field: '', operator: OPERADOR_POR_DEFECTO, value: '' }])
  }

  function updateFilter(i: number, key: keyof FilterEntry, val: string) {
    setFilters(prev => prev.map((f, idx) => idx === i ? { ...f, [key]: val } : f))
  }

  function removeFilter(i: number) {
    setFilters(prev => prev.filter((_, idx) => idx !== i))
  }

  return (
    <div className="biqubupa-txt-1">
      {/* Header */}
      <div className="biqubupa-ps2">
        <div>
          <div className="biqubupa-txt-2">{traducir('biquerybuilder.query_builder_visual')}</div>
          <div className="biqubupa-box-1">
            {traducir('biquerybuilder.construye_consultas_bi_sin_sql_de_forma')}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        items={[
          { id: 'builder', label: traducir('biquerybuilder.tab_constructor'), icon: <Hammer size={14} /> },
          { id: 'saved',   label: traducir('biquerybuilder.tab_guardadas'), icon: <FolderOpen size={14} />, count: savedQueries.length },
          { id: 'results', label: traducir('biquerybuilder.tab_resultados'), icon: <Table2 size={14} /> },
        ]}
        active={tab}
        onChange={setTab}
        className="biqubupa-tabs"
      />

      {/* ─── BUILDER TAB ─────────────────────────────────────────────────── */}
      {tab === 'builder' && (
        <div>
          {/* Dataset selector */}
          <div className="biqubupa-ps">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="biqubupa-ls">{traducir('biquerybuilder.conjunto_de_datos')}</label>
            <Select suelto id={`${idCampo}-1`} className="biqubupa-is" value={dataset} onChange={e => { setDataset(e.target.value); setSelectedFields([]); setGroupBy([]) }} placeholder={traducir('biquerybuilder.seleccionar_dataset')}>
              {datasets.map(d => <option key={d.name} value={d.name}>{d.label ?? d.name}</option>)}
            </Select>
          </div>

          {dataset && (
            <>
              {/* Fields */}
              <div className="biqubupa-ps">
                <div className="biqubupa-box-2">{traducir('constructor_informes_ui.campos_incluir')}</div>
                <div className="u-wrap-8">
                  {availableFields.map(f => (
                    <Button key={f.name} size="sm" variant={selectedFields.includes(f.name) ? 'primary' : 'secondary'} onClick={() => toggleField(f.name)}>
                      {f.label ?? f.name}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Filters */}
              <div className="biqubupa-ps">
                <div className="biqubupa-row-2">
                  <span className="u-base-600">{traducir('visual_query_builder.filters')}</span>
                  <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={addFilter}>{traducir('biquerybuilder.anadir_filtro')}</Button>
                </div>
                {filters.map((f, i) => (
                  <div key={i} className="biqubupa-row-3">
                    <Select suelto className="biqubupa-is2" value={f.field} onChange={e => updateFilter(i, 'field', e.target.value)} placeholder={traducir('constructor_informes_ui.campo')}>
                      {availableFields.map(af => <option key={af.name} value={af.name}>{af.label ?? af.name}</option>)}
                    </Select>
                    <Select suelto className="biqubupa-is3" value={f.operator} onChange={e => updateFilter(i, 'operator', e.target.value)} placeholder={false}>
                      {Object.entries(operadores).map(([op, def]) => <option key={op} value={op}>{def.label}</option>)}
                    </Select>
                    <Input aria-label={traducir('pol.valor')} placeholder={NULL_OPS.has(f.operator) ? traducir('biquerybuilder.no_aplica') : traducir('biquerybuilder.valor')} value={f.value} disabled={NULL_OPS.has(f.operator)} onChange={e => updateFilter(i, 'value', e.target.value)} className="biqubupa-is2" />
                    <IconButton className="biqubupa-del" ariaLabel={traducir('biquerybuilder.quitar')} onClick={() => removeFilter(i)}><X size={14} /></IconButton>
                  </div>
                ))}
              </div>

              {/* Group by + Aggregations */}
              <div className="biqubupa-ps">
                <div className="biqubupa-box-2">{traducir('biquerybuilder.agrupar_por')}</div>
                <div className="biqubupa-row-4">
                  {availableFields.map(f => (
                    <Button key={f.name} size="sm" variant={groupBy.includes(f.name) ? 'primary' : 'secondary'} onClick={() => toggleGroupBy(f.name)}>
                      {f.label ?? f.name}
                    </Button>
                  ))}
                </div>
                <div className="biqubupa-row-5">
                  <span className="u-base-600">{traducir('biquerybuilder.agregaciones')}</span>
                  <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={addAgg}>{traducir('biquerybuilder.anadir')}</Button>
                </div>
                {aggregations.map((a, i) => (
                  <div key={i} className="biqubupa-row-6">
                    <Select suelto className="biqubupa-is4" value={a.field} onChange={e => updateAgg(i, 'field', e.target.value)} placeholder={false}>
                      {availableFields.map(af => <option key={af.name} value={af.name}>{af.label ?? af.name}</option>)}
                    </Select>
                    <Select suelto className="biqubupa-is5" value={a.func} onChange={e => updateAgg(i, 'func', e.target.value)} placeholder={false}>
                      {agregaciones.map(fn => <option key={fn} value={fn}>{etiquetaCodigo(traducir, 'biquerybuilder.agg', fn)}</option>)}
                    </Select>
                    <Input aria-label={traducir('biquerybuilder.alias_opcional')} placeholder={traducir('biquerybuilder.alias_opcional')} value={a.alias} onChange={e => updateAgg(i, 'alias', e.target.value)} className="biqubupa-is6" />
                    <IconButton className="biqubupa-del" ariaLabel={traducir('biquerybuilder.quitar')}
                      onClick={() => setAggregations(prev => prev.filter((_, idx) => idx !== i))}><X size={14} /></IconButton>
                  </div>
                ))}
              </div>

              {/* Sort + Limit */}
              <div className="biqubupa-ps3">
                <div className="biqubupa-box-3">
                  <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="biqubupa-ls">{traducir('biquerybuilder.ordenar_por')}</label>
                  <Select suelto id={`${idCampo}-2`} className="biqubupa-is" value={sortBy} onChange={e => setSortBy(e.target.value)} placeholder={traducir('biquerybuilder.sin_orden')}>
                    {availableFields.map(f => <option key={f.name} value={f.name}>{f.label ?? f.name}</option>)}
                  </Select>
                </div>
                <div className="biqubupa-box-4">
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="biqubupa-ls">{traducir('biquerybuilder.direccion')}</label>
                  <Select suelto id={`${idCampo}-3`} className="biqubupa-is" value={sortDir} onChange={e => setSortDir(e.target.value)} placeholder={false}>
                    <option value="asc">{traducir('biquerybuilder.asc')}</option>
                    <option value="desc">{traducir('biquerybuilder.desc')}</option>
                  </Select>
                </div>
                <div className="biqubupa-box-4">
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="biqubupa-ls">{traducir('biquerybuilder.limite')}</label>
                  <Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={limit} min={1} max={5000} onChange={e => setLimit(Number(e.target.value))} inputClassName="biqubupa-is" />
                </div>
              </div>

              {/* Save name + Run */}
              <div className="biqubupa-row-7">
                <div className="biqubupa-box-5">
                  <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="biqubupa-ls">{traducir('biquerybuilder.nombre_de_la_query_requerido_para_guardar')}</label>
                  <Input id={`${idCampo}-5`} placeholder={traducir('biquerybuilder.mi_query')} value={queryName} onChange={e => setQueryName(e.target.value)} inputClassName="biqubupa-is" />
                </div>
                <Button variant="secondary" icon={<Save size={14} />} onClick={handleSaveBuilder}
                  disabled={!dataset || !queryName.trim() || saveMut.isPending} loading={saveMut.isPending}>
                  {saveMut.isPending ? traducir('biquerybuilder.guardando') : traducir('biquerybuilder.guardar')}
                </Button>
                <Button icon={<Play size={14} />} onClick={handleRunBuilder}
                  disabled={!dataset || previewMut.isPending || execSavedMut.isPending} loading={previewMut.isPending || execSavedMut.isPending}>
                  {previewMut.isPending || execSavedMut.isPending ? traducir('biquerybuilder.ejecutando') : traducir('biquerybuilder.ejecutar')}
                </Button>
              </div>
              {execError && <div className="biqubupa-box-6">{execError}</div>}
            </>
          )}
        </div>
      )}

      {/* ─── SAVED QUERIES TAB ───────────────────────────────────────────── */}
      {tab === 'saved' && (
        <div>
          {savedQueries.length === 0 ? (
            <EmptyState icon={<FolderOpen size={28} />} title={traducir('biquerybuilder.no_hay_queries_guardadas_todavia_crea_una')} />
          ) : (
            <div className="u-stack-10">
              {savedQueries.map(q => (
                <div key={q.id} className="biqubupa-ps4">
                  <div className="u-min0">
                    <div className="u-md-600">{q.name}</div>
                    <div className="u-text3-sm">
                      {traducir('biquerybuilder.dataset')} <b>{q.dataset}</b> {traducir('biquerybuilder.campos')} {(q.fields ?? []).join(', ') || '—'}
                    </div>
                  </div>
                  <div className="u-row-8">
                    <Button size="sm" variant="secondary" onClick={() => loadSavedQuery(q)}>{traducir('biquerybuilder.cargar')}</Button>
                    <Button size="sm" icon={<Play size={14} />} onClick={() => execSavedMut.mutate(q.id)}
                      disabled={execSavedMut.isPending}>{traducir('biquerybuilder.ejecutar')}</Button>
                    <IconButton variante="caja" tono="peligro" ariaLabel={traducir('biquerybuilder.eliminar')} onClick={async () => { if (await confirmar({ message: traducir('biquerybuilder.confirmar_eliminar_consulta'), danger: true, confirmLabel: traducir('biquerybuilder.eliminar') })) deleteMut.mutate(q.id) }}><Trash2 size={14} /></IconButton>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── RESULTS TAB ─────────────────────────────────────────────────── */}
      {tab === 'results' && (
        <div>
          {!results ? (
            <EmptyState icon={<Table2 size={28} />} title={traducir('biquerybuilder.ejecuta_una_query_para_ver_resultados')} />
          ) : (
            <div>
              <div className="biqubupa-box-8">
                {results.row_count} {traducir('biquerybuilder.registros_dataset')} {results.dataset}
                {results.truncated ? ` ${traducir('biquerybuilder.limitados_a', { n: results.row_count })}` : ''}
              </div>
              {results.incompleto && (
                <div role="alert" className="biqubupa-box-9">
                  {traducir('biquerybuilder.totales_parciales', { leidas: fmtNumber(results.filas_leidas, 0), totales: fmtNumber(results.filas_totales, 0) })}
                </div>
              )}
              <div className="u-scroll-x">
                <Table
                  data={results.rows.slice(0, 200)}
                  columns={results.columns.map(col => ({
                    key: col,
                    label: <span className="biqubupa-txt-3">{col}</span>,
                    render: (_v: never, row: Record<string, unknown>) => (row[col] == null ? <span className="biqubupa-txt-4">{traducir('biquerybuilder.sin_valor')}</span> : String(row[col])),
                  }))}
                />
                {results.rows.length > 200 && (
                  <div className="biqubupa-box-10">
                    {traducir('biquerybuilder.mostrando_200_de_n', { n: results.rows.length })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
