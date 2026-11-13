/**
 * WebhookLogPage — Log de eventos webhook salientes
 * Tabla con últimas llamadas: timestamp, evento, URL, status HTTP, payload
 */
import { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { enterpriseApi } from '../services/api'
import { Spinner, EmptyState, Modal, Table } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Webhook } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { POLL_FREQUENT_MS } from '../constants/timings'

interface WebhookItem {
  id: string
  name?: string
  url?: string
}

interface WebhookLogItem {
  id: string
  webhook_id?: string
  webhook_name?: string
  webhook_url?: string
  event?: string
  status_code?: number | null
  success?: boolean
  error?: string | null
  duration_ms?: number | null
  payload?: string | null
  response?: string | null
  created_at?: string | null
}

interface DeliveriesPage {
  items: WebhookLogItem[]
  total: number
}

const PAGE_SIZE = 50

function tryParseJson(value: unknown): unknown {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

const selectStyle = {
  background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8,
  padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit',
} as const

export default function WebhookLogPage() {
  const t = useAppT()
  const [selectedLog, setSelectedLog] = useState<WebhookLogItem | null>(null)
  const [webhookId, setWebhookId] = useState('')
  const [event, setEvent] = useState('')
  const [estado, setEstado] = useState<'' | 'ok' | 'ko'>('')
  const [page, setPage] = useState(1)

  // Webhooks salientes configurados (para el filtro y el KPI)
  const { data: webhooks = [] } = useQuery<WebhookItem[]>({
    queryKey: ['outbound-webhooks'],
    queryFn: () => enterpriseApi.outboundWebhooks().then(r => (Array.isArray(r.data) ? r.data : [])).catch(() => []),
  })

  const { data: eventos = [] } = useQuery<{ value: string; label: string }[]>({
    queryKey: ['outbound-webhook-events'],
    queryFn: () => enterpriseApi.outboundWebhookEvents().then(r => (Array.isArray(r.data) ? r.data : [])).catch(() => []),
    staleTime: Infinity,
  })

  // Segunda auditoría 2026-11 (#22): antes una petición por webhook (N+1).
  // Ahora un único endpoint paginado; la clave lleva los filtros y la página.
  const filtros = {
    webhook_id: webhookId || undefined,
    event: event || undefined,
    success: estado === '' ? undefined : estado === 'ok',
    page,
    page_size: PAGE_SIZE,
  }
  const { data, isLoading, refetch } = useQuery<DeliveriesPage>({
    queryKey: ['webhook-deliveries', filtros],
    // El interceptor deja la lista en `r.data` y la paginación en `r.meta`.
    queryFn: () => enterpriseApi.webhookDeliveries(filtros).then(r => {
      const items = (Array.isArray(r.data) ? r.data : []) as WebhookLogItem[]
      const meta = (r as { meta?: { total?: number } }).meta
      return { items, total: Number(meta?.total ?? items.length) }
    }),
    placeholderData: keepPreviousData,
    refetchInterval: POLL_FREQUENT_MS,
  })
  const logs = data?.items ?? []
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const STATUS_COLOR = {
    200: 'var(--success)', 201: 'var(--success)', 204: 'var(--success)',
    400: 'var(--warning)', 401: 'var(--warning)', 403: 'var(--danger)',
    404: 'var(--warning)', 500: 'var(--danger)', 503: 'var(--danger)',
  }
  const getStatusColor = (code: number | null | undefined) => {
    if (code == null) return 'var(--text-2)'
    return STATUS_COLOR[code as keyof typeof STATUS_COLOR] || (code >= 200 && code < 300 ? 'var(--success)' : code >= 400 ? 'var(--danger)' : 'var(--text-2)')
  }

  // KPIs de la página visible; el total es el del filtro.
  const successCount = logs.filter(l => l.success).length
  const failCount = logs.filter(l => !l.success).length
  const cambiarFiltro = (fn: () => void) => { fn(); setPage(1) }

  return (
    <PageShell>
      <PageHeader
        icon={<Webhook size={18} />}
        title={t('webhooks.title')}
        subtitle={t('webhooks.subtitle')}
        actions={
          <button onClick={() => refetch()}
            style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
              borderRadius:8, padding:'7px 14px', color:'var(--text-1)',
              cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>
            🔄 Actualizar
          </button>
        }
      />

      {/* KPI cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap:12, marginBottom:16 }}>
        {[
          { label:'Webhooks configurados', value: webhooks.length, color:'var(--accent)' },
          { label:'Llamadas totales', value: total, color:'var(--text-1)' },
          { label:'Exitosas', value: successCount, color:'var(--success)' },
          { label:'Fallidas', value: failCount, color: failCount > 0 ? 'var(--danger)' : 'var(--text-3)' },
        ].map(kpi => (
          <div key={kpi.label} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
            borderRadius:12, padding:'14px 18px' }}>
            <div style={{ fontSize: "var(--text-2xl)", fontWeight:900, color:kpi.color,
              fontFamily: 'var(--font-mono)' }}>{kpi.value}</div>
            <div className="u-text2-sm-mt2">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginBottom:16 }}>
        <select aria-label="Webhook" value={webhookId} style={selectStyle}
          onChange={e => cambiarFiltro(() => setWebhookId(e.target.value))}>
          <option value="">Todos los webhooks</option>
          {webhooks.map(w => <option key={w.id} value={w.id}>{w.name || w.url}</option>)}
        </select>
        <select aria-label="Evento" value={event} style={selectStyle}
          onChange={e => cambiarFiltro(() => setEvent(e.target.value))}>
          <option value="">Todos los eventos</option>
          {eventos.map(ev => <option key={ev.value} value={ev.value}>{ev.label}</option>)}
        </select>
        <select aria-label="Resultado" value={estado} style={selectStyle}
          onChange={e => cambiarFiltro(() => setEstado(e.target.value as '' | 'ok' | 'ko'))}>
          <option value="">Exitosas y fallidas</option>
          <option value="ok">Solo exitosas</option>
          <option value="ko">Solo fallidas</option>
        </select>
      </div>

      {isLoading ? <Spinner /> : logs.length === 0 ? (
        <EmptyState icon="📡" title={t('webhooklog.sin_actividad_webhook')}
          description={webhooks.length === 0
            ? "Configura webhooks salientes en Empresa → Integraciones"
            : "Los webhooks configurados aún no han disparado llamadas"} />
      ) : (
        <>
        <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
          borderRadius:12, overflowX:'auto' }}>
          <Table
            data={logs}
            onRowClick={log => setSelectedLog(log)}
            columns={[
              { key: 'created_at', label: 'Timestamp', render: (_v, log) => (
                <span style={{ fontSize: "var(--text-sm)", fontFamily:'var(--font-mono)', color:'var(--text-2)', whiteSpace:'nowrap' }}>
                  {log.created_at ? log.created_at.slice(0, 19).replace('T', ' ') : '—'}
                </span>
              ) },
              { key: 'webhook_name', label: 'Webhook', render: (_v, log) => (
                <span className="u-base-600">{log.webhook_name || '—'}</span>
              ) },
              { key: 'event', label: 'Evento', render: (_v, log) => (
                <span style={{ fontSize: "var(--text-xs)", padding:'2px 8px', borderRadius:20,
                  background:'var(--accent-muted)', color:'var(--accent)' }}>
                  {log.event || '—'}
                </span>
              ) },
              { key: 'webhook_url', label: 'URL destino', render: (_v, log) => (
                <span style={{ display:'block', fontSize: "var(--text-xs)", color:'var(--text-2)', fontFamily:'var(--font-mono)', maxWidth:200,
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                  {log.webhook_url || '—'}
                </span>
              ) },
              { key: 'status_code', label: 'Status', render: (_v, log) => {
                const statusColor = log.success ? 'var(--success)' : getStatusColor(log.status_code ?? 500)
                return (
                  <span style={{ fontSize: "var(--text-sm)", fontWeight:800, padding:'2px 8px',
                    borderRadius:'var(--radius-sm)', fontFamily:'var(--font-mono)',
                    background:alpha(statusColor, '20'), color:statusColor }}>
                    {log.success ? '✓' : '✗'} {log.status_code || 'ERR'}
                  </span>
                )
              } },
              { key: 'duration_ms', label: 'Duración', render: (_v, log) => (
                <span style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', fontFamily:'var(--font-mono)' }}>
                  {log.duration_ms ? `${log.duration_ms}ms` : '—'}
                </span>
              ) },
            ]}
          />
        </div>
        {pages > 1 && (
          <div style={{ display:'flex', justifyContent:'flex-end', alignItems:'center', gap:8, marginTop:12 }}>
            <button disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} style={selectStyle}>‹</button>
            <span style={{ fontSize:'var(--text-sm)', color:'var(--text-2)' }}>{page} / {pages}</span>
            <button disabled={page >= pages} onClick={() => setPage(p => Math.min(pages, p + 1))} style={selectStyle}>›</button>
          </div>
        )}
        </>
      )}

      {/* Modal de detalle */}
      {selectedLog && (
        <Modal open onClose={() => setSelectedLog(null)}
          title={`Detalle — ${selectedLog.webhook_name || 'Webhook'}`} width={640}>
          <div className="u-stack-14">
            {[
              ['Timestamp', selectedLog.created_at?.slice(0,19).replace('T',' ') || '—'],
              ['Webhook', selectedLog.webhook_name || '—'],
              ['Evento', selectedLog.event || '—'],
              ['URL', selectedLog.webhook_url || '—'],
              ['HTTP Status', selectedLog.status_code || 'Error'],
              ['Duración', selectedLog.duration_ms ? `${selectedLog.duration_ms}ms` : '—'],
              ...(selectedLog.error ? [['Error', selectedLog.error]] : []),
            ].map(([label, value]) => (
              <div key={String(label)} style={{ display:'grid', gridTemplateColumns:'minmax(0, 130px) minmax(0, 1fr)', gap:10 }}>
                <span style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)',
                  textTransform:'uppercase', letterSpacing:'0.06em' }}>{label}</span>
                <span style={{ fontSize: "var(--text-base)", color:'var(--text-1)', wordBreak:'break-all' }}>{String(value)}</span>
              </div>
            ))}
            {Boolean(selectedLog.payload) && (
              <div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)',
                  textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:6 }}>Payload</div>
                <pre style={{ background:'var(--surface-3)', borderRadius:8, padding:12,
                  fontSize: "var(--text-xs)", color:'var(--success)', overflow:'auto',
                  maxHeight:200, fontFamily:'var(--font-mono)', margin:0 }}>
                  {JSON.stringify(
                    tryParseJson(selectedLog.payload), null, 2)}
                </pre>
              </div>
            )}
            {Boolean(selectedLog.response) && (
              <div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)',
                  textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:6 }}>Respuesta</div>
                <pre style={{ background:'var(--surface-3)', borderRadius:8, padding:12,
                  fontSize: "var(--text-xs)", color:'var(--text-2)', overflow:'auto',
                  maxHeight:120, fontFamily:'var(--font-mono)', margin:0 }}>
                  {String(selectedLog.response).slice(0, 500)}
                </pre>
              </div>
            )}
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
