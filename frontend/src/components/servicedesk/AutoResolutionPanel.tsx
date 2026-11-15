/**
 * AutoResolutionPanel — AI auto-resolution dashboard for ITSM
 *
 * Backend endpoints:
 *   GET  /sd/auto-resolution/stats                   -> { total_auto_resolved, pct_of_all_tickets, feedback_total_validated, overall_success_rate, per_bucket: [{bucket, total, success, failed, success_rate}] }
 *   POST /sd/auto-resolution/run-job                 -> { processed, auto_resolved, suggested, failed, status, timestamp }
 *   POST /sd/auto-resolution/run-close-job           -> { processed, auto_closed, validated, failed, status, timestamp }
 *   POST /sd/tickets/{id}/auto-resolution/feedback   { success: bool } -> { recorded, ticket_id, success }
 */
import React, { type CSSProperties, useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { autoResolutionApi, ticketsApi } from '../../services/api'
import type { ConfigDeAutoResolucion, EstadisticasDeAutoResolucion } from '../../services/api/tipos-analitica'
import { Card, Button, Spinner, Modal} from '../ui'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import './AutoResolutionPanel.css'

type AutoResolutionConfig = Partial<ConfigDeAutoResolucion>
type AutoResolutionStats = EstadisticasDeAutoResolucion

const errMsg = (e: unknown, fallback: string): string => {
  const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail || fallback
}

const card: React.CSSProperties = { padding: '20px 22px' }


interface StatCardProps {
  label: string
  value?: number | string | null
  accent: string
  sub?: React.ReactNode
}

function StatCard({ label, value, accent, sub }: StatCardProps) {
  return (
    <div className="aurepa-box-21 autoreso-sx1 auto-resolution-panel-e1" style={{ '--auto-resolution-panel-background': `color-mix(in srgb, ${accent} 8%, var(--surface-3))`, '--auto-resolution-panel-border': `1px solid color-mix(in srgb, ${accent} 25%, var(--surface-4))` } as CSSProperties}>
      <div className="aurepa-txt-3 auto-resolution-panel-e2" style={{ '--auto-resolution-panel-color': accent } as CSSProperties}>
        {value ?? '—'}
      </div>
      <div className="aurepa-box-1">
        {label}
      </div>
      {sub && (
        <div className="aurepa-box-2">{sub}</div>
      )}
    </div>
  )
}

function FeedbackModal({ ticketId, onClose }: { ticketId: string | number; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [success, setSuccess] = useState<boolean>(true)

  const { mutate, isPending } = useMutation({
    mutationFn: () => ticketsApi.autoResolutionFeedback(ticketId, { success }),
    onSuccess: () => {
      toast.success(t('autoresolution.feedback_registrado_en_el_bucket_de_la'))
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
      onClose()
    },
    onError: (e) => toast.error(errMsg(e, 'Error al registrar feedback')),
  })

  return (
    <Modal open title={`Feedback auto-resolución — ${ticketId}`} onClose={onClose} width={460}>
      <div className="u-stack-14">
        <div>
          <div className="aurepa-fieldlabel">{t('autoresolution.la_auto_resolucion_fue_correcta')}</div>
          <div className="u-row-10">
            <button className={`aurepa-box-22 autoreso-sx2 auto-resolution-panel-e3 ${success ? 'auto-resolution-panel-m4' : 'auto-resolution-panel-m5'}`}
              type="button"
              onClick={() => setSuccess(true)}
              style={{ '--auto-resolution-panel-border': `1px solid ${success ? 'var(--success)' : 'var(--surface-4)'}` } as CSSProperties}
            >{t('autoresolution.correcta')}</button>
            <button className={`aurepa-box-22 autoreso-sx2 auto-resolution-panel-e3 ${!success ? 'auto-resolution-panel-m6' : 'auto-resolution-panel-m5'}`}
              type="button"
              onClick={() => setSuccess(false)}
              style={{ '--auto-resolution-panel-border': `1px solid ${!success ? 'var(--danger)' : 'var(--surface-4)'}` } as CSSProperties}
            >{t('autoresolution.fallo')}</button>
          </div>
        </div>
        <div className="aurepa-box-3">
          {t('autoresolution.tu_feedback_alimenta_el_bucket_category_priority')}
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} loading={isPending}>{t('autoresolution.enviar_feedback')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function FeedbackLookup({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useAppLang()
  const [id, setId] = useState<string>('')
  return (
    <div className="u-row-center-8">
      <input aria-label={t('autoresolution.id_o_numero_del_ticket_tsk_uuid')}
        value={id}
        onChange={e => setId(e.target.value)}
        placeholder={t('autoresolution.id_o_numero_del_ticket_tsk_uuid')}
        className="aurepa-box-4"
      />
      <Button onClick={() => id && onOpen(id.trim())} disabled={!id.trim()}>
        {t('autoresolution.dar_feedback')}
      </Button>
    </div>
  )
}

function formatDurationMs(ms: number | null | undefined): string {
  if (!Number.isFinite(ms) || ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  const sec = Math.round(ms / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  return `${min}m ${rem}s`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(localeActivo())
}

export default function AutoResolutionPanel() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [feedbackTicketId, setFeedbackTicketId] = useState<string | number | null>(null)
  const [cfgDraft, setCfgDraft] = useState<AutoResolutionConfig | null>(null)

  const { data: config, isLoading: configLoading } = useQuery<AutoResolutionConfig>({
    queryKey: ['sd-auto-resolution-config'],
    queryFn: () => autoResolutionApi.getConfig().then(r => r.data),
  })

  useEffect(() => {
    if (config) {
      setCfgDraft(config)
    }
  }, [config])

  const { data: stats, isLoading: statsLoading } = useQuery<AutoResolutionStats>({
    queryKey: ['sd-auto-resolution-stats'],
    queryFn: () => autoResolutionApi.getStats().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { mutate: runJob, isPending: runningJob } = useMutation({
    mutationFn: () => autoResolutionApi.runJob({ run_async: true, limit: cfgDraft?.default_job_limit ?? 25 }),
    onSuccess: (res) => {
      const r = res.data
      if (r.status === 'queued') {
        toast.success(t('autoresolution.job_encolado_lote_limit_puedes_seguir_trabajando', { limit: r.limit }))
      } else if (r.status === 'already_running') {
        toast.warning(t('autoresolution.ya_hay_un_job_de_auto_resolucion'))
      } else {
        toast.success(
          t('autoresolution.job_processed_procesados_auto_resolved_auto_resueltos', { processed: r.processed ?? 0, auto_resolved: r.auto_resolved ?? 0, suggested: r.suggested ?? 0, failed: r.failed ?? 0 })
        )
      }
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: (e) => toast.error(errMsg(e, 'Error al ejecutar el job')),
  })

  const { mutate: runCloseJob, isPending: runningClose } = useMutation({
    mutationFn: () => autoResolutionApi.runCloseJob(),
    onSuccess: (res) => {
      const r = res.data
      toast.success(
        t('autoresolution.auto_cierre_auto_closed_cerrados_validated_validados', { auto_closed: r.auto_closed ?? 0, validated: r.validated ?? 0, failed: r.failed ?? 0 })
      )
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: (e) => toast.error(errMsg(e, 'Error al ejecutar el job de cierre')),
  })

  const { mutate: saveConfig, isPending: savingConfig } = useMutation({
    mutationFn: () => autoResolutionApi.patchConfig({
      threshold_auto: Number(cfgDraft?.threshold_auto ?? 0.85),
      threshold_suggest: Number(cfgDraft?.threshold_suggest ?? 0.65),
      auto_close_hours_after_resolution: Number(cfgDraft?.auto_close_hours_after_resolution ?? 72),
      validation_window_hours: Number(cfgDraft?.validation_window_hours ?? 48),
      default_job_limit: Number(cfgDraft?.default_job_limit ?? 25),
    }),
    onSuccess: () => {
      toast.success(t('autoresolution.configuracion_de_auto_resolucion_guardada'))
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-config'] })
    },
    onError: (e) => toast.error(errMsg(e, 'Error al guardar configuración')),
  })

  const successRate = stats?.overall_success_rate
  const successColor = successRate == null ? 'var(--text-3)'
    : successRate >= 85 ? 'var(--success)'
    : successRate >= 60 ? 'var(--warning)' : 'var(--danger)'

  const buckets = stats?.per_bucket ?? []
  const topBuckets = buckets.slice(0, 6)
  const runtime = stats?.runtime || null
  const jobHistory = stats?.job_history ?? []
  const runtimeStatus = runtime?.running ? 'running' : runtime?.status || 'never_run'
  const runtimeLabel = runtimeStatus === 'running'
    ? 'En ejecución'
    : runtimeStatus === 'completed'
      ? 'Último job completado'
      : runtimeStatus === 'failed'
        ? 'Último job fallido'
        : runtimeStatus === 'never_run'
          ? 'Sin ejecuciones aún'
          : 'Estado desconocido'
  const runtimeColor = runtimeStatus === 'running'
    ? 'var(--info)'
    : runtimeStatus === 'completed'
      ? 'var(--success)'
      : runtimeStatus === 'failed'
        ? 'var(--danger)'
        : 'var(--text-3)'

  return (
    <div className="u-stack-16">
      {/* Config */}
      <Card style={card}>
        <div className="aurepa-box-5">
          {t('autoresolution.configuracion_del_motor_de_auto_resolucion')}
        </div>
        {configLoading || !cfgDraft ? <Spinner /> : (
          <>
            <div className="aurepa-grid-1">
              <div>
                <div className="aurepa-fieldlabel">{t('autoresolution.umbral_auto_resolver')}</div>
                <input
                  aria-label={t('autoresolution.umbral_auto_resolver')}
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={cfgDraft.threshold_auto ?? 0.85}
                  onChange={e => setCfgDraft(prev => ({ ...prev, threshold_auto: Number(e.target.value) }))}
                  className="aurepa-box-6"
                />
                <div className="u-text2-xs">{Math.round((cfgDraft.threshold_auto ?? 0.85) * 100)}%</div>
              </div>

              <div>
                <div className="aurepa-fieldlabel">{t('autoresolution.umbral_sugerencia')}</div>
                <input
                  aria-label={t('autoresolution.umbral_sugerencia')}
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={cfgDraft.threshold_suggest ?? 0.65}
                  onChange={e => setCfgDraft(prev => ({ ...prev, threshold_suggest: Number(e.target.value) }))}
                  className="aurepa-box-6"
                />
                <div className="u-text2-xs">{Math.round((cfgDraft.threshold_suggest ?? 0.65) * 100)}%</div>
              </div>

              <div>
                <div className="aurepa-fieldlabel">{t('autoresolution.horas_para_auto_cierre')}</div>
                <input
                  aria-label={t('autoresolution.horas_para_auto_cierre')}
                  type="number"
                  min="1"
                  max="720"
                  value={cfgDraft.auto_close_hours_after_resolution ?? 72}
                  onChange={e => setCfgDraft(prev => ({ ...prev, auto_close_hours_after_resolution: Number(e.target.value) }))}
                  className="aurepa-box-7"
                />
              </div>

              <div>
                <div className="aurepa-fieldlabel">{t('autoresolution.ventana_validacion_horas')}</div>
                <input
                  aria-label={t('autoresolution.ventana_validacion_horas')}
                  type="number"
                  min="1"
                  max="720"
                  value={cfgDraft.validation_window_hours ?? 48}
                  onChange={e => setCfgDraft(prev => ({ ...prev, validation_window_hours: Number(e.target.value) }))}
                  className="aurepa-box-7"
                />
              </div>

              <div>
                <div className="aurepa-fieldlabel">{t('autoresolution.lote_por_ejecucion_manual')}</div>
                <input
                  aria-label={t('autoresolution.lote_por_ejecucion_manual')}
                  type="number"
                  min="1"
                  max="500"
                  value={cfgDraft.default_job_limit ?? 25}
                  onChange={e => setCfgDraft(prev => ({ ...prev, default_job_limit: Number(e.target.value) }))}
                  className="aurepa-box-7"
                />
              </div>
            </div>

            <div className="aurepa-row-1">
              <Button onClick={() => saveConfig()} loading={savingConfig}>{t('autoresolution.guardar_configuracion')}</Button>
            </div>
          </>
        )}
      </Card>

      {/* Stats */}
      <Card style={card}>
        <div className="aurepa-box-8">
          {t('autoresolution.estadisticas_de_auto_resolucion')}
        </div>
        {statsLoading ? <Spinner /> : (
          <>
            <div className="u-wrap-10">
              <StatCard
                label={t('autoresolution.auto_resueltos_total')}
                value={stats?.total_auto_resolved}
                accent="var(--success)"
                sub={stats?.pct_of_all_tickets != null ? `${stats.pct_of_all_tickets}% de todos los tickets` : undefined}
              />
              <StatCard
                label={t('autoresolution.feedback_validado')}
                value={stats?.feedback_total_validated}
                accent="var(--accent)"
                sub="Tickets con feedback registrado"
              />
              <StatCard
                label={t('autoresolution.tasa_de_exito_global')}
                value={successRate != null ? `${successRate}%` : '—'}
                accent={successColor}
                sub={successRate == null ? 'Sin datos suficientes' : (
                  successRate >= 85 ? 'Excelente' : successRate >= 60 ? 'Aceptable' : 'Necesita ajuste'
                )}
              />
              <StatCard
                label={t('autoresolution.buckets_con_datos')}
                value={buckets.length || 0}
                accent="var(--purple)"
              />
            </div>

            {topBuckets.length > 0 && (
              <div className="aurepa-sp-1">
                <div className="aurepa-fieldlabel">{t('autoresolution.top_buckets_categoria_prioridad')}</div>
                <div className="u-stack-6">
                  {topBuckets.map((b) => {
                    const rate = b.success_rate
                    const color = rate == null ? 'var(--text-3)'
                      : rate >= 85 ? 'var(--success)'
                      : rate >= 60 ? 'var(--warning)' : 'var(--danger)'
                    const pct = rate == null ? 0 : Math.max(0, Math.min(100, rate))
                    return (
                      <div key={b.bucket} className="aurepa-box-9">
                        <div className="aurepa-row-2">
                          <span className="aurepa-txt-1">{b.bucket}</span>
                          <span className="aurepa-row-3">
                            <span className="u-text3-xs">
                              {b.success}/{b.total}
                            </span>
                            <span className="aurepa-box-23 auto-resolution-panel-e7" style={{ '--auto-resolution-panel-color': color, '--auto-resolution-panel-background': `color-mix(in srgb, ${color} 15%, transparent)`, '--auto-resolution-panel-border': `1px solid color-mix(in srgb, ${color} 30%, transparent)` } as CSSProperties}>{rate != null ? `${rate}%` : '—'}</span>
                          </span>
                        </div>
                        <div className="aurepa-box-10">
                          <div className="aurepa-box-24 auto-resolution-panel-e8" style={{ '--auto-resolution-panel-width': `${pct}%`, '--auto-resolution-panel-background': color } as CSSProperties} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Runtime health */}
      <Card style={card}>
        <div className="aurepa-box-11">
          {t('autoresolution.salud_operativa')}
        </div>
        <div className="aurepa-row-4">
          <span className="aurepa-box-25 auto-resolution-panel-e9" style={{ '--auto-resolution-panel-background': runtimeColor } as CSSProperties} />
          <span className="aurepa-txt-4 auto-resolution-panel-e2" style={{ '--auto-resolution-panel-color': runtimeColor } as CSSProperties}>{runtimeLabel}</span>
        </div>
        <div className="aurepa-grid-2">
          <div className="aurepa-box-12">
            <div className="aurepa-fieldlabel">{t('bpm.inicio')}</div>
            <div className="aurepa-txt-2">{formatDateTime(runtime?.started_at)}</div>
          </div>
          <div className="aurepa-box-12">
            <div className="aurepa-fieldlabel">{t('absences.end')}</div>
            <div className="aurepa-txt-2">{formatDateTime(runtime?.completed_at)}</div>
          </div>
          <div className="aurepa-box-12">
            <div className="aurepa-fieldlabel">{t('autoresolution.duracion')}</div>
            <div className="aurepa-txt-2">{formatDurationMs(runtime?.duration_ms)}</div>
          </div>
          <div className="aurepa-box-12">
            <div className="aurepa-fieldlabel">{t('nexusagent.resultado')}</div>
            <div className="aurepa-txt-2">
              {runtime?.stats
                ? `${runtime.stats.processed ?? 0} procesados · ${runtime.stats.auto_resolved ?? 0} auto-resueltos · ${runtime.stats.failed ?? 0} fallidos`
                : '—'}
            </div>
          </div>
        </div>
        {runtime?.error && (
          <div className="aurepa-box-13">
            {t('autoresolution.error')} {runtime.error}
          </div>
        )}
      </Card>

      {/* Job history timeline */}
      {jobHistory.length > 0 && (
        <Card style={card}>
          <div className="aurepa-box-14">
            {t('autoresolution.historial_de_ejecuciones')}
          </div>
          <div className="u-stack-6">
            {jobHistory.map((run, idx) => {
              const runColor = run.status === 'completed' ? 'var(--success)'
                : run.status === 'failed' ? 'var(--danger)' : 'var(--text-3)'
              const runLabel = run.status === 'completed' ? 'Completado'
                : run.status === 'failed' ? 'Fallido' : run.status
              const processed = run.stats?.processed ?? 0
              const autoResolved = run.stats?.auto_resolved ?? 0
              const failed = run.stats?.failed ?? 0
              return (
                <div
                  key={idx}
                  className="aurepa-row-5"
                >
                  <span className="aurepa-box-26 auto-resolution-panel-e9" style={{ '--auto-resolution-panel-background': runColor } as CSSProperties} />
                  <span className="aurepa-box-27 auto-resolution-panel-e2" style={{ '--auto-resolution-panel-color': runColor } as CSSProperties}>{runLabel}</span>
                  <span className="aurepa-box-15">{formatDateTime(run.started_at)}</span>
                  <span className="aurepa-box-16">{formatDurationMs(run.duration_ms)}</span>
                  {run.stats
                    ? <span className="aurepa-box-17">{t('autoresolution.resumen_ejecucion', { procesados: processed, autoresueltos: autoResolved, fallidos: failed })}</span>
                    : run.error
                      ? <span className="aurepa-box-18">{run.error}</span>
                      : <span className="aurepa-box-19">—</span>
                  }
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Manual job triggers */}
      <Card style={card}>
        <div className="aurepa-box-11">
          {t('autoresolution.acciones_manuales')}
        </div>
        <div className="aurepa-box-20">
          {t('autoresolution.los_jobs_tambien_se_ejecutan_de_forma')}
        </div>
        <div className="u-wrap-10">
          <Button onClick={() => runJob()} loading={runningJob}>
            {t('autoresolution.ejecutar_auto_resolucion')}
          </Button>
          <Button onClick={() => runCloseJob()} loading={runningClose} variant="secondary">
            {t('autoresolution.ejecutar_auto_cierre')}
          </Button>
        </div>
      </Card>

      {/* Feedback */}
      <Card style={card}>
        <div className="aurepa-box-11">
          {t('autoresolution.feedback_por_ticket')}
        </div>
        <div className="aurepa-box-20">
          {t('autoresolution.registra_si_la_resolucion_automatica_fue_correcta')}
        </div>
        <FeedbackLookup onOpen={(id) => setFeedbackTicketId(id)} />
      </Card>

      {feedbackTicketId && (
        <FeedbackModal ticketId={feedbackTicketId} onClose={() => setFeedbackTicketId(null)} />
      )}
    </div>
  )
}
