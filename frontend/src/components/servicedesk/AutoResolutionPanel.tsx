/**
 * AutoResolutionPanel — AI auto-resolution dashboard for ITSM
 *
 * Backend endpoints:
 *   GET  /sd/auto-resolution/stats                   -> { total_auto_resolved, pct_of_all_tickets, feedback_total_validated, overall_success_rate, per_bucket: [{bucket, total, success, failed, success_rate}] }
 *   POST /sd/auto-resolution/run-job                 -> { processed, auto_resolved, suggested, failed, status, timestamp }
 *   POST /sd/auto-resolution/run-close-job           -> { processed, auto_closed, validated, failed, status, timestamp }
 *   POST /sd/tickets/{id}/auto-resolution/feedback   { success: bool } -> { recorded, ticket_id, success }
 */
import React, { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { autoResolutionApi, ticketsApi } from '../../services/api'
import { Card, Button, Spinner, Modal} from '../ui'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'

type AutoResolutionConfig = {
  threshold_auto?: number
  threshold_suggest?: number
  auto_close_hours_after_resolution?: number
  validation_window_hours?: number
  default_job_limit?: number
}

type AutoResolutionBucket = {
  bucket: string
  total: number
  success: number
  failed: number
  success_rate?: number | null
}

type RuntimeStats = {
  processed?: number
  auto_resolved?: number
  failed?: number
}

type RuntimeInfo = {
  running?: boolean
  status?: string
  started_at?: string | null
  completed_at?: string | null
  duration_ms?: number | null
  stats?: RuntimeStats
  error?: string | null
}

type JobHistoryItem = {
  status?: string
  started_at?: string | null
  duration_ms?: number | null
  stats?: RuntimeStats
  error?: string | null
}

type AutoResolutionStats = {
  total_auto_resolved?: number
  pct_of_all_tickets?: number
  feedback_total_validated?: number
  overall_success_rate?: number
  per_bucket?: AutoResolutionBucket[]
  runtime?: RuntimeInfo | null
  job_history?: JobHistoryItem[]
}

const errMsg = (e: unknown, fallback: string): string => {
  const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail || fallback
}

const card: React.CSSProperties = { padding: '20px 22px' }

const fieldLabel: React.CSSProperties = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
}

interface StatCardProps {
  label: string
  value?: number | string | null
  accent: string
  sub?: React.ReactNode
}

function StatCard({ label, value, accent, sub }: StatCardProps) {
  return (
    <div style={{
      flex: '1 1 140px',
      background: `color-mix(in srgb, ${accent} 8%, var(--surface-3))`,
      border: `1px solid color-mix(in srgb, ${accent} 25%, var(--surface-4))`,
      borderRadius: 'var(--radius-md)',
      padding: '14px 16px',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 'var(--text-2xl-em)', fontWeight: 800, color: accent, lineHeight: 1.1 }}>
        {value ?? '—'}
      </div>
      <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      {sub && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginTop: 6 }}>{sub}</div>
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
      toast.success('Feedback registrado en el bucket de la ticket.')
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
      onClose()
    },
    onError: (e) => toast.error(errMsg(e, 'Error al registrar feedback')),
  })

  return (
    <Modal open title={`Feedback auto-resolución — ${ticketId}`} onClose={onClose} width={460}>
      <div className="u-stack-14">
        <div>
          <div style={fieldLabel}>{t('autoresolution.la_auto_resolucion_fue_correcta')}</div>
          <div className="u-row-10">
            <button
              type="button"
              onClick={() => setSuccess(true)}
              style={{
                flex: 1, padding: '10px 14px', borderRadius: 8,
                border: `1px solid ${success ? 'var(--success)' : 'var(--surface-4)'}`,
                background: success ? 'color-mix(in srgb, var(--success) 12%, transparent)' : 'var(--surface-3)',
                color: success ? 'var(--success)' : 'var(--text-2)',
                cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-base)', fontWeight: 600,
              }}
            >👍 Correcta</button>
            <button
              type="button"
              onClick={() => setSuccess(false)}
              style={{
                flex: 1, padding: '10px 14px', borderRadius: 8,
                border: `1px solid ${!success ? 'var(--danger)' : 'var(--surface-4)'}`,
                background: !success ? 'color-mix(in srgb, var(--danger) 12%, transparent)' : 'var(--surface-3)',
                color: !success ? 'var(--danger)' : 'var(--text-2)',
                cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-base)', fontWeight: 600,
              }}
            >{t('autoresolution.fallo')}</button>
          </div>
        </div>
        <div style={{
          fontSize: 'var(--text-xs)', color: 'var(--text-3)',
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '8px 12px',
        }}>
          {t('autoresolution.tu_feedback_alimenta_el_bucket_category_priority')}
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate()} loading={isPending}>Enviar feedback</Button>
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
        style={{
          flex: '1 1 240px',
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '8px 12px',
          color: 'var(--text-1)', fontSize: 'var(--text-sm)',
          fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
        }}
      />
      <Button onClick={() => id && onOpen(id.trim())} disabled={!id.trim()}>
        Dar feedback
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
  // TODO type: auto-resolution config payload — needs shared type
  const [cfgDraft, setCfgDraft] = useState<AutoResolutionConfig | null>(null)

  const { data: config, isLoading: configLoading } = useQuery<AutoResolutionConfig>({
    queryKey: ['sd-auto-resolution-config'],
    queryFn: () => autoResolutionApi.getConfig().then(r => r.data as AutoResolutionConfig),
  })

  useEffect(() => {
    if (config) {
      setCfgDraft(config)
    }
  }, [config])

  const { data: stats, isLoading: statsLoading } = useQuery<AutoResolutionStats>({
    queryKey: ['sd-auto-resolution-stats'],
    queryFn: () => autoResolutionApi.getStats().then(r => r.data as AutoResolutionStats),
    refetchInterval: 30_000,
  })

  const { mutate: runJob, isPending: runningJob } = useMutation({
    mutationFn: () => autoResolutionApi.runJob({ run_async: true, limit: cfgDraft?.default_job_limit ?? 25 }),
    onSuccess: (res) => {
      const r = res.data || {}
      if (r.status === 'queued') {
        toast.success(`Job encolado (lote ${r.limit ?? 25}). Puedes seguir trabajando mientras procesa.`)
      } else if (r.status === 'already_running') {
        toast.warning('Ya hay un job de auto-resolución en ejecución.')
      } else {
        toast.success(
          `Job: ${r.processed ?? 0} procesados · ${r.auto_resolved ?? 0} auto-resueltos · ${r.suggested ?? 0} sugeridos · ${r.failed ?? 0} fallidos`
        )
      }
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: (e) => toast.error(errMsg(e, 'Error al ejecutar el job')),
  })

  const { mutate: runCloseJob, isPending: runningClose } = useMutation({
    mutationFn: () => autoResolutionApi.runCloseJob(),
    onSuccess: (res) => {
      const r = res.data || {}
      toast.success(
        `Auto-cierre: ${r.auto_closed ?? 0} cerrados · ${r.validated ?? 0} validados · ${r.failed ?? 0} fallidos`
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
      toast.success('Configuración de auto-resolución guardada')
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
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 12 }}>
          {t('autoresolution.configuracion_del_motor_de_auto_resolucion')}
        </div>
        {configLoading || !cfgDraft ? <Spinner /> : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
              <div>
                <div style={fieldLabel}>Umbral auto-resolver</div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={cfgDraft.threshold_auto ?? 0.85}
                  onChange={e => setCfgDraft(prev => ({ ...prev, threshold_auto: Number(e.target.value) }))}
                  style={{ width: '100%' }}
                />
                <div className="u-text2-xs">{Math.round((cfgDraft.threshold_auto ?? 0.85) * 100)}%</div>
              </div>

              <div>
                <div style={fieldLabel}>Umbral sugerencia</div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={cfgDraft.threshold_suggest ?? 0.65}
                  onChange={e => setCfgDraft(prev => ({ ...prev, threshold_suggest: Number(e.target.value) }))}
                  style={{ width: '100%' }}
                />
                <div className="u-text2-xs">{Math.round((cfgDraft.threshold_suggest ?? 0.65) * 100)}%</div>
              </div>

              <div>
                <div style={fieldLabel}>{t('autoresolution.horas_para_auto_cierre')}</div>
                <input
                  type="number"
                  min="1"
                  max="720"
                  value={cfgDraft.auto_close_hours_after_resolution ?? 72}
                  onChange={e => setCfgDraft(prev => ({ ...prev, auto_close_hours_after_resolution: Number(e.target.value) }))}
                  style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)' }}
                />
              </div>

              <div>
                <div style={fieldLabel}>{t('autoresolution.ventana_validacion_horas')}</div>
                <input
                  type="number"
                  min="1"
                  max="720"
                  value={cfgDraft.validation_window_hours ?? 48}
                  onChange={e => setCfgDraft(prev => ({ ...prev, validation_window_hours: Number(e.target.value) }))}
                  style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)' }}
                />
              </div>

              <div>
                <div style={fieldLabel}>{t('autoresolution.lote_por_ejecucion_manual')}</div>
                <input
                  type="number"
                  min="1"
                  max="500"
                  value={cfgDraft.default_job_limit ?? 25}
                  onChange={e => setCfgDraft(prev => ({ ...prev, default_job_limit: Number(e.target.value) }))}
                  style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)' }}
                />
              </div>
            </div>

            <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
              <Button onClick={() => saveConfig()} loading={savingConfig}>{t('autoresolution.guardar_configuracion')}</Button>
            </div>
          </>
        )}
      </Card>

      {/* Stats */}
      <Card style={card}>
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>
          {t('autoresolution.estadisticas_de_auto_resolucion')}
        </div>
        {statsLoading ? <Spinner /> : (
          <>
            <div className="u-wrap-10">
              <StatCard
                label="Auto-resueltos (total)"
                value={stats?.total_auto_resolved}
                accent="var(--success)"
                sub={stats?.pct_of_all_tickets != null ? `${stats.pct_of_all_tickets}% de todos los tickets` : undefined}
              />
              <StatCard
                label="Feedback validado"
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
              <div style={{ marginTop: 18 }}>
                <div style={fieldLabel}>{t('autoresolution.top_buckets_categoria_prioridad')}</div>
                <div className="u-stack-6">
                  {topBuckets.map((b) => {
                    const rate = b.success_rate
                    const color = rate == null ? 'var(--text-3)'
                      : rate >= 85 ? 'var(--success)'
                      : rate >= 60 ? 'var(--warning)' : 'var(--danger)'
                    const pct = rate == null ? 0 : Math.max(0, Math.min(100, rate))
                    return (
                      <div key={b.bucket} style={{
                        background: 'var(--surface-3)',
                        border: '1px solid var(--surface-4)',
                        borderRadius: 8, padding: '8px 12px',
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, fontSize: 'var(--text-sm)' }}>
                          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{b.bucket}</span>
                          <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                            <span className="u-text3-xs">
                              {b.success}/{b.total}
                            </span>
                            <span style={{
                              fontSize: 'var(--text-xs)', fontWeight: 700, color,
                              background: `color-mix(in srgb, ${color} 15%, transparent)`,
                              border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
                              borderRadius: 'var(--radius-sm)', padding: '2px 8px',
                            }}>{rate != null ? `${rate}%` : '—'}</span>
                          </span>
                        </div>
                        <div style={{ marginTop: 6, height: 4, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ width: `${pct}%`, height: '100%', background: color, transition: 'width .4s' }} />
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
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
          🩺 Salud operativa
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: runtimeColor, display: 'inline-block' }} />
          <span style={{ fontSize: 'var(--text-sm)', color: runtimeColor, fontWeight: 700 }}>{runtimeLabel}</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={fieldLabel}>Inicio</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)' }}>{formatDateTime(runtime?.started_at)}</div>
          </div>
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={fieldLabel}>Fin</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)' }}>{formatDateTime(runtime?.completed_at)}</div>
          </div>
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={fieldLabel}>{t('autoresolution.duracion')}</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)' }}>{formatDurationMs(runtime?.duration_ms)}</div>
          </div>
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={fieldLabel}>Resultado</div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)' }}>
              {runtime?.stats
                ? `${runtime.stats.processed ?? 0} procesados · ${runtime.stats.auto_resolved ?? 0} auto-resueltos · ${runtime.stats.failed ?? 0} fallidos`
                : '—'}
            </div>
          </div>
        </div>
        {runtime?.error && (
          <div style={{ marginTop: 10, fontSize: 'var(--text-xs)', color: 'var(--danger)' }}>
            Error: {runtime.error}
          </div>
        )}
      </Card>

      {/* Job history timeline */}
      {jobHistory.length > 0 && (
        <Card style={card}>
          <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 10 }}>
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
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '8px 12px',
                    borderRadius: 8,
                    background: 'var(--surface-3)',
                    border: '1px solid var(--surface-4)',
                    fontSize: 'var(--text-xs)',
                  }}
                >
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: runColor, flexShrink: 0 }} />
                  <span style={{ fontWeight: 700, color: runColor, minWidth: 80 }}>{runLabel}</span>
                  <span style={{ color: 'var(--text-3)', minWidth: 130 }}>{formatDateTime(run.started_at)}</span>
                  <span style={{ color: 'var(--text-2)', minWidth: 70 }}>{formatDurationMs(run.duration_ms)}</span>
                  {run.stats
                    ? <span style={{ color: 'var(--text-2)', flex: 1 }}>{processed} procesados · {autoResolved} auto-resueltos · {failed} fallidos</span>
                    : run.error
                      ? <span style={{ color: 'var(--danger)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{run.error}</span>
                      : <span style={{ color: 'var(--text-3)', flex: 1 }}>—</span>
                  }
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Manual job triggers */}
      <Card style={card}>
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
          ⚡ Acciones manuales
        </div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', marginBottom: 14 }}>
          {t('autoresolution.los_jobs_tambien_se_ejecutan_de_forma')}
        </div>
        <div className="u-wrap-10">
          <Button onClick={() => runJob()} loading={runningJob}>
            {t('autoresolution.ejecutar_auto_resolucion')}
          </Button>
          <Button onClick={() => runCloseJob()} loading={runningClose} variant="secondary">
            🔒 Ejecutar auto-cierre
          </Button>
        </div>
      </Card>

      {/* Feedback */}
      <Card style={card}>
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
          {t('autoresolution.feedback_por_ticket')}
        </div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', marginBottom: 14 }}>
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
