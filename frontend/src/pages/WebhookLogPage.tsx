/**
 * WebhookLogPage — Log de eventos webhook salientes
 * Tabla con últimas llamadas: timestamp, evento, URL, status HTTP, payload
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { webhooksApi } from '../services/api'
import { Spinner, EmptyState, Modal, Table } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Webhook } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { POLL_FREQUENT_MS } from '../constants/timings'

interface WebhookItem {
  id: string | number
  name?: string
  url?: string
  event_type?: string
}

interface WebhookLogItem {
  id?: string | number
  created_at?: string
  payload?: unknown
  response_body?: unknown
  http_status?: number
  duration_ms?: number
  trigger_slug?: string
  webhook_name?: string
  webhook_url?: string
  event_type?: string
}

function tryParseJson(value: unknown): unknown {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

export default function WebhookLogPage() {
  const t = useAppT()
  const [selectedLog, setSelectedLog] = useState<WebhookLogItem | null>(null)

  // Obtener los webhooks configurados
  const { data: webhooks = [] } = useQuery<WebhookItem[]>({
    queryKey: ['webhooks-list'],
    queryFn: () => webhooksApi.list().then(r => r.data?.items ?? r.data ?? []).catch(() => []),
  })

  // Obtener logs de todos los webhooks.
  // Auditoria 2026-11 (#45): la clave no llevaba los webhooks de los que
  // depende, asi que al crear o borrar uno se seguian ensenando los logs
  // cacheados de la lista anterior. Ahora la clave incluye sus ids.
  // N+1 pendiente: el backend solo expone /webhooks/{id}/logs; una peticion por
  // webhook (en paralelo) hasta que haya un endpoint agregado.
  const validWebhooks = webhooks.filter((w) => w && w.id)
  const idsWebhooks = validWebhooks.map(w => w.id)
  const { data: allLogs = [], isLoading, refetch } = useQuery<WebhookLogItem[]>({
    queryKey: ['webhook-logs-all', idsWebhooks],
    queryFn: async () => {
      const results = await Promise.all(
        validWebhooks.map((w) =>
          webhooksApi.logs(w.id)
            .then(r => ((r.data || []) as WebhookLogItem[]).map(l => ({
              ...l,
              webhook_name: w.name,
              webhook_url: w.url,
              event_type: w.event_type,
            })))
            .catch(() => [])
        )
      )
      return results.flat().sort((a, b) =>
        new Date(b.created_at || '').getTime() - new Date(a.created_at || '').getTime()
      )
    },
    enabled: webhooks.length > 0,
    refetchInterval: POLL_FREQUENT_MS,
  })

  const STATUS_COLOR = {
    200: 'var(--success)', 201: 'var(--success)', 204: 'var(--success)',
    400: 'var(--warning)', 401: 'var(--warning)', 403: 'var(--danger)',
    404: 'var(--warning)', 500: 'var(--danger)', 503: 'var(--danger)',
  }
  const getStatusColor = (code: number | undefined) => {
    if (code == null) return 'var(--text-2)'
    return STATUS_COLOR[code as keyof typeof STATUS_COLOR] || (code >= 200 && code < 300 ? 'var(--success)' : code >= 400 ? 'var(--danger)' : 'var(--text-2)')
  }

  const successCount = allLogs.filter(l => (l.http_status ?? 0) >= 200 && (l.http_status ?? 0) < 300).length
  const failCount = allLogs.filter(l => !l.http_status || l.http_status >= 400).length

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
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap:12, marginBottom:24 }}>
        {[
          { label:'Webhooks configurados', value: webhooks.length, color:'var(--accent)' },
          { label:'Llamadas totales', value: allLogs.length, color:'var(--text-1)' },
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

      {isLoading ? <Spinner /> : allLogs.length === 0 ? (
        <EmptyState icon="📡" title={t('webhooklog.sin_actividad_webhook')}
          description={webhooks.length === 0
            ? "Configura webhooks salientes en Empresa → Integraciones"
            : "Los webhooks configurados aún no han disparado llamadas"} />
      ) : (
        <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
          borderRadius:12, overflowX:'auto' }}>
          <Table
            data={allLogs.slice(0, 200)}
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
              { key: 'event_type', label: 'Evento', render: (_v, log) => (
                <span style={{ fontSize: "var(--text-xs)", padding:'2px 8px', borderRadius:20,
                  background:'var(--accent-muted)', color:'var(--accent)' }}>
                  {log.event_type || log.trigger_slug || '—'}
                </span>
              ) },
              { key: 'webhook_url', label: 'URL destino', render: (_v, log) => (
                <span style={{ display:'block', fontSize: "var(--text-xs)", color:'var(--text-2)', fontFamily:'var(--font-mono)', maxWidth:200,
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                  {log.webhook_url || '—'}
                </span>
              ) },
              { key: 'http_status', label: 'Status', render: (_v, log) => {
                const statusColor = getStatusColor(log.http_status)
                const ok = (log.http_status ?? 0) >= 200 && (log.http_status ?? 0) < 300
                return (
                  <span style={{ fontSize: "var(--text-sm)", fontWeight:800, padding:'2px 8px',
                    borderRadius:'var(--radius-sm)', fontFamily:'var(--font-mono)',
                    background:alpha(statusColor, '20'), color:statusColor }}>
                    {ok ? '✓' : '✗'} {log.http_status || 'ERR'}
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
      )}

      {/* Modal de detalle */}
      {selectedLog && (
        <Modal open onClose={() => setSelectedLog(null)}
          title={`Detalle — ${selectedLog.webhook_name || 'Webhook'}`} width={640}>
          <div className="u-stack-14">
            {[
              ['Timestamp', selectedLog.created_at?.slice(0,19).replace('T',' ') || '—'],
              ['Webhook', selectedLog.webhook_name || '—'],
              ['Evento', selectedLog.event_type || selectedLog.trigger_slug || '—'],
              ['URL', selectedLog.webhook_url || '—'],
              ['HTTP Status', selectedLog.http_status || 'Error'],
              ['Duración', selectedLog.duration_ms ? `${selectedLog.duration_ms}ms` : '—'],
            ].map(([label, value]) => (
              <div key={label} style={{ display:'grid', gridTemplateColumns:'minmax(0, 130px) minmax(0, 1fr)', gap:10 }}>
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
            {Boolean(selectedLog.response_body) && (
              <div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)',
                  textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:6 }}>Respuesta</div>
                <pre style={{ background:'var(--surface-3)', borderRadius:8, padding:12,
                  fontSize: "var(--text-xs)", color:'var(--text-2)', overflow:'auto',
                  maxHeight:120, fontFamily:'var(--font-mono)', margin:0 }}>
                  {String(selectedLog.response_body).slice(0, 500)}
                </pre>
              </div>
            )}
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
