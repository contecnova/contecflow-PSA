/**
 * SearchPage v23 — Búsqueda unificada (NQL + Full-text)
 * Fusiona SearchPage (NQL avanzado) y FullTextSearchPage
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { extractErr } from '../utils/helpers'
import { useQuery, useMutation } from '@tanstack/react-query'
import { epicsApi, projectsApi, tasksApi, clientsApi, ticketsApi, contractsApi } from '../services/api'
import { Button, Spinner, EmptyState, DataTable } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Search } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'

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

interface NqlResponse {
  total?: number
  entity?: string
  execution_time_ms?: number
  results?: Array<Record<string, unknown>>
}

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
      const calls = await Promise.allSettled([
        ents.includes('project')  ? projectsApi.list({ search: q, limit: 8 } as unknown as import('../services/api/projects').ProjectListParams).then(r => ({ type: 'project', items: (r.data as unknown as { items?: SearchItem[] })?.items || r.data || [] })) : null,
        ents.includes('task')     ? tasksApi.list({ search: q, limit: 8 } as unknown as import('../services/api/tasks').TaskListParams).then(r => ({ type: 'task',    items: (r.data as unknown as { items?: SearchItem[] })?.items || r.data || [] })) : null,
        ents.includes('client')   ? clientsApi.list({ q, limit: 8 }).then(r => ({ type: 'client',  items: r.data?.items ?? r.data ?? [] })) : null,
        ents.includes('ticket')   ? ticketsApi.list({ search: q, page_size: 8 }).then(r => ({ type: 'ticket',  items: r.data?.tickets || r.data?.items || (Array.isArray(r.data) ? r.data : []) })) : null,
        ents.includes('contract') ? contractsApi.list({ q, limit: 8 }).then(r => ({ type: 'contract', items: r.data?.items || r.data || [] })) : null,
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
    staleTime: 5000,
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
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button onClick={() => setEntity('all')}
            style={{ padding: '5px 14px', borderRadius: 20, border: `1px solid ${entity === 'all' ? 'var(--accent)' : 'var(--surface-4)'}`,
              background: entity === 'all' ? 'var(--accent-muted)' : 'transparent', color: entity === 'all' ? 'var(--accent)' : 'var(--text-2)',
              fontSize: "var(--text-sm)", fontWeight: entity === 'all' ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
            Todo
          </button>
          {ENTITY_TYPES.map(e => (
            <button key={e.id} onClick={() => setEntity(e.id)}
              style={{ padding: '5px 14px', borderRadius: 20, border: `1px solid ${entity === e.id ? e.color : 'var(--surface-4)'}`,
                background: entity === e.id ? e.color + '15' : 'transparent', color: entity === e.id ? e.color : 'var(--text-2)',
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
                <span style={{ fontSize: "var(--text-xs)", background: etype.color + '20', color: etype.color, borderRadius: 10, padding: '1px 7px' }}>
                  {results[etype.id]!.length}
                </span>
              </div>
              {results[etype.id]!.map(item => (
                <button key={item.id} type="button" style={{ ...panel, padding: '12px 16px', marginBottom: 6,
                  cursor: 'pointer', transition: 'border-color 0.12s' }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = etype.color + '40'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
                  onClick={() => {
                    const paths: Record<EntityTypeId, string> = { project: '/projects', task: '/tasks', client: '/clients', ticket: '/service-desk', contract: '/contracts', invoice: '/invoices' }
                    nav(paths[etype.id])
                  }}>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginBottom: 2 }}>
                    {item.name || item.title || item.code || item.number || '—'}
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
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
    </div>
  )
}

// ── NQL / Advanced search ─────────────────────────────────────────────────────
function NQLMode() {
  const t = useAppT()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<NqlResponse | null>(null)
  const toast = useToast()

  const { mutate: runSearch, isPending } = useMutation({
    mutationFn: (d: { query: string }) => epicsApi.nqlSearch(d).then(r => r.data),
    onSuccess: (data: NqlResponse) => setResults(data),
    onError: (e: unknown) => toast.error(extractErr(e, 'Error en la búsqueda NQL')),
  })

  const EXAMPLES = [
    'projects where status = "active" and risk_level = "high"',
    'tasks where priority = "critical" and status != "done"',
    'users where department = "Engineering"',
  ]

  return (
    <div>
      <div style={{ ...panel, padding: '20px 24px', marginBottom: 20 }}>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 12 }}>Consulta NQL</div>
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Ejemplo: tasks where priority = 'critical'"
          aria-label="Consulta NQL"
          style={{ ...inp, minHeight: 80, resize: 'vertical', fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {EXAMPLES.map((ex, i) => (
              <button key={i} onClick={() => setQuery(ex)}
                style={{ fontSize: "var(--text-2xs)", padding: '3px 8px', borderRadius: 6, border: '1px solid var(--surface-4)',
                  background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>
                Ejemplo {i+1}
              </button>
            ))}
          </div>
          <Button onClick={() => runSearch({ query })} loading={isPending} disabled={!query.trim()}>
            {t('search.ejecutar_busqueda')}
          </Button>
        </div>
      </div>

      {results && (
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 4 }}>
            Resultados <span style={{ fontWeight: 400, color: 'var(--text-2)' }}>({results.total || results.results?.length || 0})</span>
          </div>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 16 }}>
            Entidad: {results.entity} · {results.execution_time_ms}ms
          </div>
          {results.results && results.results.length > 0 ? (
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
          <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 4 }}>
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
