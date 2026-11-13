import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { biIntelligenceApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { Table } from '../ui'

// TODO type: biIntelligenceApi.queryBuilderSchema payload — needs shared type
interface ColumnDef {
  type?: string
  label?: string
  [k: string]: unknown
}

interface EntityDef {
  columns?: Record<string, ColumnDef>
  group?: string
  label?: string
  [k: string]: unknown
}

interface OperatorDef {
  label?: string
  [k: string]: unknown
}

interface BuilderSchema {
  entities?: Record<string, EntityDef>
  operators?: Record<string, OperatorDef>
  groups?: Record<string, string>
}

interface FilterEntry {
  column: string
  operator: string
  value: string
}

interface QueryTemplate {
  id: string | number
  name: string
  query?: {
    entity?: string
    columns?: unknown[]
    filters?: Array<{ column?: string; operator?: string; value?: unknown }>
    sort?: { column?: string; direction?: string }
  }
  [k: string]: unknown
}

interface PreviewResponse {
  rows?: Array<Record<string, unknown>>
  columns?: string[]
  count?: number
  truncated?: boolean
}

const EMPTY_FILTER: FilterEntry = { column: '', operator: 'eq', value: '' }
const NULL_OPS = new Set(['is_null', 'is_not_null'])

function RowTable({ rows = [], columns = [] }: { rows?: Array<Record<string, unknown>>; columns?: string[] }) {
  if (!rows.length || !columns.length) return null
  return (
    <div style={{ overflowX: 'auto', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
      <Table
        data={rows}
        columns={columns.map((c) => ({
          key: c,
          label: c,
          render: (_v: never, row: Record<string, unknown>) => (row?.[c] == null ? '—' : String(row[c])),
        }))}
      />
    </div>
  )
}

export default function VisualQueryBuilderWidget() {
  const t = useAppT()
  const [entity, setEntity] = useState<string>('projects')
  const [selectedColumns, setSelectedColumns] = useState<string[]>([])
  const [filters, setFilters] = useState<FilterEntry[]>([])
  const [sortColumn, setSortColumn] = useState<string>('')
  const [sortDirection, setSortDirection] = useState<string>('asc')
  const [templateName, setTemplateName] = useState<string>('')

  const schemaQuery = useQuery<BuilderSchema>({
    queryKey: ['bi-intelligence-query-builder-schema'],
    queryFn: () => biIntelligenceApi.queryBuilderSchema().then((r) => r.data),
    staleTime: 5 * 60_000,
  })

  const previewMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => biIntelligenceApi.queryBuilderPreview(payload).then((r) => r.data as PreviewResponse),
  })

  const templatesQuery = useQuery<{ items?: QueryTemplate[] } | QueryTemplate[]>({
    queryKey: ['bi-intelligence-query-builder-templates'],
    queryFn: () => biIntelligenceApi.queryBuilderTemplates().then((r) => r.data),
  })

  const saveTemplateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => biIntelligenceApi.saveQueryBuilderTemplate(payload).then((r) => r.data),
    onSuccess: () => {
      setTemplateName('')
      templatesQuery.refetch()
    },
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: (id: QueryTemplate['id']) => biIntelligenceApi.deleteQueryBuilderTemplate(id).then((r) => r.data),
    onSuccess: () => templatesQuery.refetch(),
  })

  const entities = useMemo(() => schemaQuery.data?.entities || {}, [schemaQuery.data])
  const operators = useMemo(() => schemaQuery.data?.operators || {}, [schemaQuery.data])
  const groups = useMemo(() => schemaQuery.data?.groups || {}, [schemaQuery.data])
  const templateItems = useMemo<QueryTemplate[]>(() => {
    const data = templatesQuery.data
    if (!data) return []
    return Array.isArray(data) ? data : (data.items || [])
  }, [templatesQuery.data])

  const entityDef = entity ? entities[entity] : null
  const allColumns = useMemo(() => Object.keys(entityDef?.columns || {}), [entityDef])
  const effectiveColumns = selectedColumns.length ? selectedColumns : allColumns
  const validOperators = useMemo(() => new Set(Object.keys(operators || {})), [operators])

  const groupedEntities = useMemo(() => {
    const acc: Record<string, Array<{ key: string; label: string }>> = {}
    ;(Object.entries(entities) as Array<[string, EntityDef]>).forEach(([key, cfg]) => {
      const g = cfg.group || 'other'
      if (!acc[g]) acc[g] = []
      acc[g].push({ key, label: cfg.label || key })
    })
    return acc
  }, [entities])

  const sortedGroupKeys = useMemo(() => {
    const preferred = Object.keys(groups)
    const dynamic = Object.keys(groupedEntities)
    return [...preferred.filter((k) => dynamic.includes(k)), ...dynamic.filter((k) => !preferred.includes(k))]
  }, [groups, groupedEntities])

  const addFilter = () => setFilters((prev) => [...prev, { ...EMPTY_FILTER }])
  const removeFilter = (i: number) => setFilters((prev) => prev.filter((_, idx) => idx !== i))
  const patchFilter = (i: number, patch: Partial<FilterEntry>) => {
    setFilters((prev) => prev.map((f, idx) => (idx === i ? { ...f, ...patch } : f)))
  }

  const toggleColumn = (col: string) => {
    setSelectedColumns((prev) => (prev.includes(col) ? prev.filter((x) => x !== col) : [...prev, col]))
  }

  const buildQueryPayload = () => {
    const validColumns = new Set(allColumns)
    const columns = effectiveColumns.filter((c) => validColumns.has(c))

    const normalizedFilters = filters
      .filter((f) => validColumns.has(f.column) && validOperators.has(f.operator))
      .map((f) => {
        if (NULL_OPS.has(f.operator)) {
          return { column: f.column, operator: f.operator, value: null }
        }
        if (f.operator === 'in') {
          const raw = Array.isArray(f.value) ? f.value : String(f.value || '').split(',')
          const list = raw.map((x) => String(x).trim()).filter(Boolean)
          return { column: f.column, operator: f.operator, value: list }
        }
        return {
          column: f.column,
          operator: f.operator,
          value: f.value == null ? '' : String(f.value),
        }
      })
      .filter((f) => NULL_OPS.has(f.operator) || (f.operator === 'in' ? (f.value?.length ?? 0) > 0 : (f.value ?? '') !== ''))

    const sort = validColumns.has(sortColumn)
      ? { column: sortColumn, direction: sortDirection }
      : null

    return {
      entity,
      columns,
      filters: normalizedFilters,
      sort,
      limit: 100,
    }
  }

  const saveTemplate = () => {
    const name = templateName.trim()
    if (!name || !entity) return
    saveTemplateMutation.mutate({
      name,
      query: buildQueryPayload(),
    })
  }

  const loadTemplate = (item: QueryTemplate) => {
    const q = item?.query || {}
    setEntity(q.entity || 'projects')
    const templateColumns = Array.isArray(q.columns) ? q.columns.filter((c) => typeof c === 'string') : []
    setSelectedColumns(templateColumns)
    const templateFilters: FilterEntry[] = Array.isArray(q.filters)
      ? q.filters
        .filter((f) => f && typeof f.column === 'string' && typeof f.operator === 'string')
        .map((f) => ({ column: String(f.column), operator: String(f.operator), value: f.value == null ? '' : String(f.value) }))
      : []
    setFilters(templateFilters)
    setSortColumn(q.sort?.column || '')
    setSortDirection(q.sort?.direction || 'asc')
  }

  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--surface-4)' }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)' }}>{t('visual_query_builder.title')}</div>
        <div className="u-text3-2xs">{t('visual_query_builder.subtitle')}</div>
      </div>

      <div style={{ padding: '14px 20px', display: 'grid', gap: 10 }}>
        <select
          value={entity}
          onChange={(e) => {
            setEntity(e.target.value)
            setSelectedColumns([])
            setFilters([])
            setSortColumn('')
          }}
          style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 10px', fontSize: "var(--text-sm)" }}
        >
          <option value="">{t('visual_query_builder.entity_placeholder')}</option>
          {sortedGroupKeys.map((g) => (
            <optgroup key={g} label={groups[g] || g}>
              {(groupedEntities[g] || []).map((item) => (
                <option key={item.key} value={item.key}>{item.label}</option>
              ))}
            </optgroup>
          ))}
        </select>

        {!!entityDef && (
          <>
            <div style={{ display: 'grid', gap: 6, gridTemplateColumns: '1fr auto', alignItems: 'center' }}>
              <input aria-label={t('visual_query_builder.template_placeholder')}
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                placeholder={t('visual_query_builder.template_placeholder')}
                style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '7px 9px', fontSize: "var(--text-sm)" }}
              />
              <button
                type="button"
                onClick={saveTemplate}
                disabled={saveTemplateMutation.isPending || !templateName.trim()}
                style={{ border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-2)', borderRadius: 7, padding: '7px 10px', fontSize: "var(--text-xs)", cursor: 'pointer' }}
              >
                {saveTemplateMutation.isPending ? t('visual_query_builder.saving') : t('visual_query_builder.save')}
              </button>
            </div>

            {!!templateItems.length && (
              <div style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8, maxHeight: 120, overflowY: 'auto' }}>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 6 }}>{t('visual_query_builder.saved_templates')}</div>
                <div style={{ display: 'grid', gap: 4 }}>
                  {templateItems.map((item) => (
                    <div key={item.id} className="u-row-center-6">
                      <button
                        type="button"
                        onClick={() => loadTemplate(item)}
                        style={{ flex: 1, textAlign: 'left', border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-2)', borderRadius: 'var(--radius-sm)', padding: '5px 8px', fontSize: "var(--text-xs)", cursor: 'pointer' }}
                      >
                        {item.name}
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteTemplateMutation.mutate(item.id)}
                        style={{ border: 'none', background: 'transparent', color: 'var(--danger)', fontSize: "var(--text-xs)", cursor: 'pointer' }}
                      >
                        {t('visual_query_builder.delete_btn')}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8, maxHeight: 130, overflowY: 'auto' }}>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 6 }}>{t('visual_query_builder.columns')}</div>
              <div style={{ display: 'grid', gap: 4 }}>
                {allColumns.map((col) => (
                  <label key={col} style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', display: 'flex', alignItems: 'center', gap: 7 }}>
                    <input type="checkbox" checked={selectedColumns.includes(col)} onChange={() => toggleColumn(col)} />
                    {entityDef.columns?.[col]?.label || col}
                  </label>
                ))}
              </div>
            </div>

            <div style={{ display: 'grid', gap: 7 }}>
              <div className="u-row-between">
                <span className="u-text3-xs">{t('visual_query_builder.filters')}</span>
                <button
                  type="button"
                  onClick={addFilter}
                  style={{ border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-2)', borderRadius: 7, fontSize: "var(--text-xs)", padding: '4px 8px', cursor: 'pointer' }}
                >
                  {t('visual_query_builder.add_filter')}
                </button>
              </div>
              {filters.map((f, i) => (
                <div key={i} style={{ display: 'grid', gap: 6, gridTemplateColumns: '1.2fr 1fr 1fr auto' }}>
                  <select value={f.column} onChange={(e) => patchFilter(i, { column: e.target.value })} style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: "var(--text-sm)" }}>
                    <option value="">{t('visual_query_builder.field_placeholder')}</option>
                    {allColumns.map((c) => <option key={c} value={c}>{entityDef.columns?.[c]?.label || c}</option>)}
                  </select>
                  <select value={f.operator} onChange={(e) => patchFilter(i, { operator: e.target.value })} style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: "var(--text-sm)" }}>
                    {(Object.entries(operators) as Array<[string, OperatorDef]>).map(([k, op]) => <option key={k} value={k}>{op?.label || k}</option>)}
                  </select>
                  <input
                    value={f.value}
                    disabled={NULL_OPS.has(f.operator)}
                    onChange={(e) => patchFilter(i, { value: e.target.value })}
                    placeholder={NULL_OPS.has(f.operator) ? t('visual_query_builder.n_a') : t('visual_query_builder.value_placeholder')}
                    style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: "var(--text-sm)" }}
                  />
                  <button type="button" onClick={() => removeFilter(i)} style={{ border: 'none', background: 'transparent', color: 'var(--text-3)', cursor: 'pointer' }}>x</button>
                </div>
              ))}
            </div>

            <div style={{ display: 'grid', gap: 7, gridTemplateColumns: '1fr 120px auto' }}>
              <select
                value={sortColumn}
                onChange={(e) => setSortColumn(e.target.value)}
                style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: "var(--text-sm)" }}
              >
                <option value="">{t('visual_query_builder.no_sort')}</option>
                {allColumns.map((c) => <option key={c} value={c}>{entityDef.columns?.[c]?.label || c}</option>)}
              </select>
              <select
                value={sortDirection}
                onChange={(e) => setSortDirection(e.target.value)}
                style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: "var(--text-sm)" }}
              >
                <option value="asc">{t('visual_query_builder.asc')}</option>
                <option value="desc">{t('visual_query_builder.desc')}</option>
              </select>
              <button
                type="button"
                onClick={() => previewMutation.mutate(buildQueryPayload())}
                disabled={previewMutation.isPending}
                style={{ border: 'none', background: 'var(--accent)', color: 'var(--on-accent)', borderRadius: 8, padding: '7px 12px', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer' }}
              >
                {previewMutation.isPending ? t('visual_query_builder.loading') : t('visual_query_builder.preview')}
              </button>
            </div>
          </>
        )}

        {previewMutation.isError && (
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--danger)' }}>{t('visual_query_builder.error')}</div>
        )}

        {previewMutation.data && (
          <div style={{ display: 'grid', gap: 8 }}>
            <div className="u-text3-xs">
              {previewMutation.data.count} {t('visual_query_builder.results')}
              {previewMutation.data.truncated ? ` ${t('visual_query_builder.truncated')}` : ''}
            </div>
            <RowTable rows={previewMutation.data.rows || []} columns={previewMutation.data.columns || []} />
          </div>
        )}
      </div>
    </div>
  )
}
