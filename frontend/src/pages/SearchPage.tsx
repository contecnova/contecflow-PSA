/**
 * SearchPage v23 — Búsqueda unificada (NQL + Full-text)
 * Fusiona SearchPage (NQL avanzado) y FullTextSearchPage
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { extractErr } from '../utils/helpers'
import { useQuery, useMutation } from '@tanstack/react-query'
import { epicsApi, projectsApi, tasksApi, clientsApi, ticketsApi, contractsApi, conectoresApi, mensajeDeConector } from '../services/api'
import type { BusquedaNql } from '../services/api/tipos-proyectos'
import DocumentoContecmind from '../components/conectores/DocumentoContecmind'
import { Button, Spinner, EmptyState, DataTable, Pulsable, Select } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { FileText, Search } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'
import { STALE_DEFAULT_MS, STALE_VERY_SHORT_MS } from '../constants/timings'
import { SEARCH_RESULTS_PER_ENTITY } from '../constants/pagination'
import './SearchPage.css'

type EntityTypeId = 'project' | 'task' | 'client' | 'ticket' | 'contract' | 'invoice'

interface SearchEntityType {
  id: EntityTypeId
  label: string
  icon: string
  color: string
}

interface SearchItem {
  id: string | number
  name?: string
  title?: string
  code?: string
  number?: string
  status?: string
  client_name?: string
  project_name?: string
}

type GroupedResults = Partial<Record<EntityTypeId, SearchItem[]>>

/** Entidades y campos que acepta POST /epics/nql/search (epics_service._ENTIDADES_NQL). */
const NQL_ENTIDADES: Array<{ id: BusquedaNql['entity_type']; label: string; campos: string; ejemplo: string }> = [
  { id: 'task',    label: 'tareas',    campos: 'status, priority, project, title', ejemplo: 'priority = critical status = in_progress' },
  { id: 'project', label: 'proyectos', campos: 'status, name',                     ejemplo: 'status = active' },
  { id: 'epic',    label: 'epicas',    campos: 'status, priority, title',          ejemplo: 'status = open priority = high' },
]

const ENTITY_TYPES = [
  { id: 'project', label: 'proyectos',   icon: '⬡',  color: 'var(--accent)' },
  { id: 'task',    label: 'tareas',      icon: '▦',  color: 'var(--success)' },
  { id: 'client',  label: 'clientes',    icon: '🏢', color: 'var(--warning)' },
  { id: 'ticket',  label: 'tickets',     icon: '🎫', color: 'var(--purple)' },
  { id: 'contract',label: 'contratos',   icon: '📄', color: 'var(--warning)' },
  { id: 'invoice', label: 'facturas',    icon: '🧾', color: 'var(--accent)' },
] as const satisfies readonly SearchEntityType[]

/** Color de la entidad para las clases `.srch-*` (variable CSS). */
const colorVar = (color: string) => ({ '--srch-color': color }) as CSSProperties

// Revisión 2026-11: los documentos de contecmind, con los permisos de quien busca.
function DocumentosEnLaBusqueda({ q }: { q: string }) {
  const t = useAppT()
  const [abierto, setAbierto] = useState<string | null>(null)
  const disp = useQuery({ queryKey: ['conectores', 'cm-disponible'], queryFn: conectoresApi.cmDisponible, staleTime: STALE_DEFAULT_MS, retry: false })
  const docs = useQuery({ queryKey: ['conectores', 'buscar', q], queryFn: () => conectoresApi.buscar(q, 8),
    enabled: !!disp.data?.configurado && q.length >= 2, retry: false, staleTime: STALE_VERY_SHORT_MS })
  if (!disp.data?.configurado) return null
  const items = docs.data?.items ?? []
  return (
    <section aria-label={t('docs.titulo')} className="srch-docs">
      <div className="srch-docs__head">
        <FileText size={16} color="var(--accent)" aria-hidden />
        <span className="srch-docs__title">{t('docs.titulo')} · contecmind</span>
        {docs.isFetching && <Spinner size={14} />}
      </div>
      {docs.isError ? <div role="alert" className="u-text3-sm">{mensajeDeConector(docs.error, t('docs.error_generico'))}</div>
        : !docs.isFetching && items.length === 0 ? <div className="u-text3-sm">{t('docs.sin_resultados')}</div>
        : items.map(d => (
          <Pulsable key={d.document_id} type="button" onClick={() => setAbierto(d.document_id)} className="srch-panel srch-item">
            <div className="srch-item__title">{d.title}</div>
            {d.snippet && <div className="u-text2-xs">{d.snippet}</div>}
          </Pulsable>
        ))}
      {abierto && <DocumentoContecmind id={abierto} puedeEscribir={!!disp.data?.puede_escribir} onClose={() => setAbierto(null)} />}
    </section>
  )
}

// ── Full-text search ──────────────────────────────────────────────────────────
function FTSMode() {
  const t = useAppT()
  const [searchParams, setSearchParams] = useSearchParams()
  const q = searchParams.get('q') || ''
  const entity = (searchParams.get('entity') || 'all') as EntityTypeId | 'all'
  const setQ = (v: string) => setSearchParams(p => { const n = new URLSearchParams(p); v ? n.set('q', v) : n.delete('q'); return n }, { replace: true })
  const setEntity = (v: EntityTypeId | 'all') => setSearchParams(p => { const n = new URLSearchParams(p); v && v !== 'all' ? n.set('entity', v) : n.delete('entity'); return n }, { replace: true })
  const _toast = useToast()
  const nav = useNavigate()

  const { data: resultsRaw = {}, isFetching } = useQuery({
    queryKey: ['fts-unified', q, entity],
    queryFn: async () => {
      if (q.trim().length < 2) return {}
      const ents = entity === 'all' ? ENTITY_TYPES.map(e => e.id) : [entity]
      // Auditoría 2026-11: `/projects` no admite `limit`, y sin `page` el listado recorre todas
      // las páginas (`todasLasPaginas`): se pide una sola página de 8.
      const calls = await Promise.allSettled([
        ents.includes('project')  ? projectsApi.list({ search: q, page: 1, page_size: SEARCH_RESULTS_PER_ENTITY }).then(r => ({ type: 'project', items: r.data })) : null,
        ents.includes('task')     ? tasksApi.list({ search: q, page: 1, page_size: SEARCH_RESULTS_PER_ENTITY }).then(r => ({ type: 'task',    items: r.data })) : null,
        ents.includes('client')   ? clientsApi.list({ q, limit: SEARCH_RESULTS_PER_ENTITY }).then(r => ({ type: 'client',  items: r.data ?? [] })) : null,
        ents.includes('ticket')   ? ticketsApi.list({ search: q, page_size: SEARCH_RESULTS_PER_ENTITY }).then(r => ({ type: 'ticket',  items: r.data ?? [] })) : null,
        ents.includes('contract') ? contractsApi.list({ q, limit: SEARCH_RESULTS_PER_ENTITY }).then(r => ({ type: 'contract', items: r.data ?? [] })) : null,
      ].filter(Boolean))
      const grouped: GroupedResults = {}
      calls.forEach(c => {
        if (c.status === 'fulfilled' && c.value) {
          grouped[c.value.type as EntityTypeId] = c.value.items as SearchItem[]
        }
      })
      return grouped
    },
    enabled: q.trim().length >= 2,
    staleTime: STALE_VERY_SHORT_MS,
  })
  const results = resultsRaw as GroupedResults

  const totalResults = Object.values(results).flat().length

  return (
    <div>
      {/* Barra de búsqueda */}
      <div className="srch-panel srch-panel--bar">
        <div className="srch-bar">
          <div className="srch-bar__field">
            <span className="srch-bar__icon" aria-hidden="true">
              {isFetching ? '⟳' : '🔍'}
            </span>
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder={t('search_page.placeholder')}
              aria-label={t('search_page.busqueda_rapida')}
              className="srch-input srch-input--query"
              autoFocus
            />
          </div>
        </div>
        {/* Filtros por tipo */}
        <div className="u-wrap-6" role="group" aria-label={t('search_page.filtrar_por_tipo')}>
          <Pulsable type="button" onClick={() => setEntity('all')} aria-pressed={entity === 'all'}
            className={`srch-chip srch-chip--all${entity === 'all' ? ' srch-chip--active' : ''}`}>
            {t('search_page.todo')}
          </Pulsable>
          {ENTITY_TYPES.map(e => (
            <Pulsable key={e.id} type="button" onClick={() => setEntity(e.id)} aria-pressed={entity === e.id}
              className={`srch-chip${entity === e.id ? ' srch-chip--active' : ''}`} style={colorVar(e.color)}>
              <span aria-hidden="true">{e.icon}</span> {t(`search_page.${e.label}`)}
            </Pulsable>
          ))}
        </div>
      </div>

      {/* Resultados */}
      {q.trim().length < 2 ? (
        <EmptyState icon="🔍" title={t('search_page.empieza_titulo')} description={t('search_page.empieza_desc')} />
      ) : isFetching ? (
        <div className="srch-loading"><Spinner /></div>
      ) : totalResults === 0 ? (
        <EmptyState icon="🔭" title={t('search_page.sin_resultados_para', { q })} description={t('search_page.sin_resultados_desc')} />
      ) : (
        <div>
          <div className="srch-count" role="status">
            {t('search_page.n_resultados_para', { n: totalResults, q })}
          </div>
          {ENTITY_TYPES.filter(e => (results[e.id]?.length ?? 0) > 0).map(etype => (
            <div key={etype.id} className="srch-group" style={colorVar(etype.color)}>
              <div className="srch-group__head">
                <span className="srch-group__icon" aria-hidden="true">{etype.icon}</span>
                <span className="srch-group__label">{t(`search_page.${etype.label}`)}</span>
                <span className="srch-group__badge">
                  {results[etype.id]!.length}
                </span>
              </div>
              {results[etype.id]!.map(item => (
                <Pulsable key={item.id} type="button" className="srch-panel srch-item"
                  onClick={() => {
                    const paths: Record<EntityTypeId, string> = { project: '/projects', task: '/tasks', client: '/clients', ticket: '/service-desk', contract: '/contracts', invoice: '/invoices' }
                    nav(paths[etype.id])
                  }}>
                  <div className="srch-item__title">
                    {item.name || item.title || item.code || item.number || '—'}
                  </div>
                  <div className="u-text2-xs">
                    {item.code && item.code !== (item.name || item.title) && `${item.code} · `}
                    {item.status && `${item.status} · `}
                    {item.client_name || item.project_name || ''}
                  </div>
                </Pulsable>
              ))}
            </div>
          ))}
        </div>
      )}
      {q.trim().length >= 2 && <DocumentosEnLaBusqueda q={q.trim()} />}
    </div>
  )
}

// ── NQL / Advanced search ─────────────────────────────────────────────────────
function NQLMode() {
  const t = useAppT()
  const [query, setQuery] = useState('')
  const [entidad, setEntidad] = useState<BusquedaNql['entity_type']>('task')
  const [results, setResults] = useState<BusquedaNql | null>(null)
  const toast = useToast()
  const elegida = NQL_ENTIDADES.find(e => e.id === entidad) ?? NQL_ENTIDADES[0]
  const entidadResultados = results ? NQL_ENTIDADES.find(e => e.id === results.entity_type) : undefined

  // NQLIn exige `entity_type` (antes no se mandaba: 422 siempre).
  const { mutate: runSearch, isPending } = useMutation({
    mutationFn: (d: { entity_type: BusquedaNql['entity_type']; query: string }) => epicsApi.nqlSearch(d).then(r => r.data),
    onSuccess: (data) => setResults(data),
    onError: (e: unknown) => toast.error(extractErr(e, t('search_page.error_nql'))),
  })

  return (
    <div>
      <div className="srch-panel srch-panel--bar">
        <div className="srch-title">{t('search_page.consulta_nql')}</div>
        <div className="u-wrap-6 srch-nql-entity">
          <Select suelto placeholder={false} value={entidad} onChange={e => { setEntidad(e.target.value as BusquedaNql['entity_type']); setResults(null) }}
            aria-label={t('search_page.entidad')} className="srch-input srch-input--auto">
            {NQL_ENTIDADES.map(e => <option key={e.id} value={e.id}>{t(`search_page.${e.label}`)}</option>)}
          </Select>
          <span className="srch-hint">{t('search_page.campos', { campos: elegida.campos })}</span>
        </div>
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={t('search_page.ejemplo_ph', { ejemplo: elegida.ejemplo })}
          aria-label={t('search_page.consulta_nql')}
          className="srch-input srch-input--nql"
        />
        <div className="srch-actions">
          <Pulsable type="button" onClick={() => setQuery(elegida.ejemplo)} className="srch-btn">
            {t('search_page.ejemplo')}
          </Pulsable>
          <Button onClick={() => runSearch({ entity_type: entidad, query })} loading={isPending} disabled={!query.trim()}>
            {t('search.ejecutar_busqueda')}
          </Button>
        </div>
      </div>

      {results && (
        <div className="srch-panel srch-panel--results">
          <div className="srch-title srch-title--results">
            {t('search_page.resultados')} <span className="srch-title__count">({results.count})</span>
          </div>
          <div className="srch-hint srch-hint--block">
            {t('search_page.entidad_valor', { entidad: entidadResultados ? t(`search_page.${entidadResultados.label}`) : results?.entity_type })}
          </div>
          {results.results.length > 0 ? (
            <DataTable
              columns={Object.keys(results.results[0]).slice(0, 6).map(k => ({
                key: k, label: k.replace(/_/g, ' ').toUpperCase(),
                sortable: true,
              }))}
              data={results.results}
              pageSize={20}
            />
          ) : (
            <EmptyState icon="📭" title={t('search.sin_resultados_nql')} description={t('search_page.nql_sin_registros')} />
          )}
        </div>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function SearchPage() {
  const _t = useAppT()
  const [mode, setMode] = useState<'fts' | 'nql'>('fts')

  return (
    <PageShell>
      <PageHeader
        icon={<Search size={18} />}
        title={_t('search.title')}
        subtitle={_t('search.subtitle')}
        actions={
          <div className="srch-modes" role="group" aria-label={_t('search_page.modo')}>
            {([['fts', '🔍', 'search_page.modo_rapida'], ['nql', '⚡', 'search_page.modo_nql']] as const).map(([id, icono, clave]) => (
              <Pulsable key={id} type="button" onClick={() => setMode(id)} aria-pressed={mode === id}
                className={`srch-mode${mode === id ? ' srch-mode--active' : ''}`}>
                <span aria-hidden="true">{icono}</span> {_t(clave)}
              </Pulsable>
            ))}
          </div>
        }
      showListExport={false}
      />
      {mode === 'fts' ? <FTSMode /> : <NQLMode />}
    </PageShell>
  )
}
