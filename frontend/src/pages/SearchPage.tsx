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
import { Button, Spinner, EmptyState, DataTable } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { FileText, Search } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { STALE_DEFAULT_MS, STALE_VERY_SHORT_MS } from '../constants/timings'
import { SEARCH_RESULTS_PER_ENTITY } from '../constants/pagination'

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
  { id: 'task',    label: 'Tareas',    campos: 'status, priority, project, title', ejemplo: 'priority = critical status = in_progress' },
  { id: 'project', label: 'Proyectos', campos: 'status, name',                     ejemplo: 'status = active' },
  { id: 'epic',    label: 'Épicas',    campos: 'status, priority, title',          ejemplo: 'status = open priority = high' },
]

const ENTITY_TYPES = [
  { id: 'project', label: 'Proyectos',   icon: '⬡',  color: 'var(--accent)' },
  { id: 'task',    label: 'Tareas',      icon: '▦',  color: 'var(--success)' },
  { id: 'client',  label: 'Clientes',    icon: '🏢', color: 'var(--warning)' },
  { id: 'ticket',  label: 'Tickets',     icon: '🎫', color: 'var(--purple)' },
  { id: 'contract',label: 'Contratos',   icon: '📄', color: 'var(--warning)' },
  { id: 'invoice', label: 'Facturas',    icon: '🧾', color: 'var(--accent)' },
] as const satisfies readonly SearchEntityType[]

const panel: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const inp: CSSProperties   = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }

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
    <section aria-label={t('docs.titulo')} style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <FileText size={16} color="var(--accent)" aria-hidden />
        <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--accent)' }}>{t('docs.titulo')} · contecmind</span>
        {docs.isFetching && <Spinner size={14} />}
      </div>
      {docs.isError ? <div role="alert" className="u-text3-sm">{mensajeDeConector(docs.error, t('docs.error_generico'))}</div>
        : !docs.isFetching && items.length === 0 ? <div className="u-text3-sm">{t('docs.sin_resultados')}</div>
        : items.map(d => (
          <button key={d.document_id} type="button" onClick={() => setAbierto(d.document_id)} style={{ ...panel, padding: '12px 16px', marginBottom: 6, cursor: 'pointer', textAlign: 'left', width: '100%' }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 2 }}>{d.title}</div>
            {d.snippet && <div className="u-text2-xs">{d.snippet}</div>}
          </button>
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
      <div style={{ ...panel, padding: '20px 24px', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <span style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', fontSize: "var(--text-lg)", color: 'var(--text-2)' }}>
              {isFetching ? '⟳' : '🔍'}
            </span>
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Buscar proyectos, tareas, clientes o tickets"
              aria-label="Busqueda rapida"
              style={{ ...inp, paddingLeft: 42, fontSize: "var(--text-md-em)" }}
              autoFocus
            />
          </div>
        </div>
        {/* Filtros por tipo */}
        <div className="u-wrap-6">
          <button onClick={() => setEntity('all')}
            style={{ padding: '5px 14px', borderRadius: 20, border: `1px solid ${entity === 'all' ? 'var(--accent)' : 'var(--surface-4)'}`,
              background: entity === 'all' ? 'var(--accent-muted)' : 'transparent', color: entity === 'all' ? 'var(--accent)' : 'var(--text-2)',
              fontSize: "var(--text-sm)", fontWeight: entity === 'all' ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
            Todo
          </button>
          {ENTITY_TYPES.map(e => (
            <button key={e.id} onClick={() => setEntity(e.id)}
              style={{ padding: '5px 14px', borderRadius: 20, border: `1px solid ${entity === e.id ? e.color : 'var(--surface-4)'}`,
                background: entity === e.id ? alpha(e.color, '15') : 'transparent', color: entity === e.id ? e.color : 'var(--text-2)',
                fontSize: "var(--text-sm)", fontWeight: entity === e.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
              {e.icon} {e.label}
            </button>
          ))}
        </div>
      </div>

      {/* Resultados */}
      {q.trim().length < 2 ? (
        <EmptyState icon="🔍" title="Empieza a buscar" description="Escribe al menos dos caracteres para lanzar la busqueda" />
      ) : isFetching ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spinner /></div>
      ) : totalResults === 0 ? (
        <EmptyState icon="🔭" title={`Sin resultados para "${q}"`} description="Prueba con otro termino o cambia el tipo de entidad" />
      ) : (
        <div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 16 }}>
            {totalResults} {t('search.resultado_s_para')}{q}&quot;
          </div>
          {ENTITY_TYPES.filter(e => (results[e.id]?.length ?? 0) > 0).map(etype => (
            <div key={etype.id} style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: "var(--text-lg)" }}>{etype.icon}</span>
                <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: etype.color }}>{etype.label}</span>
                <span style={{ fontSize: "var(--text-xs)", background: alpha(etype.color, '20'), color: etype.color, borderRadius: 'var(--radius-md)', padding: '1px 7px' }}>
                  {results[etype.id]!.length}
                </span>
              </div>
              {results[etype.id]!.map(item => (
                <button key={item.id} type="button" style={{ ...panel, padding: '12px 16px', marginBottom: 6,
                  cursor: 'pointer', transition: 'border-color 0.12s' }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = alpha(etype.color, '40')}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
                  onClick={() => {
                    const paths: Record<EntityTypeId, string> = { project: '/projects', task: '/tasks', client: '/clients', ticket: '/service-desk', contract: '/contracts', invoice: '/invoices' }
                    nav(paths[etype.id])
                  }}>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 2 }}>
                    {item.name || item.title || item.code || item.number || '—'}
                  </div>
                  <div className="u-text2-xs">
                    {item.code && item.code !== (item.name || item.title) && `${item.code} · `}
                    {item.status && `${item.status} · `}
                    {item.client_name || item.project_name || ''}
                  </div>
                </button>
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

  // NQLIn exige `entity_type` (antes no se mandaba: 422 siempre).
  const { mutate: runSearch, isPending } = useMutation({
    mutationFn: (d: { entity_type: BusquedaNql['entity_type']; query: string }) => epicsApi.nqlSearch(d).then(r => r.data),
    onSuccess: (data) => setResults(data),
    onError: (e: unknown) => toast.error(extractErr(e, 'Error en la búsqueda NQL')),
  })

  return (
    <div>
      <div style={{ ...panel, padding: '20px 24px', marginBottom: 20 }}>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 12 }}>Consulta NQL</div>
        <div className="u-wrap-6" style={{ marginBottom: 10 }}>
          <select value={entidad} onChange={e => { setEntidad(e.target.value as BusquedaNql['entity_type']); setResults(null) }}
            aria-label="Entidad" style={{ ...inp, width: 'auto' }}>
            {NQL_ENTIDADES.map(e => <option key={e.id} value={e.id}>{e.label}</option>)}
          </select>
          <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', alignSelf: 'center' }}>Campos: {elegida.campos}</span>
        </div>
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={`Ejemplo: ${elegida.ejemplo}`}
          aria-label="Consulta NQL"
          style={{ ...inp, minHeight: 80, resize: 'vertical', fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
          <button onClick={() => setQuery(elegida.ejemplo)}
            style={{ fontSize: "var(--text-2xs)", padding: '3px 8px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)',
              background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>
            Ejemplo
          </button>
          <Button onClick={() => runSearch({ entity_type: entidad, query })} loading={isPending} disabled={!query.trim()}>
            {t('search.ejecutar_busqueda')}
          </Button>
        </div>
      </div>

      {results && (
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 4 }}>
            Resultados <span style={{ fontWeight: 400, color: 'var(--text-2)' }}>({results.count})</span>
          </div>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 16 }}>
            Entidad: {NQL_ENTIDADES.find(e => e.id === results.entity_type)?.label ?? results.entity_type}
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
            <EmptyState icon="📭" title={t('search.sin_resultados_nql')} description="La consulta no devolvio registros" />
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
          <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 4 }}>
            {([['fts', '🔍 Búsqueda rápida'], ['nql', '⚡ NQL avanzado']] as const).map(([id, label]) => (
              <button key={id} onClick={() => setMode(id)}
                style={{ padding: '7px 16px', borderRadius: 7, border: 'none',
                  background: mode === id ? 'var(--accent)' : 'transparent',
                  color: mode === id ? 'var(--surface-0)' : 'var(--text-2)',
                  fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                {label}
              </button>
            ))}
          </div>
        }
      showListExport={false}
      />
      {mode === 'fts' ? <FTSMode /> : <NQLMode />}
    </PageShell>
  )
}
