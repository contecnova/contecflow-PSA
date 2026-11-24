import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { biIntelligenceApi } from '../../services/api'
import type { PlantillaDeConsultaVisual } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, IconButton, Table, Select, Pulsable, Checkbox, Input } from '../ui'
import { Eye, Plus, Save, Trash2, X } from 'lucide-react'
import { STALE_5_MIN_MS } from '../../constants/timings'
import { VISUAL_QUERY_ROW_LIMIT } from '../../constants/pagination'
import './VisualQueryBuilderWidget.css'

interface FilterEntry {
  column: string
  operator: string
  value: string
}

const EMPTY_FILTER: FilterEntry = { column: '', operator: 'eq', value: '' }
const NULL_OPS = new Set(['is_null', 'is_not_null'])

function RowTable({ rows = [], columns = [] }: { rows?: Array<Record<string, unknown>>; columns?: string[] }) {
  if (!rows.length || !columns.length) return null
  return (
    <div className="viqubuwi-box-1">
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

  const schemaQuery = useQuery({
    queryKey: ['bi-intelligence-query-builder-schema'],
    queryFn: () => biIntelligenceApi.queryBuilderSchema().then((r) => r.data),
    staleTime: STALE_5_MIN_MS,
  })

  const previewMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => biIntelligenceApi.queryBuilderPreview(payload).then((r) => r.data),
  })

  const templatesQuery = useQuery({
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
    mutationFn: (id: PlantillaDeConsultaVisual['id']) => biIntelligenceApi.deleteQueryBuilderTemplate(id).then((r) => r.data),
    onSuccess: () => templatesQuery.refetch(),
  })

  const entities = useMemo(() => schemaQuery.data?.entities || {}, [schemaQuery.data])
  const operators = useMemo(() => schemaQuery.data?.operators || {}, [schemaQuery.data])
  const groups = useMemo(() => schemaQuery.data?.groups || {}, [schemaQuery.data])
  // APIListResponse: llega como lista.
  const templateItems = useMemo(() => templatesQuery.data ?? [], [templatesQuery.data])

  const entityDef = entity ? entities[entity] : null
  const allColumns = useMemo(() => Object.keys(entityDef?.columns || {}), [entityDef])
  const effectiveColumns = selectedColumns.length ? selectedColumns : allColumns
  const validOperators = useMemo(() => new Set(Object.keys(operators || {})), [operators])

  const groupedEntities = useMemo(() => {
    const acc: Record<string, Array<{ key: string; label: string }>> = {}
    ;Object.entries(entities).forEach(([key, cfg]) => {
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
      limit: VISUAL_QUERY_ROW_LIMIT,
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

  const loadTemplate = (item: PlantillaDeConsultaVisual) => {
    // Se guardó sin los campos nulos (`exclude_none`): `sort` puede faltar.
    const q = item.query
    setEntity(q.entity)
    setSelectedColumns(q.columns ?? [])
    setFilters((q.filters ?? []).map((f) => ({ column: f.column, operator: f.operator, value: f.value == null ? '' : String(f.value) })))
    setSortColumn(q.sort?.column || '')
    setSortDirection(q.sort?.direction || 'asc')
  }

  return (
    <div className="viqubuwi-box-2">
      <div className="viqubuwi-box-3">
        <div className="viqubuwi-txt-1">{t('visual_query_builder.title')}</div>
        <div className="u-text3-2xs">{t('visual_query_builder.subtitle')}</div>
      </div>

      <div className="viqubuwi-grid-1">
        <Select suelto
          value={entity}
          onChange={(e) => {
            setEntity(e.target.value)
            setSelectedColumns([])
            setFilters([])
            setSortColumn('')
          }}
          className="viqubuwi-box-4" placeholder={t('visual_query_builder.entity_placeholder')}>
          {sortedGroupKeys.map((g) => (
            <optgroup key={g} label={groups[g] || g}>
              {(groupedEntities[g] || []).map((item) => (
                <option key={item.key} value={item.key}>{item.label}</option>
              ))}
            </optgroup>
          ))}
        </Select>

        {!!entityDef && (
          <>
            <div className="viqubuwi-grid-2">
              <Input aria-label={t('visual_query_builder.template_placeholder')} value={templateName} onChange={(e) => setTemplateName(e.target.value)} placeholder={t('visual_query_builder.template_placeholder')} inputClassName="viqubuwi-box-5" />
              <Button
                variant="secondary"
                icon={<Save size={14} />}
                onClick={saveTemplate}
                disabled={saveTemplateMutation.isPending || !templateName.trim()}
                loading={saveTemplateMutation.isPending}
              >
                {saveTemplateMutation.isPending ? t('visual_query_builder.saving') : t('visual_query_builder.save')}
              </Button>
            </div>

            {!!templateItems.length && (
              <div className="viqubuwi-box-7">
                <div className="viqubuwi-box-8">{t('visual_query_builder.saved_templates')}</div>
                <div className="viqubuwi-grid-3">
                  {templateItems.map((item) => (
                    <div key={item.id} className="u-row-center-6">
                      <Pulsable
                        onClick={() => loadTemplate(item)}
                        className="viqubuwi-box-9"
                      >
                        {item.name}
                      </Pulsable>
                      <IconButton variante="caja" tono="peligro"
                        onClick={() => deleteTemplateMutation.mutate(item.id)}
                        ariaLabel={t('visual_query_builder.delete_btn')}
                      >
                        <Trash2 size={13} />
                      </IconButton>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="viqubuwi-box-11">
              <div className="viqubuwi-box-8">{t('visual_query_builder.columns')}</div>
              <div className="viqubuwi-grid-3">
                {allColumns.map((col) => (
                  <Checkbox key={col} className="viqubuwi-row-1" label={entityDef.columns?.[col]?.label || col} checked={selectedColumns.includes(col)} onChange={() => toggleColumn(col)} />
                ))}
              </div>
            </div>

            <div className="viqubuwi-grid-4">
              <div className="u-row-between">
                <span className="u-text3-xs">{t('visual_query_builder.filters')}</span>
                <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={addFilter}>
                  {t('visual_query_builder.add_filter')}
                </Button>
              </div>
              {filters.map((f, i) => (
                <div key={i} className="viqubuwi-grid-5">
                  <Select suelto value={f.column} onChange={(e) => patchFilter(i, { column: e.target.value })} className="viqubuwi-box-13" placeholder={t('visual_query_builder.field_placeholder')}>
                    {allColumns.map((c) => <option key={c} value={c}>{entityDef.columns?.[c]?.label || c}</option>)}
                  </Select>
                  <Select suelto value={f.operator} onChange={(e) => patchFilter(i, { operator: e.target.value })} className="viqubuwi-box-13" placeholder={false}>
                    {Object.entries(operators).map(([k, op]) => <option key={k} value={k}>{op.label}</option>)}
                  </Select>
                  <Input aria-label={t('visual_query_builder.value_placeholder')} value={f.value} disabled={NULL_OPS.has(f.operator)} onChange={(e) => patchFilter(i, { value: e.target.value })} placeholder={NULL_OPS.has(f.operator) ? t('visual_query_builder.n_a') : t('visual_query_builder.value_placeholder')} />
                  <IconButton onClick={() => removeFilter(i)} className="viqubuwi-del" ariaLabel={t('visual_query_builder.delete_btn')}><X size={14} /></IconButton>
                </div>
              ))}
            </div>

            <div className="viqubuwi-grid-6">
              <Select suelto
                value={sortColumn}
                onChange={(e) => setSortColumn(e.target.value)}
                className="viqubuwi-box-13" placeholder={t('visual_query_builder.no_sort')}>
                {allColumns.map((c) => <option key={c} value={c}>{entityDef.columns?.[c]?.label || c}</option>)}
              </Select>
              <Select suelto
                value={sortDirection}
                onChange={(e) => setSortDirection(e.target.value)}
                className="viqubuwi-box-13" placeholder={false}>
                <option value="asc">{t('visual_query_builder.asc')}</option>
                <option value="desc">{t('visual_query_builder.desc')}</option>
              </Select>
              <Button
                icon={<Eye size={14} />}
                onClick={() => previewMutation.mutate(buildQueryPayload())}
                disabled={previewMutation.isPending}
                loading={previewMutation.isPending}
              >
                {previewMutation.isPending ? t('visual_query_builder.loading') : t('visual_query_builder.preview')}
              </Button>
            </div>
          </>
        )}

        {previewMutation.isError && (
          <div className="viqubuwi-txt-2">{t('visual_query_builder.error')}</div>
        )}

        {previewMutation.data && (
          <div className="viqubuwi-grid-7">
            <div className="u-text3-xs">
              {previewMutation.data.count} {t('visual_query_builder.results')}
              {previewMutation.data.truncated ? ` ${t('visual_query_builder.truncated')}` : ''}
            </div>
            <RowTable rows={previewMutation.data.rows} columns={previewMutation.data.columns} />
          </div>
        )}
      </div>
    </div>
  )
}
