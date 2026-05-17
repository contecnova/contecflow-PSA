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

const TABS = [
  { id: 'builder', label: '🔧 Constructor' },
  { id: 'saved',   label: '📁 Guardadas'  },
  { id: 'results', label: '📊 Resultados' },
]

const ps: React.CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 20, marginBottom: 16 }
const ls: React.CSSProperties = { display: 'block', fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 4, fontWeight: 500 }
const is: React.CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '7px 10px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', boxSizing: 'border-box' }
const btn = (accent: boolean): React.CSSProperties => ({ padding: '7px 16px', borderRadius: 6, border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: "var(--text-base)", fontWeight: 600, background: accent ? 'var(--accent)' : 'var(--surface-3)', color: accent ? '#fff' : 'var(--text-1)' })

// TODO type: biQueryBuilderApi schema/payload — needs shared type
interface DatasetField {
  name: string
  label?: string
  type?: string
  [k: string]: unknown
}

interface DatasetMeta {
  name: string
  label?: string
  fields: DatasetField[]
  [k: string]: unknown
}

interface Schema {
  datasets?: DatasetMeta[]
}

interface FilterEntry {
  field: string
  operator: string
  value: string
}

interface AggregationEntry {
  func: string
  field: string
  alias?: string
}

interface SavedQuery {
  id: string | number
  name: string
  dataset?: string
  fields?: string[]
  filters?: Array<{ field?: string; operator?: string; value?: string | null }>
  group_by?: string[]
  aggregations?: AggregationEntry[]
  sort_by?: string
  sort_dir?: string
  limit?: number
  [k: string]: unknown
}

interface QueryResult {
  columns?: string[]
  rows?: Array<Record<string, unknown>>
  row_count?: number
  dataset?: string
  truncated?: boolean
  [k: string]: unknown
}

const errorMessage = (e: unknown, fallback: string): string => {
  return (e as { message?: string })?.message || fallback
}

const OPERATORS = ['=', '!=', '>', '>=', '<', '<=', 'contains', 'starts_with', 'is_null', 'is_not_null']
const AGG_FUNCS  = ['count', 'sum', 'avg', 'min', 'max']
const NULL_OPS = new Set(['is_null', 'is_not_null'])

export default function BiQueryBuilderPanel() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<string>('builder')
  const [results, setResults] = useState<QueryResult | null>(null)
  const [execError, setExecError] = useState<string | null>(null)

  // ── Schema ────────────────────────────────────────────────────────────────
  const { data: schema } = useQuery<Schema>({
    queryKey: ['bi-qb-schema'],
    queryFn: () => biQueryBuilderApi.getSchema({}).then((r) => r.data as Schema),
    staleTime: 60_000,
  })

  const datasets = useMemo<DatasetMeta[]>(() => schema?.datasets ?? [], [schema])

  // ── Saved queries ─────────────────────────────────────────────────────────
  const { data: savedData } = useQuery<{ items?: SavedQuery[] }>({
    queryKey: ['bi-qb-queries'],
    queryFn: () => biQueryBuilderApi.listQueries().then((r) => r.data as { items?: SavedQuery[] }),
  })
  const savedQueries: SavedQuery[] = savedData?.items ?? []

  // ── Builder state ─────────────────────────────────────────────────────────
  const [dataset, setDataset] = useState<string>('')
  const [selectedFields, setSelectedFields] = useState<string[]>([])
  const [filters, setFilters] = useState<FilterEntry[]>([{ field: '', operator: '=', value: '' }])
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

  const previewMut = useMutation<QueryResult, unknown, Record<string, unknown>>({
    mutationFn: (payload) => biQueryBuilderApi.previewQuery(payload).then((r) => r.data as QueryResult),
    onSuccess: (data) => { setResults(data); setTab('results') },
    onError: (e) => setExecError(errorMessage(e, 'Error ejecutando preview')),
  })

  const execSavedMut = useMutation<QueryResult, unknown, string | number>({
    mutationFn: (id) => biQueryBuilderApi.executeQuery(id).then((r) => r.data as QueryResult),
    onSuccess: (data) => { setResults(data); setTab('results') },
    onError: (e) => setExecError(errorMessage(e, 'Error ejecutando query')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string | number) => biQueryBuilderApi.deleteQuery(id).then((r) => r.data),
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

  function loadSavedQuery(q: SavedQuery) {
    setDataset(q.dataset || '')
    setSelectedFields(q.fields || [])
    setFilters((q.filters || []).map((f) => ({
      field: f.field || '',
      operator: f.operator || '=',
      value: f.value ?? '',
    })))
    setGroupBy(q.group_by || [])
    setAggregations(q.aggregations || [])
    setSortBy(q.sort_by || '')
    setSortDir(q.sort_dir || 'desc')
    setLimit(Number(q.limit || 100))
    setQueryName(q.name || '')
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
    setFilters(prev => [...prev, { field: '', operator: '=', value: '' }])
  }

  function updateFilter(i: number, key: keyof FilterEntry, val: string) {
    setFilters(prev => prev.map((f, idx) => idx === i ? { ...f, [key]: val } : f))
  }

  function removeFilter(i: number) {
    setFilters(prev => prev.filter((_, idx) => idx !== i))
  }

  return (
    <div style={{ fontFamily: 'inherit' }}>
      {/* Header */}
      <div style={{ ...ps, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px' }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: "var(--text-lg)" }}>🔧 Query Builder Visual</div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 2 }}>
            Construye consultas BI sin SQL de forma visual
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, borderBottom: '1px solid var(--surface-4)', paddingBottom: 0 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding: '7px 16px', fontSize: "var(--text-base)", fontWeight: tab === t.id ? 700 : 400,
              color: tab === t.id ? 'var(--accent)' : 'var(--text-2)', background: 'transparent',
              border: 'none', borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
              cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ─── BUILDER TAB ─────────────────────────────────────────────────── */}
      {tab === 'builder' && (
        <div>
          {/* Dataset selector */}
          <div style={ps}>
            <label style={ls}>Dataset</label>
            <select style={is} value={dataset} onChange={e => { setDataset(e.target.value); setSelectedFields([]); setGroupBy([]) }}>
              <option value="">Seleccionar dataset…</option>
              {datasets.map(d => <option key={d.name} value={d.name}>{d.label ?? d.name}</option>)}
            </select>
          </div>

          {dataset && (
            <>
              {/* Fields */}
              <div style={ps}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginBottom: 10 }}>Campos a incluir</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {availableFields.map(f => (
                    <button key={f.name} onClick={() => toggleField(f.name)}
                      style={{ ...btn(selectedFields.includes(f.name)), padding: '5px 12px', fontSize: "var(--text-sm)" }}>
                      {f.label ?? f.name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Filters */}
              <div style={ps}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>Filtros</span>
                  <button style={btn(false)} onClick={addFilter}>+ Añadir filtro</button>
                </div>
                {filters.map((f, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <select style={{ ...is, flex: '1 1 140px' }} value={f.field} onChange={e => updateFilter(i, 'field', e.target.value)}>
                      <option value="">Campo…</option>
                      {availableFields.map(af => <option key={af.name} value={af.name}>{af.label ?? af.name}</option>)}
                    </select>
                    <select style={{ ...is, flex: '0 0 110px' }} value={f.operator} onChange={e => updateFilter(i, 'operator', e.target.value)}>
                      {OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                    </select>
                    <input style={{ ...is, flex: '1 1 140px' }} placeholder={NULL_OPS.has(f.operator) ? 'N/A' : 'Valor'} value={f.value}
                      disabled={NULL_OPS.has(f.operator)}
                      onChange={e => updateFilter(i, 'value', e.target.value)} />
                    <button style={{ ...btn(false), padding: '5px 10px', color: 'var(--danger)' }} onClick={() => removeFilter(i)}>✕</button>
                  </div>
                ))}
              </div>

              {/* Group by + Aggregations */}
              <div style={ps}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginBottom: 10 }}>Agrupar por</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                  {availableFields.map(f => (
                    <button key={f.name} onClick={() => toggleGroupBy(f.name)}
                      style={{ ...btn(groupBy.includes(f.name)), padding: '4px 10px', fontSize: "var(--text-sm)" }}>
                      {f.label ?? f.name}
                    </button>
                  ))}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>Agregaciones</span>
                  <button style={btn(false)} onClick={addAgg}>+ Añadir</button>
                </div>
                {aggregations.map((a, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    <select style={{ ...is, flex: '1 1 130px' }} value={a.field} onChange={e => updateAgg(i, 'field', e.target.value)}>
                      {availableFields.map(af => <option key={af.name} value={af.name}>{af.label ?? af.name}</option>)}
                    </select>
                    <select style={{ ...is, flex: '0 0 90px' }} value={a.func} onChange={e => updateAgg(i, 'func', e.target.value)}>
                      {AGG_FUNCS.map(fn => <option key={fn} value={fn}>{fn}</option>)}
                    </select>
                    <input style={{ ...is, flex: '1 1 110px' }} placeholder="Alias (opcional)" value={a.alias}
                      onChange={e => updateAgg(i, 'alias', e.target.value)} />
                    <button style={{ ...btn(false), color: 'var(--danger)', padding: '5px 10px' }}
                      onClick={() => setAggregations(prev => prev.filter((_, idx) => idx !== i))}>✕</button>
                  </div>
                ))}
              </div>

              {/* Sort + Limit */}
              <div style={{ ...ps, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 160px' }}>
                  <label style={ls}>Ordenar por</label>
                  <select style={is} value={sortBy} onChange={e => setSortBy(e.target.value)}>
                    <option value="">Sin orden</option>
                    {availableFields.map(f => <option key={f.name} value={f.name}>{f.label ?? f.name}</option>)}
                  </select>
                </div>
                <div style={{ flex: '0 0 100px' }}>
                  <label style={ls}>Dirección</label>
                  <select style={is} value={sortDir} onChange={e => setSortDir(e.target.value)}>
                    <option value="asc">ASC ↑</option>
                    <option value="desc">DESC ↓</option>
                  </select>
                </div>
                <div style={{ flex: '0 0 100px' }}>
                  <label style={ls}>Límite</label>
                  <input type="number" style={is} value={limit} min={1} max={5000}
                    onChange={e => setLimit(Number(e.target.value))} />
                </div>
              </div>

              {/* Save name + Run */}
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 200px' }}>
                  <label style={ls}>Nombre de la query (requerido para guardar)</label>
                  <input style={is} placeholder="Mi query…" value={queryName}
                    onChange={e => setQueryName(e.target.value)} />
                </div>
                <button style={btn(false)} onClick={handleSaveBuilder}
                  disabled={!dataset || !queryName.trim() || saveMut.isPending}>
                  {saveMut.isPending ? 'Guardando…' : '💾 Guardar'}
                </button>
                <button style={btn(true)} onClick={handleRunBuilder}
                  disabled={!dataset || previewMut.isPending || execSavedMut.isPending}>
                  {previewMut.isPending || execSavedMut.isPending ? 'Ejecutando…' : '▶ Ejecutar'}
                </button>
              </div>
              {execError && <div style={{ color: 'var(--danger)', fontSize: "var(--text-sm)", marginTop: 8 }}>{execError}</div>}
            </>
          )}
        </div>
      )}

      {/* ─── SAVED QUERIES TAB ───────────────────────────────────────────── */}
      {tab === 'saved' && (
        <div>
          {savedQueries.length === 0 ? (
            <div style={{ color: 'var(--text-3)', fontSize: "var(--text-base)", textAlign: 'center', padding: 40 }}>
              No hay queries guardadas todavía. Crea una en el constructor.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {savedQueries.map(q => (
                <div key={q.id} style={{ ...ps, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "var(--text-md)" }}>{q.name}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
                      Dataset: <b>{q.dataset}</b> · Campos: {(q.fields ?? []).join(', ') || '—'}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button style={btn(false)} onClick={() => loadSavedQuery(q)}>✎ Cargar</button>
                    <button style={btn(true)} onClick={() => execSavedMut.mutate(q.id)}
                      disabled={execSavedMut.isPending}>▶ Ejecutar</button>
                    <button style={{ ...btn(false), color: 'var(--danger)' }} onClick={() => deleteMut.mutate(q.id)}>🗑</button>
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
            <div style={{ color: 'var(--text-3)', fontSize: "var(--text-base)", textAlign: 'center', padding: 40 }}>
              Ejecuta una query para ver resultados.
            </div>
          ) : (
            <div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginBottom: 12 }}>
                {results.row_count ?? results.rows?.length ?? 0} registros · dataset: {results.dataset ?? '—'}
                {results.truncated ? ` · limitados a ${results.row_count}` : ''}
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
                      {(results.columns ?? []).map(col => (
                        <th key={col} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-2)', fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(results.rows ?? []).slice(0, 200).map((row, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid var(--surface-4)', background: i % 2 === 0 ? 'transparent' : 'var(--surface-2)' }}>
                        {(results.columns ?? []).map(col => (
                          <td key={col} style={{ padding: '7px 12px', color: 'var(--text-1)' }}>
                            {row[col] == null ? <span style={{ color: 'var(--text-4)' }}>null</span> : String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {results.rows?.length > 200 && (
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 8, textAlign: 'center' }}>
                    Mostrando 200 de {results.rows.length} filas
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
