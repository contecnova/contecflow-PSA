/**
 * SearchPage v23 — Búsqueda unificada (NQL + Full-text)
 * Fusiona SearchPage (NQL avanzado) y FullTextSearchPage
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useQuery, useMutation } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, DataTable } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useToast } from '../context/ToastContext'
import { useNavigate } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'

const ENTITY_TYPES = [
  { id: 'project', label: 'Proyectos',   icon: '⬡',  color: 'var(--accent)' },
  { id: 'task',    label: 'Tareas',      icon: '▦',  color: 'var(--success)' },
  { id: 'client',  label: 'Clientes',    icon: '🏢', color: 'var(--warning)' },
  { id: 'ticket',  label: 'Tickets',     icon: '🎫', color: 'var(--purple)' },
  { id: 'contract',label: 'Contratos',   icon: '📄', color: 'var(--warning)' },
  { id: 'invoice', label: 'Facturas',    icon: '🧾', color: 'var(--accent)' },
]

const panel = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const inp   = { background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: 14, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }

// ── Full-text search ──────────────────────────────────────────────────────────
function FTSMode() {
  const [q, setQ] = useState('')
  const [entity, setEntity] = useState('all')
  const _toast = useToast()
  const nav = useNavigate()

  const { data: results = {}, isFetching } = useQuery({
    queryKey: ['fts-unified', q, entity],
    queryFn: async () => {
      if (q.trim().length < 2) return {}
      const _params = { q: q.trim(), limit: 8 }
      const ents = entity === 'all' ? ENTITY_TYPES.map(e => e.id) : [entity]
      const calls = await Promise.allSettled([
        ents.includes('project')  ? api.get('/projects', { params: { search: q, limit: 8 } }).then(r => ({ type: 'project', items: r.data?.items || r.data || [] })) : null,
        ents.includes('task')     ? api.get('/tasks',    { params: { search: q, limit: 8 } }).then(r => ({ type: 'task',    items: r.data?.items || r.data || [] })) : null,
        ents.includes('client')   ? api.get('/clients',  { params: { q, limit: 8 } }).then(r => ({ type: 'client',  items: r.data || [] })) : null,
        ents.includes('ticket')   ? api.get('/sd/tickets',{ params: { search: q, page_size: 8 } }).then(r => ({ type: 'ticket',  items: r.data?.tickets || r.data?.items || (Array.isArray(r.data) ? r.data : []) })) : null,
        ents.includes('contract') ? api.get('/contracts',{ params: { q, limit: 8 } }).then(r => ({ type: 'contract', items: r.data?.items || r.data || [] })) : null,
      ].filter(Boolean))
      const grouped = {}
      calls.forEach(c => { if (c.status === 'fulfilled' && c.value) grouped[c.value.type] = c.value.items })
      return grouped
    },
    enabled: q.trim().length >= 2,
    staleTime: 5000,
  })

  const totalResults = Object.values(results).flat().length

  return (
    <div>
      {/* Barra de búsqueda */}
      <div style={{ ...panel, padding: '20px 24px', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <span style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', fontSize: 16, color: 'var(--text-2)' }}>
              {isFetching ? '⟳' : '🔍'}
            </span>
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Buscar proyectos, tareas, clientes o tickets"
              aria-label="Busqueda rapida"
              style={{ ...inp, paddingLeft: 42, fontSize: 15 }}
              autoFocus
            />
          </div>
        </div>
        {/* Filtros por tipo */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button onClick={() => setEntity('all')}
            style={{ padding: '5px 14px', borderRadius: 20, border: `1px solid ${entity === 'all' ? 'var(--accent)' : 'var(--surface-4)'}`,
              background: entity === 'all' ? 'var(--accent-muted)' : 'transparent', color: entity === 'all' ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12, fontWeight: entity === 'all' ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
            Todo
          </button>
          {ENTITY_TYPES.map(e => (
            <button key={e.id} onClick={() => setEntity(e.id)}
              style={{ padding: '5px 14px', borderRadius: 20, border: `1px solid ${entity === e.id ? e.color : 'var(--surface-4)'}`,
                background: entity === e.id ? e.color + '15' : 'transparent', color: entity === e.id ? e.color : 'var(--text-2)',
                fontSize: 12, fontWeight: entity === e.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
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
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16 }}>
            {totalResults} resultado(s) para &quot;{q}&quot;
          </div>
          {ENTITY_TYPES.filter(e => results[e.id]?.length > 0).map(etype => (
            <div key={etype.id} style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 16 }}>{etype.icon}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: etype.color }}>{etype.label}</span>
                <span style={{ fontSize: 11, background: etype.color + '20', color: etype.color, borderRadius: 10, padding: '1px 7px' }}>
                  {results[etype.id].length}
                </span>
              </div>
              {results[etype.id].map(item => (
                <button key={item.id} type="button" style={{ ...panel, padding: '12px 16px', marginBottom: 6,
                  cursor: 'pointer', transition: 'border-color 0.12s' }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = etype.color + '40'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
                  onClick={() => {
                    const paths = { project: '/projects', task: '/tasks', client: '/clients', ticket: '/service-desk', contract: '/contracts', invoice: '/invoices' }
                    nav(paths[etype.id] || '/')
                  }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 2 }}>
                    {item.name || item.title || item.code || item.number || '—'}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
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
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const toast = useToast()

  const { mutate: runSearch, isPending } = useMutation({
    mutationFn: d => api.post('nql/search', d).then(r => r.data),
    onSuccess: data => setResults(data),
    onError: e => toast.error(extractErr(e, 'Error en la búsqueda NQL')),
  })

  const EXAMPLES = [
    'projects where status = "active" and risk_level = "high"',
    'tasks where priority = "critical" and status != "done"',
    'users where department = "Engineering"',
  ]

  return (
    <div>
      <div style={{ ...panel, padding: '20px 24px', marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Consulta NQL</div>
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Ejemplo: tasks where priority = 'critical'"
          aria-label="Consulta NQL"
          style={{ ...inp, minHeight: 80, resize: 'vertical', fontSize: 13, fontFamily: "'Space Mono', monospace" }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {EXAMPLES.map((ex, i) => (
              <button key={i} onClick={() => setQuery(ex)}
                style={{ fontSize: 10, padding: '3px 8px', borderRadius: 6, border: '1px solid #1e2d45',
                  background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>
                Ejemplo {i+1}
              </button>
            ))}
          </div>
          <Button onClick={() => runSearch({ query })} loading={isPending} disabled={!query.trim()}>
            Ejecutar búsqueda
          </Button>
        </div>
      </div>

      {results && (
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
            Resultados <span style={{ fontWeight: 400, color: 'var(--text-2)' }}>({results.total || results.results?.length || 0})</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 16 }}>
            Entidad: {results.entity} · {results.execution_time_ms}ms
          </div>
          {results.results?.length > 0 ? (
            <DataTable
              columns={Object.keys(results.results[0]).slice(0, 6).map(k => ({
                key: k, label: k.replace(/_/g, ' ').toUpperCase(),
                sortable: true,
              }))}
              data={results.results}
              pageSize={20}
            />
          ) : (
            <EmptyState icon="📭" title="Sin resultados NQL" description="La consulta no devolvio registros" />
          )}
        </div>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function SearchPage() {
  const _t = useAppT()
  const [mode, setMode] = useState('fts')

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title={_t('search.title')}
        subtitle={_t('search.subtitle')}
        actions={
          <div style={{ display: 'flex', gap: 4, background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10, padding: 4 }}>
            {[['fts', '🔍 Búsqueda rápida'], ['nql', '⚡ NQL avanzado']].map(([id, label]) => (
              <button key={id} onClick={() => setMode(id)}
                style={{ padding: '7px 16px', borderRadius: 7, border: 'none',
                  background: mode === id ? 'var(--accent)' : 'transparent',
                  color: mode === id ? 'var(--surface-0)' : 'var(--text-2)',
                  fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                {label}
              </button>
            ))}
          </div>
        }
      />
      {mode === 'fts' ? <FTSMode /> : <NQLMode />}
    </div>
  )
}
