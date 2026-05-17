/**
 * WebhookLogPage — Log de eventos webhook salientes
 * Tabla con últimas llamadas: timestamp, evento, URL, status HTTP, payload
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { webhooksApi } from '../services/api'
import { Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Webhook } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

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

  // Obtener logs de todos los webhooks
  const { data: allLogs = [], isLoading, refetch } = useQuery<WebhookLogItem[]>({
    queryKey: ['webhook-logs-all'],
    queryFn: async () => {
      const validWebhooks = webhooks.filter((w) => w && w.id)
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
    refetchInterval: 30000,
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

  const successCount = allLogs.filter(l => l.http_status >= 200 && l.http_status < 300).length
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
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:24 }}>
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
            <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginTop:2 }}>{kpi.label}</div>
          </div>
        ))}
      </div>

      {isLoading ? <Spinner /> : allLogs.length === 0 ? (
        <EmptyState icon="📡" title="Sin actividad webhook"
          description={webhooks.length === 0
            ? "Configura webhooks salientes en Empresa → Integraciones"
            : "Los webhooks configurados aún no han disparado llamadas"} />
      ) : (
        <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
          borderRadius:12, overflow:'hidden' }}>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ borderBottom:'1px solid var(--surface-4)' }}>
                {['Timestamp','Webhook','Evento','URL destino','Status','Duración'].map(h => (
                  <th key={h} style={{ padding:'10px 14px', textAlign:'left', fontSize: "var(--text-xs)",
                    fontWeight:700, color:'var(--text-2)', textTransform:'uppercase',
                    letterSpacing:'0.06em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allLogs.slice(0, 200).map((log, i) => {
                const statusColor = getStatusColor(log.http_status)
                const ok = log.http_status >= 200 && log.http_status < 300
                return (
                  <tr key={log.id || i}
                    style={{ borderBottom:'1px solid var(--surface-4)20', cursor:'pointer' }}
                    onClick={() => setSelectedLog(log)}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <td style={{ padding:'10px 14px', fontSize: "var(--text-sm)",
                      fontFamily:'var(--font-mono)', color:'var(--text-2)', whiteSpace:'nowrap' }}>
                      {log.created_at ? log.created_at.slice(0, 19).replace('T', ' ') : '—'}
                    </td>
                    <td style={{ padding:'10px 14px', fontSize: "var(--text-base)", fontWeight:600 }}>
                      {log.webhook_name || '—'}
                    </td>
                    <td style={{ padding:'10px 14px' }}>
                      <span style={{ fontSize: "var(--text-xs)", padding:'2px 8px', borderRadius:20,
                        background:'var(--accent-muted)', color:'var(--accent)' }}>
                        {log.event_type || log.trigger_slug || '—'}
                      </span>
                    </td>
                    <td style={{ padding:'10px 14px', fontSize: "var(--text-xs)",
                      color:'var(--text-2)', fontFamily:'var(--font-mono)', maxWidth:200,
                      overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                      {log.webhook_url || '—'}
                    </td>
                    <td style={{ padding:'10px 14px' }}>
                      <span style={{ fontSize: "var(--text-sm)", fontWeight:800, padding:'2px 8px',
                        borderRadius:6, fontFamily:'var(--font-mono)',
                        background:`${statusColor}20`, color:statusColor }}>
                        {ok ? '✓' : '✗'} {log.http_status || 'ERR'}
                      </span>
                    </td>
                    <td style={{ padding:'10px 14px', fontSize: "var(--text-sm)",
                      color:'var(--text-2)', fontFamily:'var(--font-mono)' }}>
                      {log.duration_ms ? `${log.duration_ms}ms` : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal de detalle */}
      {selectedLog && (
        <Modal open onClose={() => setSelectedLog(null)}
          title={`Detalle — ${selectedLog.webhook_name || 'Webhook'}`} width={640}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {[
              ['Timestamp', selectedLog.created_at?.slice(0,19).replace('T',' ') || '—'],
              ['Webhook', selectedLog.webhook_name || '—'],
              ['Evento', selectedLog.event_type || selectedLog.trigger_slug || '—'],
              ['URL', selectedLog.webhook_url || '—'],
              ['HTTP Status', selectedLog.http_status || 'Error'],
              ['Duración', selectedLog.duration_ms ? `${selectedLog.duration_ms}ms` : '—'],
            ].map(([label, value]) => (
              <div key={label} style={{ display:'grid', gridTemplateColumns:'130px 1fr', gap:10 }}>
                <span style={{ fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)',
                  textTransform:'uppercase', letterSpacing:'0.06em' }}>{label}</span>
                <span style={{ fontSize: "var(--text-base)", color:'var(--text-1)', wordBreak:'break-all' }}>{String(value)}</span>
              </div>
            ))}
            {selectedLog.payload && (
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
            {selectedLog.response_body && (
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
