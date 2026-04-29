import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { biIntelligenceApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'

const EMPTY_FILTER = { column: '', operator: 'eq', value: '' }
const NULL_OPS = new Set(['is_null', 'is_not_null'])

function RowTable({ rows = [], columns = [] }) {
  if (!rows.length || !columns.length) return null
  return (
    <div style={{ overflowX: 'auto', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: 'var(--surface-3)' }}>
            {columns.map((c) => (
              <th
                key={c}
                style={{
                  textAlign: 'left',
                  padding: '8px 10px',
                  color: 'var(--text-2)',
                  borderBottom: '1px solid var(--surface-4)',
                }}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid var(--surface-4)' }}>
              {columns.map((c) => (
                <td key={c} style={{ padding: '7px 10px', color: 'var(--text-1)' }}>
                  {row?.[c] == null ? '—' : String(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function VisualQueryBuilderWidget() {
  const t = useAppT()
  const [entity, setEntity] = useState('projects')
  const [selectedColumns, setSelectedColumns] = useState([])
  const [filters, setFilters] = useState([])
  const [sortColumn, setSortColumn] = useState('')
  const [sortDirection, setSortDirection] = useState('asc')
  const [templateName, setTemplateName] = useState('')

  const schemaQuery = useQuery({
    queryKey: ['bi-intelligence-query-builder-schema'],
    queryFn: () => biIntelligenceApi.queryBuilderSchema().then((r) => r.data),
    staleTime: 5 * 60_000,
  })

  const previewMutation = useMutation({
    mutationFn: (payload) => biIntelligenceApi.queryBuilderPreview(payload).then((r) => r.data),
  })

  const templatesQuery = useQuery({
    queryKey: ['bi-intelligence-query-builder-templates'],
    queryFn: () => biIntelligenceApi.queryBuilderTemplates().then((r) => r.data),
  })

  const saveTemplateMutation = useMutation({
    mutationFn: (payload) => biIntelligenceApi.saveQueryBuilderTemplate(payload).then((r) => r.data),
    onSuccess: () => {
      setTemplateName('')
      templatesQuery.refetch()
    },
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: (id) => biIntelligenceApi.deleteQueryBuilderTemplate(id).then((r) => r.data),
    onSuccess: () => templatesQuery.refetch(),
  })

  const entities = schemaQuery.data?.entities || {}
  const operators = schemaQuery.data?.operators || {}
  const groups = schemaQuery.data?.groups || {}

  const entityDef = entity ? entities[entity] : null
  const allColumns = useMemo(() => Object.keys(entityDef?.columns || {}), [entityDef])
  const effectiveColumns = selectedColumns.length ? selectedColumns : allColumns

  const groupedEntities = useMemo(() => {
    const acc = {}
    Object.entries(entities).forEach(([key, cfg]) => {
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
  const removeFilter = (i) => setFilters((prev) => prev.filter((_, idx) => idx !== i))
  const patchFilter = (i, patch) => {
    setFilters((prev) => prev.map((f, idx) => (idx === i ? { ...f, ...patch } : f)))
  }

  const toggleColumn = (col) => {
    setSelectedColumns((prev) => (prev.includes(col) ? prev.filter((x) => x !== col) : [...prev, col]))
  }

  const buildQueryPayload = () => ({
    entity,
    columns: effectiveColumns,
    filters: filters
      .filter((f) => f.column && f.operator)
      .map((f) => ({
        column: f.column,
        operator: f.operator,
        value: NULL_OPS.has(f.operator) ? null : f.value,
      })),
    sort: sortColumn ? { column: sortColumn, direction: sortDirection } : null,
    limit: 100,
  })

  const saveTemplate = () => {
    const name = templateName.trim()
    if (!name || !entity) return
    saveTemplateMutation.mutate({
      name,
      query: buildQueryPayload(),
    })
  }

  const loadTemplate = (item) => {
    const q = item?.query || {}
    setEntity(q.entity || 'projects')
    setSelectedColumns(Array.isArray(q.columns) ? q.columns : [])
    setFilters(Array.isArray(q.filters) ? q.filters : [])
    setSortColumn(q.sort?.column || '')
    setSortDirection(q.sort?.direction || 'asc')
  }

  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, overflow: 'hidden' }}>
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--surface-4)' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)' }}>{t('visual_query_builder.title')}</div>
        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{t('visual_query_builder.subtitle')}</div>
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
          style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 10px', fontSize: 12 }}
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
              <input
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                placeholder={t('visual_query_builder.template_placeholder')}
                style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '7px 9px', fontSize: 12 }}
              />
              <button
                type="button"
                onClick={saveTemplate}
                disabled={saveTemplateMutation.isPending || !templateName.trim()}
                style={{ border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-2)', borderRadius: 7, padding: '7px 10px', fontSize: 11, cursor: 'pointer' }}
              >
                {saveTemplateMutation.isPending ? t('visual_query_builder.saving') : t('visual_query_builder.save')}
              </button>
            </div>

            {!!templatesQuery.data?.items?.length && (
              <div style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8, maxHeight: 120, overflowY: 'auto' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 6 }}>{t('visual_query_builder.saved_templates')}</div>
                <div style={{ display: 'grid', gap: 4 }}>
                  {templatesQuery.data.items.map((item) => (
                    <div key={item.id} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <button
                        type="button"
                        onClick={() => loadTemplate(item)}
                        style={{ flex: 1, textAlign: 'left', border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-2)', borderRadius: 6, padding: '5px 8px', fontSize: 11, cursor: 'pointer' }}
                      >
                        {item.name}
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteTemplateMutation.mutate(item.id)}
                        style={{ border: 'none', background: 'transparent', color: '#ef4444', fontSize: 11, cursor: 'pointer' }}
                      >
                        {t('visual_query_builder.delete_btn')}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ border: '1px solid var(--surface-4)', borderRadius: 8, padding: 8, maxHeight: 130, overflowY: 'auto' }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 6 }}>{t('visual_query_builder.columns')}</div>
              <div style={{ display: 'grid', gap: 4 }}>
                {allColumns.map((col) => (
                  <label key={col} style={{ fontSize: 12, color: 'var(--text-2)', display: 'flex', alignItems: 'center', gap: 7 }}>
                    <input type="checkbox" checked={selectedColumns.includes(col)} onChange={() => toggleColumn(col)} />
                    {entityDef.columns[col]?.label || col}
                  </label>
                ))}
              </div>
            </div>

            <div style={{ display: 'grid', gap: 7 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{t('visual_query_builder.filters')}</span>
                <button
                  type="button"
                  onClick={addFilter}
                  style={{ border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-2)', borderRadius: 7, fontSize: 11, padding: '4px 8px', cursor: 'pointer' }}
                >
                  {t('visual_query_builder.add_filter')}
                </button>
              </div>
              {filters.map((f, i) => (
                <div key={i} style={{ display: 'grid', gap: 6, gridTemplateColumns: '1.2fr 1fr 1fr auto' }}>
                  <select value={f.column} onChange={(e) => patchFilter(i, { column: e.target.value })} style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: 12 }}>
                    <option value="">{t('visual_query_builder.field_placeholder')}</option>
                    {allColumns.map((c) => <option key={c} value={c}>{entityDef.columns[c]?.label || c}</option>)}
                  </select>
                  <select value={f.operator} onChange={(e) => patchFilter(i, { operator: e.target.value })} style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: 12 }}>
                    {Object.entries(operators).map(([k, op]) => <option key={k} value={k}>{op?.label || k}</option>)}
                  </select>
                  <input
                    value={f.value}
                    disabled={NULL_OPS.has(f.operator)}
                    onChange={(e) => patchFilter(i, { value: e.target.value })}
                    placeholder={NULL_OPS.has(f.operator) ? t('visual_query_builder.n_a') : t('visual_query_builder.value_placeholder')}
                    style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: 12 }}
                  />
                  <button type="button" onClick={() => removeFilter(i)} style={{ border: 'none', background: 'transparent', color: 'var(--text-3)', cursor: 'pointer' }}>x</button>
                </div>
              ))}
            </div>

            <div style={{ display: 'grid', gap: 7, gridTemplateColumns: '1fr 120px auto' }}>
              <select
                value={sortColumn}
                onChange={(e) => setSortColumn(e.target.value)}
                style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: 12 }}
              >
                <option value="">{t('visual_query_builder.no_sort')}</option>
                {allColumns.map((c) => <option key={c} value={c}>{entityDef.columns[c]?.label || c}</option>)}
              </select>
              <select
                value={sortDirection}
                onChange={(e) => setSortDirection(e.target.value)}
                style={{ background: 'var(--surface-1)', color: 'var(--text-1)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '6px 8px', fontSize: 12 }}
              >
                <option value="asc">{t('visual_query_builder.asc')}</option>
                <option value="desc">{t('visual_query_builder.desc')}</option>
              </select>
              <button
                type="button"
                onClick={() => previewMutation.mutate(buildQueryPayload())}
                disabled={previewMutation.isPending}
                style={{ border: 'none', background: '#0ea5e9', color: '#fff', borderRadius: 8, padding: '7px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
              >
                {previewMutation.isPending ? t('visual_query_builder.loading') : t('visual_query_builder.preview')}
              </button>
            </div>
          </>
        )}

        {previewMutation.isError && (
          <div style={{ fontSize: 12, color: '#ef4444' }}>{t('visual_query_builder.error')}</div>
        )}

        {previewMutation.data && (
          <div style={{ display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
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
