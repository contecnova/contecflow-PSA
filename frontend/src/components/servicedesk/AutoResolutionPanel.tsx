/**
 * AutoResolutionPanel — resolución automática de tickets con IA (Service Desk → Herramientas).
 *
 * Backend endpoints:
 *   GET  /sd/auto-resolution/stats                   -> { total_auto_resolved, pct_of_all_tickets, feedback_total_validated, overall_success_rate, per_bucket: [{bucket, total, success, failed, success_rate}] }
 *   POST /sd/auto-resolution/run-job                 -> { processed, auto_resolved, suggested, failed, status, timestamp }
 *   POST /sd/auto-resolution/run-close-job           -> { processed, auto_closed, validated, failed, status, timestamp }
 *   POST /sd/tickets/{id}/auto-resolution/feedback   { success: bool } -> { recorded, ticket_id, success }
 *
 * 16-11-2026 (pasada de diseño): rehecho con los componentes comunes (Card +
 * Section, KpiCard en `ds-grid-stats`, StatusBadge, Input, Button con icono
 * lucide). Antes tenía tarjetas de cifra propias con fondo tintado, emojis en
 * los títulos y botones (⚙️ 📊 🩺 📋 ⚡ 💬 ▶ 🔒 👍 👎), textos fijos en
 * castellano (estado del proceso, «de todos los tickets», «Excelente»...) y
 * jerga («bucket», «job», «feedback»). Las fechas usan el formateador del idioma.
 *
 * 19-11-2026: la tarjeta «Configuración» (umbrales, cierre automático,
 * ventana de validación, lote) vive en Configuración → Service desk →
 * Autorresolución (`/settings/sd-autorresolucion`, ConfigAutoResolucion.tsx).
 * Aquí no hay botón «Configurar»; el lote
 * de «Ejecutar» se sigue leyendo de la configuración guardada.
 */
import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, History, Lock, MessageSquareText, Play, ShieldCheck, ThumbsDown, ThumbsUp, Activity, Layers, Gauge } from 'lucide-react'
import { autoResolutionApi, ticketsApi } from '../../services/api'
import type { ConfigDeAutoResolucion, EstadisticasDeAutoResolucion } from '../../services/api/tipos-analitica'
import { Card, Button, Pulsable, Spinner, Modal, KpiCard, Input, Section, EmptyState } from '../ui'
import { useAuth } from '../../context/AuthContext'
import StatusBadge from '../ui/StatusBadge'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { fmtDateTime } from '../../utils/helpers'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import './AutoResolutionPanel.css'

type AutoResolutionConfig = Partial<ConfigDeAutoResolucion>
type AutoResolutionStats = EstadisticasDeAutoResolucion

const errMsg = (e: unknown, fallback: string): string => {
  const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail || fallback
}

/** Título de tarjeta con icono, como en el resto de pantallas. */
const Titulo = ({ icon, children }: { icon: ReactNode; children: ReactNode }) => (
  <span className="arp-titulo">{icon}{children}</span>
)

/** Color de una tasa de acierto (0-100). */
const kindDeTasa = (r: number | null | undefined): StatusBadgeKind =>
  r == null ? 'neutral' : r >= 85 ? 'success' : r >= 60 ? 'warning' : 'danger'

function formatDurationMs(ms: number | null | undefined): string {
  if (!Number.isFinite(ms) || ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  const sec = Math.round(ms / 1000)
  if (sec < 60) return `${sec} s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  return `${min} min ${rem} s`
}

function FeedbackModal({ ticketId, onClose }: { ticketId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [success, setSuccess] = useState<boolean>(true)

  const { mutate, isPending } = useMutation({
    mutationFn: () => ticketsApi.autoResolutionFeedback(ticketId, { success }),
    onSuccess: () => {
      toast.success(t('autoresolution.feedback_registrado'))
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
      onClose()
    },
    onError: (e) => toast.error(errMsg(e, t('autoresolution.error_feedback'))),
  })

  return (
    <Modal open title={t('autoresolution.feedback_titulo', { ticket: ticketId })} onClose={onClose} size="sm">
      <div className="u-stack-16">
        <div className="u-stack-8">
          <div className="campo-etiqueta">{t('autoresolution.la_auto_resolucion_fue_correcta')}</div>
          <div className="arp-eleccion" role="group" aria-label={t('autoresolution.la_auto_resolucion_fue_correcta')}>
            <Pulsable className="arp-opcion" aria-pressed={success} onClick={() => setSuccess(true)}>
              <ThumbsUp size={14} aria-hidden="true" />{t('autoresolution.correcta')}
            </Pulsable>
            <Pulsable className="arp-opcion" aria-pressed={!success} onClick={() => setSuccess(false)}>
              <ThumbsDown size={14} aria-hidden="true" />{t('autoresolution.fallo')}
            </Pulsable>
          </div>
        </div>
        <div className="u-text3-xs">{t('autoresolution.feedback_explica')}</div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} loading={isPending}>{t('autoresolution.enviar_feedback')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function AutoResolutionPanel() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [feedbackTicketId, setFeedbackTicketId] = useState<string | null>(null)
  const [buscado, setBuscado] = useState('')
  const configura = useAuth().puede('sd.administrar')

  // Solo para el lote de «Ejecutar»; la configuración se edita en Configuración.
  // El GET es solo admin: sin la capacidad no se pide (antes daba 403).
  const { data: config } = useQuery<AutoResolutionConfig>({
    queryKey: ['sd-auto-resolution-config'],
    queryFn: () => autoResolutionApi.getConfig().then(r => r.data),
    enabled: configura,
  })

  const { data: stats, isLoading: statsLoading } = useQuery<AutoResolutionStats>({
    queryKey: ['sd-auto-resolution-stats'],
    queryFn: () => autoResolutionApi.getStats().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { mutate: runJob, isPending: runningJob } = useMutation({
    mutationFn: () => autoResolutionApi.runJob({ run_async: true, limit: config?.default_job_limit ?? 25 }),
    onSuccess: (res) => {
      const r = res.data
      if (r.status === 'queued') {
        toast.success(t('autoresolution.job_encolado', { limit: r.limit }))
      } else if (r.status === 'already_running') {
        toast.warning(t('autoresolution.ya_hay_un_job'))
      } else {
        toast.success(t('autoresolution.job_resultado', { processed: r.processed ?? 0, auto_resolved: r.auto_resolved ?? 0, suggested: r.suggested ?? 0, failed: r.failed ?? 0 }))
      }
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: (e) => toast.error(errMsg(e, t('autoresolution.error_ejecutar'))),
  })

  const { mutate: runCloseJob, isPending: runningClose } = useMutation({
    mutationFn: () => autoResolutionApi.runCloseJob(),
    onSuccess: (res) => {
      const r = res.data
      toast.success(t('autoresolution.auto_cierre_resultado', { auto_closed: r.auto_closed ?? 0, validated: r.validated ?? 0, failed: r.failed ?? 0 }))
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: (e) => toast.error(errMsg(e, t('autoresolution.error_cierre'))),
  })

  const successRate = stats?.overall_success_rate
  const buckets = stats?.per_bucket ?? []
  const topBuckets = buckets.slice(0, 6)
  const runtime = stats?.runtime || null
  const jobHistory = stats?.job_history ?? []
  const runtimeStatus = runtime?.running ? 'running' : runtime?.status || 'never_run'
  const runtimeKind: StatusBadgeKind = runtimeStatus === 'running' ? 'accent'
    : runtimeStatus === 'completed' ? 'success' : runtimeStatus === 'failed' ? 'danger' : 'neutral'
  const tasaSub = successRate == null ? t('autoresolution.tasa_sin_datos')
    : successRate >= 85 ? t('autoresolution.tasa_excelente') : successRate >= 60 ? t('autoresolution.tasa_aceptable') : t('autoresolution.tasa_ajustar')

  /** «categoría::prioridad» → «Categoría · P2 Alto». */
  const nombreDeGrupo = (bucket: string) => {
    const [cat, prio] = bucket.split('::')
    const categoria = !cat || cat === 'unknown' ? t('autoresolution.sin_categoria') : cat
    return prio ? `${categoria} · ${etiquetaCodigo(t, 'estado', prio)}` : categoria
  }

  return (
    <div className="u-stack-16">
      {/* Resultados */}
      {statsLoading ? <div className="arp-cargando"><Spinner /></div> : (
        <div className="ds-grid-stats">
          <KpiCard icon={<CheckCircle2 size={16} />} label={t('autoresolution.auto_resueltos_total')} value={stats?.total_auto_resolved ?? '—'}
            sub={stats?.pct_of_all_tickets != null ? t('autoresolution.pct_de_todos', { p: stats.pct_of_all_tickets }) : undefined} />
          <KpiCard icon={<MessageSquareText size={16} />} label={t('autoresolution.feedback_validado')} value={stats?.feedback_total_validated ?? '—'}
            sub={t('autoresolution.feedback_validado_sub')} />
          <KpiCard icon={<Gauge size={16} />} label={t('autoresolution.tasa_de_exito_global')} value={successRate != null ? `${successRate} %` : '—'}
            sub={tasaSub} accent={successRate != null && successRate >= 85} warning={successRate != null && successRate >= 60 && successRate < 85}
            danger={successRate != null && successRate < 60} />
          <KpiCard icon={<Layers size={16} />} label={t('autoresolution.buckets_con_datos')} value={buckets.length} />
        </div>
      )}

      <div className="arp-grid">
        {/* Acierto por grupo */}
        <Card>
          <Section title={<Titulo icon={<ShieldCheck size={16} aria-hidden />}>{t('autoresolution.top_buckets')}</Titulo>}>
            {topBuckets.length === 0 ? (
              <div className="u-text3-sm">{t('autoresolution.buckets_vacio')}</div>
            ) : (
              <ul className="arp-lista">
                {topBuckets.map((b) => {
                  const pct = b.success_rate == null ? 0 : Math.max(0, Math.min(100, b.success_rate))
                  return (
                    <li key={b.bucket} className="arp-grupo">
                      <div className="arp-grupo__fila">
                        <span className="arp-grupo__nombre">{nombreDeGrupo(b.bucket)}</span>
                        <span className="u-text3-xs">{b.success}/{b.total}</span>
                        <StatusBadge kind={kindDeTasa(b.success_rate)} caps={false}>{b.success_rate != null ? `${b.success_rate} %` : '—'}</StatusBadge>
                      </div>
                      <div className="arp-barra" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={nombreDeGrupo(b.bucket)}>
                        <span className={`arp-barra__relleno arp-barra__relleno--${kindDeTasa(b.success_rate)}`} style={{ '--arp-w': `${pct}%` } as CSSProperties} />
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </Section>
        </Card>

        {/* Estado del proceso */}
        <Card>
          <Section title={<Titulo icon={<Activity size={16} aria-hidden />}>{t('autoresolution.salud_operativa')}</Titulo>}
            actions={<StatusBadge kind={runtimeKind} dot caps={false}>{t(`autoresolution.estado_${['running', 'completed', 'failed', 'never_run'].includes(runtimeStatus) ? runtimeStatus : 'unknown'}`)}</StatusBadge>}>
            <dl className="arp-datos">
              <div><dt className="ds-eyebrow">{t('autoresolution.inicio')}</dt><dd>{runtime?.started_at ? fmtDateTime(runtime.started_at) : '—'}</dd></div>
              <div><dt className="ds-eyebrow">{t('autoresolution.fin')}</dt><dd>{runtime?.completed_at ? fmtDateTime(runtime.completed_at) : '—'}</dd></div>
              <div><dt className="ds-eyebrow">{t('autoresolution.duracion')}</dt><dd>{formatDurationMs(runtime?.duration_ms)}</dd></div>
              <div><dt className="ds-eyebrow">{t('autoresolution.resultado')}</dt><dd>{runtime?.stats
                ? t('autoresolution.resumen_ejecucion', { procesados: runtime.stats.processed ?? 0, autoresueltos: runtime.stats.auto_resolved ?? 0, fallidos: runtime.stats.failed ?? 0 })
                : '—'}</dd></div>
            </dl>
            {runtime?.error && <div className="arp-error" role="alert">{t('autoresolution.error')} {runtime.error}</div>}
          </Section>
        </Card>
      </div>

      {/* Ejecutar ahora */}
      <Card>
        <Section title={<Titulo icon={<Play size={16} aria-hidden />}>{t('autoresolution.acciones_manuales')}</Titulo>}
          subtitle={t('autoresolution.los_jobs_tambien_se_ejecutan_de_forma')}>
          <div className="u-wrap-center-8">
            <Button icon={<Play size={14} />} onClick={() => runJob()} loading={runningJob}>{t('autoresolution.ejecutar_auto_resolucion')}</Button>
            <Button variant="secondary" icon={<Lock size={14} />} onClick={() => runCloseJob()} loading={runningClose}>{t('autoresolution.ejecutar_auto_cierre')}</Button>
          </div>
        </Section>
      </Card>

      {/* Últimas ejecuciones */}
      <Card>
        <Section title={<Titulo icon={<History size={16} aria-hidden />}>{t('autoresolution.historial_de_ejecuciones')}</Titulo>}>
          {jobHistory.length === 0 ? (
            <EmptyState icon={<History size={28} />} title={t('autoresolution.historial_vacio')} description={t('autoresolution.los_jobs_tambien_se_ejecutan_de_forma')} />
          ) : (
            <ul className="arp-lista">
              {jobHistory.map((run, idx) => (
                <li key={idx} className="arp-ejecucion">
                  <StatusBadge kind={run.status === 'completed' ? 'success' : run.status === 'failed' ? 'danger' : 'neutral'} dot caps={false}>
                    {etiquetaCodigo(t, 'autoresolution.run', run.status)}
                  </StatusBadge>
                  <span className="u-text2-xs">{run.started_at ? fmtDateTime(run.started_at) : '—'}</span>
                  <span className="u-text3-xs">{formatDurationMs(run.duration_ms)}</span>
                  <span className={run.stats ? 'arp-ejecucion__res' : run.error ? 'arp-ejecucion__res arp-ejecucion__res--error' : 'arp-ejecucion__res'}>
                    {run.stats
                      ? t('autoresolution.resumen_ejecucion', { procesados: run.stats.processed ?? 0, autoresueltos: run.stats.auto_resolved ?? 0, fallidos: run.stats.failed ?? 0 })
                      : run.error || '—'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </Card>

      {/* Valorar un ticket */}
      <Card>
        <Section title={<Titulo icon={<MessageSquareText size={16} aria-hidden />}>{t('autoresolution.feedback_por_ticket')}</Titulo>}
          subtitle={t('autoresolution.feedback_desc')}>
          <div className="arp-fila">
            <Input label={t('autoresolution.numero_ticket')} value={buscado} onChange={e => setBuscado(e.target.value)} className="arp-fila__campo" />
            <Button onClick={() => buscado.trim() && setFeedbackTicketId(buscado.trim())} disabled={!buscado.trim()}>
              {t('autoresolution.dar_feedback')}
            </Button>
          </div>
        </Section>
      </Card>

      {feedbackTicketId && (
        <FeedbackModal ticketId={feedbackTicketId} onClose={() => setFeedbackTicketId(null)} />
      )}
    </div>
  )
}
