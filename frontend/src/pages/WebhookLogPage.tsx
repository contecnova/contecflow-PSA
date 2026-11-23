/**
 * WebhookLogPage — Log de eventos webhook salientes
 * Tabla con últimas llamadas: timestamp, evento, URL, status HTTP, payload
 *
 * 16-11-2026: título del menú (nav.webhook_log, antes "Log de Webhooks");
 * "Refrescar" con Button e icono (antes un emoji en el texto); KPIs con KpiCard
 * (antes cifra monoespaciada en negrita); filtros con ds-input; estado HTTP y
 * evento con StatusBadge; vacío con EmptyState e icono lucide (antes un emoji);
 * paginación con el componente común.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { enterpriseApi } from '../services/api'
import type { EntregaDeWebhook } from '../services/api/tipos-plataforma'
import { Button, Card, EmptyState, KpiCard, Modal, Spinner, StatusBadge, Table, Select } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Activity, Check, CheckCircle2, RefreshCw, Webhook, X, XCircle } from 'lucide-react'
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
    queryFn: () => enterpriseApi.outboundWebhooks().then(r => r.data),
  })

  // Auditoría 22-11-2026 (A44): los suspendidos por el cortacircuitos se ven y se reactivan.
  const qc = useQueryClient()
  const suspendidos = webhooks.filter(w => w.suspended)
  const { mutate: reactivar, isPending: reactivando } = useMutation({
    mutationFn: (id: string) => enterpriseApi.reactivateWebhook(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['outbound-webhooks'] }),
  })

  const { data: eventos = [] } = useQuery({
    queryKey: ['outbound-webhook-events'],
    queryFn: () => enterpriseApi.outboundWebhookEvents().then(r => r.data),
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

  // KPIs de la página visible; el total es el del filtro.
  const successCount = logs.filter(l => l.success).length
  const failCount = logs.filter(l => !l.success).length
  const cambiarFiltro = (fn: () => void) => { fn(); setPage(1) }

  return (
    <PageShell>
      <PageHeader
        icon={<Webhook size={18} />}
        title={t('nav.webhook_log')}
        subtitle={t('webhooks.subtitle')}
        actions={
          <Button variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetch()}>
            {t('common.refresh')}
          </Button>
        }
      />

      <div className="ds-page">
      <div className="ds-grid-stats">
        <KpiCard icon={<Webhook size={16} />} label={t('webhook_log_page.kpi_configurados')} value={fmtEntero(webhooks.length)} />
        <KpiCard icon={<Activity size={16} />} label={t('webhook_log_page.kpi_totales')} value={fmtEntero(total)} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('webhook_log_page.kpi_exitosas')} value={fmtEntero(successCount)} />
        <KpiCard icon={<XCircle size={16} />} label={t('webhook_log_page.kpi_fallidas')} value={fmtEntero(failCount)} danger={failCount > 0} />
      </div>

      {suspendidos.length > 0 && (
        <Card>
          <strong>{t('webhook_log_page.suspendidos')}</strong>
          {suspendidos.map(w => (
            <div key={w.id} className="ds-toolbar">
              <span>{w.name || w.url} — {t('webhook_log_page.fallos_seguidos', { n: w.consecutive_failures ?? 0 })}</span>
              <Button size="sm" disabled={reactivando} onClick={() => reactivar(w.id)}>{t('webhook_log_page.reactivar')}</Button>
            </div>
          ))}
        </Card>
      )}

      <div className="ds-toolbar">
        <Select suelto placeholder={false} aria-label={t('webhook_log_page.col_webhook')} value={webhookId} className="whl-select"
          onChange={e => cambiarFiltro(() => setWebhookId(e.target.value))}>
          <option value="">{t('webhook_log_page.todos_webhooks')}</option>
          {webhooks.map(w => <option key={w.id} value={w.id}>{w.name || w.url}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={t('webhook_log_page.col_evento')} value={event} className="whl-select"
          onChange={e => cambiarFiltro(() => setEvent(e.target.value))}>
          <option value="">{t('webhook_log_page.todos_eventos')}</option>
          {eventos.map(ev => <option key={ev.value} value={ev.value}>{ev.label}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={t('webhook_log_page.resultado')} value={estado} className="whl-select"
          onChange={e => cambiarFiltro(() => setEstado(e.target.value as '' | 'ok' | 'ko'))}>
          <option value="">{t('webhook_log_page.exitosas_y_fallidas')}</option>
          <option value="ok">{t('webhook_log_page.solo_exitosas')}</option>
          <option value="ko">{t('webhook_log_page.solo_fallidas')}</option>
        </Select>
      </div>

      {isLoading ? <Spinner /> : logs.length === 0 ? (
        <EmptyState icon={<Webhook size={28} />} title={t('webhooklog.sin_actividad_webhook')}
          description={webhooks.length === 0
            ? t('webhook_log_page.vacio_sin_webhooks')
            : t('webhook_log_page.vacio_sin_llamadas')} />
      ) : (
        <>
        <Card className="whl-table-wrap">
          <Table
            data={logs}
            onRowClick={log => setSelectedLog(log)}
            columns={[
              { key: 'created_at', label: t('webhook_log_page.col_fecha'), render: (_v, log) => (
                <span className="whl-muted-sm whl-nowrap">
                  {fmtFechaHora(log.created_at)}
                </span>
              ) },
              { key: 'webhook_name', label: t('webhook_log_page.col_webhook'), render: (_v, log) => (
                <span className="u-base-600">{log.webhook_name || '—'}</span>
              ) },
              { key: 'event', label: t('webhook_log_page.col_evento'), render: (_v, log) => (
                log.event ? <StatusBadge kind="accent" caps={false}>{log.event}</StatusBadge> : <span className="whl-muted-sm">—</span>
              ) },
              { key: 'webhook_url', label: t('webhook_log_page.col_url'), render: (_v, log) => (
                <span className="ds-codigo whl-url" title={log.webhook_url || undefined}>
                  {log.webhook_url || '—'}
                </span>
              ) },
              { key: 'status_code', label: t('webhook_log_page.col_status'), render: (_v, log) => (
                <StatusBadge kind={log.success ? 'success' : 'danger'} caps={false}>
                  <span className="whl-status">
                    {log.success ? <Check size={12} aria-hidden="true" /> : <X size={12} aria-hidden="true" />}
                    {log.status_code || t('webhook_log_page.error')}
                  </span>
                </StatusBadge>
              ) },
              { key: 'duration_ms', label: t('webhook_log_page.col_duracion'), render: (_v, log) => (
                <span className="whl-muted-sm">
                  {log.duration_ms ? `${fmtEntero(log.duration_ms)} ms` : '—'}
                </span>
              ) },
            ]}
          />
        </Card>
        {pages > 1 && (
          <Pagination page={page} totalPages={pages} onChange={setPage} total={total} pageSize={PAGE_SIZE} />
        )}
        </>
      )}
      </div>

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
                <pre className="ds-codigo whl-pre whl-pre--payload">
                  {JSON.stringify(
                    tryParseJson(selectedLog.payload), null, 2)}
                </pre>
              </div>
            )}
            {Boolean(selectedLog.response) && (
              <div>
                <div className="whl-detail-label whl-detail-label--block">{t('webhook_log_page.respuesta')}</div>
                <pre className="ds-codigo whl-pre">
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
