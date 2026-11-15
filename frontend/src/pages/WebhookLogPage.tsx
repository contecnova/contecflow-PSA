/**
 * WebhookLogPage — Log de eventos webhook salientes
 * Tabla con últimas llamadas: timestamp, evento, URL, status HTTP, payload
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { enterpriseApi } from '../services/api'
import type { EntregaDeWebhook, EventoDeWebhook, WebhookSaliente } from '../services/api/tipos-plataforma'
import { Spinner, EmptyState, Modal, Table } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Webhook } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { formateadorDeFecha, localeActivo } from '../utils/helpers'
import { POLL_FREQUENT_MS } from '../constants/timings'
import './WebhookLogPage.css'

const PAGE_SIZE = 50

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
  // Fecha, hora y cifras en el idioma activo (antes, ISO recortado a mano).
  const fmtFechaHora = (d?: string | null) => d ? formateadorDeFecha({ day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(d)) : '—'
  const fmtEntero = (n: number) => new Intl.NumberFormat(localeActivo()).format(n)
  const [selectedLog, setSelectedLog] = useState<EntregaDeWebhook | null>(null)
  const [webhookId, setWebhookId] = useState('')
  const [event, setEvent] = useState('')
  const [estado, setEstado] = useState<'' | 'ok' | 'ko'>('')
  const [page, setPage] = useState(1)

  // Webhooks salientes configurados (para el filtro y el KPI)
  const { data: webhooks = [] } = useQuery({
    queryKey: ['outbound-webhooks'],
    queryFn: () => enterpriseApi.outboundWebhooks().then(r => r.data).catch((): WebhookSaliente[] => []),
  })

  const { data: eventos = [] } = useQuery({
    queryKey: ['outbound-webhook-events'],
    queryFn: () => enterpriseApi.outboundWebhookEvents().then(r => r.data).catch((): EventoDeWebhook[] => []),
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
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['webhook-deliveries', filtros],
    // El interceptor deja la lista en `r.data` y la paginación en `r.meta`.
    queryFn: () => enterpriseApi.webhookDeliveries(filtros).then(r => ({ items: r.data, total: r.meta?.total ?? r.data.length })),
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
          <button type="button" onClick={() => refetch()} className="whl-btn whl-btn--refresh">
            🔄 {t('common.refresh')}
          </button>
        }
      />

      {/* KPI cards */}
      <div className="whl-kpis">
        {[
          { label: t('webhook_log_page.kpi_configurados'), value: webhooks.length, color: 'var(--accent)' },
          { label: t('webhook_log_page.kpi_totales'), value: total, color: 'var(--text-1)' },
          { label: t('webhook_log_page.kpi_exitosas'), value: successCount, color: 'var(--success)' },
          { label: t('webhook_log_page.kpi_fallidas'), value: failCount, color: failCount > 0 ? 'var(--danger)' : 'var(--text-3)' },
        ].map(kpi => (
          <div key={kpi.label} className="whl-kpi">
            <div className="whl-kpi-value" style={{ '--whl-color': kpi.color } as CSSProperties}>{fmtEntero(kpi.value)}</div>
            <div className="u-text2-sm-mt2">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div className="whl-filters">
        <select aria-label={t('webhook_log_page.col_webhook')} value={webhookId} className="whl-select"
          onChange={e => cambiarFiltro(() => setWebhookId(e.target.value))}>
          <option value="">{t('webhook_log_page.todos_webhooks')}</option>
          {webhooks.map(w => <option key={w.id} value={w.id}>{w.name || w.url}</option>)}
        </select>
        <select aria-label={t('webhook_log_page.col_evento')} value={event} className="whl-select"
          onChange={e => cambiarFiltro(() => setEvent(e.target.value))}>
          <option value="">{t('webhook_log_page.todos_eventos')}</option>
          {eventos.map(ev => <option key={ev.value} value={ev.value}>{ev.label}</option>)}
        </select>
        <select aria-label={t('webhook_log_page.resultado')} value={estado} className="whl-select"
          onChange={e => cambiarFiltro(() => setEstado(e.target.value as '' | 'ok' | 'ko'))}>
          <option value="">{t('webhook_log_page.exitosas_y_fallidas')}</option>
          <option value="ok">{t('webhook_log_page.solo_exitosas')}</option>
          <option value="ko">{t('webhook_log_page.solo_fallidas')}</option>
        </select>
      </div>

      {isLoading ? <Spinner /> : logs.length === 0 ? (
        <EmptyState icon="📡" title={t('webhooklog.sin_actividad_webhook')}
          description={webhooks.length === 0
            ? t('webhook_log_page.vacio_sin_webhooks')
            : t('webhook_log_page.vacio_sin_llamadas')} />
      ) : (
        <>
        <div className="whl-table-wrap">
          <Table
            data={logs}
            onRowClick={log => setSelectedLog(log)}
            columns={[
              { key: 'created_at', label: t('webhook_log_page.col_fecha'), render: (_v, log) => (
                <span className="whl-mono-sm whl-nowrap">
                  {fmtFechaHora(log.created_at)}
                </span>
              ) },
              { key: 'webhook_name', label: t('webhook_log_page.col_webhook'), render: (_v, log) => (
                <span className="u-base-600">{log.webhook_name || '—'}</span>
              ) },
              { key: 'event', label: t('webhook_log_page.col_evento'), render: (_v, log) => (
                <span className="whl-event">
                  {log.event || '—'}
                </span>
              ) },
              { key: 'webhook_url', label: t('webhook_log_page.col_url'), render: (_v, log) => (
                <span className="whl-url" title={log.webhook_url || undefined}>
                  {log.webhook_url || '—'}
                </span>
              ) },
              { key: 'status_code', label: t('webhook_log_page.col_status'), render: (_v, log) => {
                const statusColor = log.success ? 'var(--success)' : getStatusColor(log.status_code ?? 500)
                return (
                  <span className="whl-status" style={{ '--whl-color': statusColor } as CSSProperties}>
                    {log.success ? '✓' : '✗'} {log.status_code || 'ERR'}
                  </span>
                )
              } },
              { key: 'duration_ms', label: t('webhook_log_page.col_duracion'), render: (_v, log) => (
                <span className="whl-mono-sm">
                  {log.duration_ms ? `${fmtEntero(log.duration_ms)} ms` : '—'}
                </span>
              ) },
            ]}
          />
        </div>
        {pages > 1 && (
          <nav className="whl-pager" aria-label={t('webhook_log_page.paginacion')}>
            <button type="button" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} className="whl-btn" aria-label={t('webhook_log_page.pagina_anterior')}>‹</button>
            <span className="whl-pager-info" aria-live="polite">{page} / {pages}</span>
            <button type="button" disabled={page >= pages} onClick={() => setPage(p => Math.min(pages, p + 1))} className="whl-btn" aria-label={t('webhook_log_page.pagina_siguiente')}>›</button>
          </nav>
        )}
        </>
      )}

      {/* Modal de detalle */}
      {selectedLog && (
        <Modal open onClose={() => setSelectedLog(null)}
          title={t('webhook_log_page.detalle', { nombre: selectedLog.webhook_name || t('webhook_log_page.col_webhook') })} width={640}>
          <div className="u-stack-14">
            {[
              [t('webhook_log_page.col_fecha'), fmtFechaHora(selectedLog.created_at)],
              [t('webhook_log_page.col_webhook'), selectedLog.webhook_name || '—'],
              [t('webhook_log_page.col_evento'), selectedLog.event || '—'],
              [t('webhook_log_page.col_url'), selectedLog.webhook_url || '—'],
              [t('webhook_log_page.http_status'), selectedLog.status_code || t('webhook_log_page.error')],
              [t('webhook_log_page.col_duracion'), selectedLog.duration_ms ? `${fmtEntero(selectedLog.duration_ms)} ms` : '—'],
              ...(selectedLog.error ? [[t('webhook_log_page.error'), selectedLog.error]] : []),
            ].map(([label, value]) => (
              <div key={String(label)} className="whl-detail-row">
                <span className="whl-detail-label">{label}</span>
                <span className="whl-detail-value">{String(value)}</span>
              </div>
            ))}
            {Boolean(selectedLog.payload) && (
              <div>
                <div className="whl-detail-label whl-detail-label--block">{t('webhook_log_page.payload')}</div>
                <pre className="whl-pre whl-pre--payload">
                  {JSON.stringify(
                    tryParseJson(selectedLog.payload), null, 2)}
                </pre>
              </div>
            )}
            {Boolean(selectedLog.response) && (
              <div>
                <div className="whl-detail-label whl-detail-label--block">{t('webhook_log_page.respuesta')}</div>
                <pre className="whl-pre">
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
