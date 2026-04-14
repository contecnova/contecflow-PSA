/**
 * WebhookLogPage — Log de eventos webhook salientes
 * Tabla con últimas llamadas: timestamp, evento, URL, status HTTP, payload
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

export default function WebhookLogPage() {
  const t = useAppT()
  const [selectedLog, setSelectedLog] = useState(null)

  // Obtener los webhooks configurados
  const { data: webhooks = [] } = useQuery({
    queryKey: ['webhooks-list'],
    queryFn: () => api.get('/webhooks').then(r => r.data).catch(() => []),
  })

  // Obtener logs de todos los webhooks
  const { data: allLogs = [], isLoading, refetch } = useQuery({
    queryKey: ['webhook-logs-all'],
    queryFn: async () => {
      const results = await Promise.all(
        webhooks.map(w =>
          api.get(`/webhooks/${w.id}/logs`)
            .then(r => (r.data || []).map(l => ({
              ...l,
              webhook_name: w.name,
              webhook_url: w.url,
              event_type: w.event_type,
            })))
            .catch(() => [])
        )
      )
      return results.flat().sort((a, b) =>
        new Date(b.created_at || 0) - new Date(a.created_at || 0)
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
  const getStatusColor = (code) => STATUS_COLOR[code] || (code >= 200 && code < 300 ? 'var(--success)' : code >= 400 ? 'var(--danger)' : 'var(--text-2)')

  const successCount = allLogs.filter(l => l.http_status >= 200 && l.http_status < 300).length
  const failCount = allLogs.filter(l => !l.http_status || l.http_status >= 400).length

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title={t('webhooks.title')}
        subtitle="Historial de llamadas salientes y eventos entregados"
        actions={
          <button onClick={() => refetch()}
            style={{ background:'var(--surface-2)', border:'1px solid #1e2d45',
              borderRadius:8, padding:'7px 14px', color:'var(--text-1)',
              cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
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
          <div key={kpi.label} style={{ background:'var(--surface-2)', border:'1px solid #1e2d45',
            borderRadius:12, padding:'14px 18px' }}>
            <div style={{ fontSize:24, fontWeight:900, color:kpi.color,
              fontFamily:"'Space Mono',monospace" }}>{kpi.value}</div>
            <div style={{ fontSize:12, color:'var(--text-2)', marginTop:2 }}>{kpi.label}</div>
          </div>
        ))}
      </div>

      {isLoading ? <Spinner /> : allLogs.length === 0 ? (
        <EmptyState icon="📡" title="Sin registros de webhook"
          description={webhooks.length === 0
            ? "Configura webhooks salientes en Empresa → Integraciones"
            : "Los webhooks configurados aún no han disparado llamadas"} />
      ) : (
        <div style={{ background:'var(--surface-2)', border:'1px solid #1e2d45',
          borderRadius:12, overflow:'hidden' }}>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ borderBottom:'1px solid #1e2d45' }}>
                {['Timestamp','Webhook','Evento','URL destino','Status','Duración'].map(h => (
                  <th key={h} style={{ padding:'10px 14px', textAlign:'left', fontSize:11,
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
                    style={{ borderBottom:'1px solid #1e2d4520', cursor:'pointer' }}
                    onClick={() => setSelectedLog(log)}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <td style={{ padding:'10px 14px', fontSize:12,
                      fontFamily:'monospace', color:'var(--text-2)', whiteSpace:'nowrap' }}>
                      {log.created_at ? log.created_at.slice(0, 19).replace('T', ' ') : '—'}
                    </td>
                    <td style={{ padding:'10px 14px', fontSize:13, fontWeight:600 }}>
                      {log.webhook_name || '—'}
                    </td>
                    <td style={{ padding:'10px 14px' }}>
                      <span style={{ fontSize:11, padding:'2px 8px', borderRadius:20,
                        background:'var(--accent-muted)', color:'var(--accent)' }}>
                        {log.event_type || log.trigger_slug || '—'}
                      </span>
                    </td>
                    <td style={{ padding:'10px 14px', fontSize:11,
                      color:'var(--text-2)', fontFamily:'monospace', maxWidth:200,
                      overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                      {log.webhook_url || '—'}
                    </td>
                    <td style={{ padding:'10px 14px' }}>
                      <span style={{ fontSize:12, fontWeight:800, padding:'2px 8px',
                        borderRadius:6, fontFamily:'monospace',
                        background:`${statusColor}20`, color:statusColor }}>
                        {ok ? '✓' : '✗'} {log.http_status || 'ERR'}
                      </span>
                    </td>
                    <td style={{ padding:'10px 14px', fontSize:12,
                      color:'var(--text-2)', fontFamily:'monospace' }}>
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
                <span style={{ fontSize:11, fontWeight:700, color:'var(--text-2)',
                  textTransform:'uppercase', letterSpacing:'0.06em' }}>{label}</span>
                <span style={{ fontSize:13, color:'var(--text-1)', wordBreak:'break-all' }}>{String(value)}</span>
              </div>
            ))}
            {selectedLog.payload && (
              <div>
                <div style={{ fontSize:11, fontWeight:700, color:'var(--text-2)',
                  textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:6 }}>Payload</div>
                <pre style={{ background:'var(--surface-3)', borderRadius:8, padding:12,
                  fontSize:11, color:'var(--success)', overflow:'auto',
                  maxHeight:200, fontFamily:'monospace', margin:0 }}>
                  {JSON.stringify(
                    typeof selectedLog.payload === 'string'
                      ? JSON.parse(selectedLog.payload)
                      : selectedLog.payload, null, 2)}
                </pre>
              </div>
            )}
            {selectedLog.response_body && (
              <div>
                <div style={{ fontSize:11, fontWeight:700, color:'var(--text-2)',
                  textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:6 }}>Respuesta</div>
                <pre style={{ background:'var(--surface-3)', borderRadius:8, padding:12,
                  fontSize:11, color:'var(--text-2)', overflow:'auto',
                  maxHeight:120, fontFamily:'monospace', margin:0 }}>
                  {String(selectedLog.response_body).slice(0, 500)}
                </pre>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}
