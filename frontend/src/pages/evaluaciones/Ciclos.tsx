/**
 * Ciclos de evaluación: tarjeta, alta y panel de KPIs.
 * Troceado de PerformanceReviewsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { type CSSProperties, useState, useMemo, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { performanceApi } from '../../services/api'
import { Button, KpiCard, Modal, Pulsable, Select, Spinner, useErroresDeCampo, Input } from '../../components/ui'
import { Plus, ChevronRight, ChevronDown, Clock, CheckCircle2, UserPlus, Lock, History, Activity, Bell, AlertTriangle } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import DateInput from '../../components/ui/DateInput'
import { type Cycle, type CycleKpis, NO_PERMISSION_TIP, type OrgKpis, type Review, ScoreBar, STATUS_CFG, TYPE_BY_ID } from './compartido'
import { QuestionsEditor } from './EditorDePreguntas'
import { CampaignsList } from './Campanas360'

// ── CycleCard: tarjeta de un ciclo con sus evaluaciones ────────────────────
export function CycleCard({ cycle, isManager, onActivate, onCloseCycle, onAssign, onCreateCampaign, onOpenDashboard }: {
  cycle: Cycle; isManager: boolean
  onActivate: (id: string) => void; onCloseCycle: (id: string) => void
  onAssign: (cycle: Cycle) => void; onCreateCampaign: (cycle: Cycle) => void; onOpenDashboard: (id: string) => void
}) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const [expanded, setExpanded] = useState(false)
  const { data: reviews = [], isLoading } = useQuery<Review[]>({
    queryKey: ['perf-cycle-reviews', cycle.id],
    queryFn: () => performanceApi.cycleReviews(cycle.id).then(r => r.data),
    enabled: expanded && (cycle.status === 'active' || cycle.status === 'closed'),
  })

  const statusCfg = STATUS_CFG[cycle.status as keyof typeof STATUS_CFG] || STATUS_CFG.draft
  const submittedReviews = reviews.filter(r => r.score_overall != null)
  const avgScore = submittedReviews.length > 0
    ? (submittedReviews.reduce((s, r) => s + (r.score_overall || 0), 0) / submittedReviews.length).toFixed(1)
    : null

  const ChevronIcon = expanded ? ChevronDown : ChevronRight

  return (
    <div className="ds-card perf-box-3">
      <div className="ds-row perf-box-3">
        <Pulsable onClick={() => setExpanded(s => !s)}
          aria-label={expanded ? t('pagina_perf.contraer') : t('pagina_perf.expandir')}
          className="perf-btn-4">
          <ChevronIcon size={16} />
        </Pulsable>
        <div className="u-flex1-min0">
          <div className="performance-reviews-page-e17">{cycle.name}</div>
          <div className="ds-row-wrap perf-box-4">
            <span className={`ds-pill ds-pill--${statusCfg.kind === 'neutral' ? '' : statusCfg.kind}`}>
              {t(statusCfg.label)}
            </span>
            {cycle.start_date && (
              <span className="ds-muted u-xs">
                {fmtDate(cycle.start_date)} – {cycle.end_date ? fmtDate(cycle.end_date) : '?'}
              </span>
            )}
            <span className="ds-muted u-xs">
              {t('pagina_perf.ciclo_resumen', { total: cycle.total_reviews || 0, pendientes: cycle.pending, enviadas: cycle.submitted })}
            </span>
            {avgScore && (
              <span className="perf-label-10">
                {t('pagina_perf.media')}{' '}{avgScore}/5
              </span>
            )}
          </div>
        </div>
        <div className="perf-row-6">
          {cycle.status === 'draft' && (
            <span title={!isManager ? t(NO_PERMISSION_TIP) : undefined} className="perf-row-2">
              <Button size="sm" onClick={() => onActivate(cycle.id)} disabled={!isManager}>
                {t('pagina_perf.activar')}
              </Button>
            </span>
          )}
          {cycle.status === 'active' && (
            <>
              <span title={!isManager ? t(NO_PERMISSION_TIP) : undefined} className="perf-row-2">
                <Button size="sm" onClick={() => onAssign(cycle)} disabled={!isManager}>
                  <UserPlus size={12} />{' '}{t('pagina_perf.asignar')}
                </Button>
              </span>
              <span title={!isManager ? t(NO_PERMISSION_TIP) : undefined} className="perf-row-2">
                <Button size="sm" variant="secondary" onClick={() => onCloseCycle(cycle.id)} disabled={!isManager}>
                  {t('pagina_perf.cerrar_ciclo')}
                </Button>
              </span>
            </>
          )}
        </div>
      </div>

      {expanded && (
        <div className="ds-stack-sm">
          {/* Plantilla de preguntas (siempre visible cuando expandido) */}
          <QuestionsEditor cycleId={cycle.id} cycleStatus={cycle.status} />

          {/* Campañas 360° — solo en ciclos activos o cerrados */}
          {(cycle.status === 'active' || cycle.status === 'closed') && (
            <CampaignsList cycle={cycle} isManager={isManager}
              onCreate={onCreateCampaign}
              onOpenDashboard={onOpenDashboard} />
          )}

          {/* Evaluaciones — solo en ciclos activos/cerrados */}
          {(cycle.status === 'active' || cycle.status === 'closed') && (
            isLoading ? <Spinner /> : reviews.length === 0 ? (
              <div className="ds-card--inset perf-box-14">
                <div className="ds-muted u-sm">
                  {traducir('performancereviews.sin_evaluaciones_aun')} {cycle.status === 'active' && isManager && t('pagina_perf.pulsa_asignar_para_crear_la_primera')}
                  {cycle.status === 'active' && !isManager && t('pagina_perf.rr_hh_asignara_las_evaluaciones_cuando')}
                </div>
              </div>
            ) : (
              <div className="ds-grid-cards perf-box-25">
                {reviews.map(r => {
                  const tipo = TYPE_BY_ID[r.review_type] || TYPE_BY_ID.peer
                  const TypeIcon = tipo.Icon
                  const submitted = r.status === 'submitted'
                  return (
                    <div key={r.id} className="ds-card--inset perf-box-14">
                      <div className="ds-row-between perf-box-26">
                        <div className="performance-reviews-page-e8">
                          <div className="performance-reviews-page-e16">
                            {r.reviewee_name}
                          </div>
                          <div className="ds-muted perf-row-13">
                            <TypeIcon size={11} /> {t(tipo.label)}
                          </div>
                        </div>
                        <span className={`perf-row-14 ${submitted ? 'performa-sx7' : 'performa-sx8'}`}>
                          {submitted
                            ? <><CheckCircle2 size={10} /> {t('pagina_perf.enviado')}</>
                            : <><Clock size={10} /> {t('pagina_perf.pendiente')}</>}
                        </span>
                      </div>
                      {r.score_overall != null && <ScoreBar value={r.score_overall} />}
                      <div className="ds-muted perf-box-27">
                        {traducir('performancereviews.por')} {r.reviewer_name}
                      </div>
                    </div>
                  )
                })}
              </div>
            )
          )}
        </div>
      )}
    </div>
  )
}

// ── NewCycleModal ──────────────────────────────────────────────────────────
export function NewCycleModal({ existingCycles, onClose }: { existingCycles: Cycle[]; onClose: () => void }) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name: '', start_date: '', end_date: '',
    template_mode: 'default',  // 'default' | 'clone' | 'empty'
    clone_from: '',
  })

  const cloneable = useMemo(
    () => (existingCycles || []).filter(c => c.id),
    [existingCycles],
  )

  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: () => {
      const payload = {
        name: form.name,
        start_date: form.start_date || null,
        end_date:   form.end_date   || null,
        seed_default_questions: form.template_mode === 'default',
        clone_questions_from_cycle_id: form.template_mode === 'clone' ? form.clone_from : null,
      }
      return performanceApi.createCycle(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-cycles'] })
      toast.success(t('pagina_perf.ciclo_creado'))
      onClose()
    },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const canCreate = !!form.name.trim() &&
    (form.template_mode !== 'clone' || !!form.clone_from)

  return (
    <Modal open onClose={onClose} title={traducir('performancereviews.nuevo_ciclo_de_evaluacion')} width={520}>
      <div className="ds-stack">
        <div className="ds-field">
          <Input label={t('pagina_perf.nombre')} id={`${idCampo}-1`} value={form.name} onChange={e => { camposB.limpiar('name'); setForm(f => ({ ...f, name: e.target.value })) }} placeholder={traducir('performancereviews.ej_evaluacion_q1_2026')} autoFocus />{msgB('name')}
        </div>
        <div className="performance-reviews-page-e15">
          <div className="ds-field">
            <DateInput label={t('pagina_perf.inicio')} id={`${idCampo}-2`} value={form.start_date}
              onChange={e => { camposB.limpiar('start_date'); setForm(f => ({ ...f, start_date: e.target.value })) }} />{msgB('start_date')}
          </div>
          <div className="ds-field">
            <DateInput label={t('pagina_perf.fin')} id={`${idCampo}-3`} value={form.end_date}
              onChange={e => { camposB.limpiar('end_date'); setForm(f => ({ ...f, end_date: e.target.value })) }} />{msgB('end_date')}
          </div>
        </div>
        <div className="ds-field">
          <label className="ds-field__label">{traducir('performancereviews.plantilla_de_preguntas_2')}</label>
          <div className="ds-row-wrap">
            {[
              { id: 'default', label: t('pagina_perf.por_defecto_5_ratings_3_textos') },
              { id: 'clone',   label: t('pagina_perf.clonar_de_otro_ciclo'), disabled: cloneable.length === 0 },
              { id: 'empty',   label: t('pagina_perf.vacia_la_rellenare_yo') },
            ].map(opt => {
              const active = form.template_mode === opt.id
              return (
                <Pulsable key={opt.id}
                  disabled={opt.disabled}
                  onClick={() => setForm(f => ({ ...f, template_mode: opt.id }))}
                  className={`perf-btn-5 performa-sx4 ${active ? 'performa-sx5' : 'performa-sx6'} ${opt.disabled ? 'performa-sx9' : 'performa-sx10'} performance-reviews-page-e3`} style={{ '--performance-reviews-page-border': `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                  {opt.label}
                </Pulsable>
              )
            })}
          </div>
          {form.template_mode === 'clone' && (
            <div className="perf-box-28">
              <Select suelto placeholder={false} value={form.clone_from}
                onChange={e => { camposB.limpiar('clone_from'); setForm(f => ({ ...f, clone_from: e.target.value })) }}>
                <option value="">{t('pagina_perf.selecciona_ciclo_origen')}</option>
                {cloneable.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>{msgB('clone_from')}
            </div>
          )}
        </div>
        <div className="performance-reviews-page-e12">
          <Button variant="secondary" onClick={onClose}>{t('pagina_perf.cancelar')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !canCreate} loading={isPending}>
            <Plus size={13} />{' '}{t('pagina_perf.crear_ciclo')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── KPIDashboardTab: panel operativo de HR ─────────────────────────────────
export function KPIDashboardTab({ cycles }: { cycles: Cycle[] }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()

  const { data: kpis, isLoading } = useQuery<OrgKpis>({
    queryKey: ['perf-kpis-org'],
    queryFn: () => performanceApi.orgKpis().then(r => r.data),
  })

  const { mutate: runReminders, isPending: running } = useMutation({
    mutationFn: () => performanceApi.runReminders(),
    onSuccess: res => {
      const d = res.data
      toast.success(
        t('pagina_perf.recordatorios_enviados_omitidos', { reminders_sent: d.reminders_sent, reminders_skipped_dedup: d.reminders_skipped_dedup }),
      )
      qc.invalidateQueries({ queryKey: ['perf-kpis-org'] })
    },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_disparar_recordatorios'))),
  })

  if (isLoading || !kpis) return <Spinner />

  return (
    <div className="ds-stack perf-box-2">
      <div className="ds-row-between">
        <div className="ds-eyebrow performance-reviews-page-e13">
          <Activity size={12} />{' '}{t('pagina_perf.panel_operativo')}
        </div>
        <Button size="sm" variant="secondary" icon={<Bell size={13} />} onClick={() => runReminders()} loading={running}>
          {t('pagina_perf.disparar_recordatorios_ahora')}
        </Button>
      </div>

      {/* 16-11-2026: KpiCard del kit (antes una tarjeta propia con la etiqueta encima). */}
      <div className="ds-grid-stats">
        <KpiCard icon={<Activity size={16} />} label={t('pagina_perf.ciclos_activos')} value={kpis.active_cycles} />
        <KpiCard icon={<Lock size={16} />} label={t('pagina_perf.ciclos_cerrados')} value={kpis.closed_cycles} />
        <KpiCard icon={<Clock size={16} />} label={t('pagina_perf.reviews_pendientes')} value={kpis.pending_reviews_active}
          sub={t('pagina_perf.de_en_ciclos_activos', { total_reviews_active: kpis.total_reviews_active })}
          warning={kpis.pending_reviews_active > 0} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('pagina_perf.completion_rate_global')} value={`${kpis.global_completion_rate}%`}
          sub={t('pagina_perf.sobre_todos_los_ciclos_activos')}
          warning={kpis.global_completion_rate < 40} />
        <KpiCard icon={<History size={16} />} label={t('pagina_perf.tiempo_medio_de_envio')}
          value={kpis.avg_days_to_submit_closed != null ? t('pagina_perf.d', { avg_days_to_submit_closed: kpis.avg_days_to_submit_closed }) : '—'}
          sub={t('pagina_perf.en_ciclos_ya_cerrados')} />
      </div>

      {/* Ciclos atascados */}
      {kpis.stalled_cycles?.length > 0 && (
        <div className="ds-card--inset perf-box-14">
          <div className="ds-row perf-box-31">
            <AlertTriangle size={14} />
            {kpis.stalled_cycles.length}{' '}{t('pagina_perf.ciclo_s_atascado_s')}
          </div>
          <div className="ds-stack-sm">
            {kpis.stalled_cycles.map(s => (
              <div key={s.cycle_id} className="ds-row-between performance-reviews-page-e14">
                <div className="performance-reviews-page-e8">
                  <div className="performance-reviews-page-e16">
                    {s.cycle_name}
                  </div>
                  <div className="ds-muted u-xs">
                    {s.completion_rate}{t('pagina_perf.completado')}
                    {s.overdue && t('pagina_perf.vencido')}
                    {s.end_date && t('pagina_perf.cerraba', { end_date: fmtDate(s.end_date) })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Drill-down por ciclo */}
      {(cycles?.filter(c => c.status === 'active').length ?? 0) > 0 && (
        <div className="ds-card--inset perf-box-14">
          <div className="ds-eyebrow perf-box-26">{t('pagina_perf.ciclos_activos_en_detalle')}</div>
          <div className="ds-stack-sm">
            {cycles.filter(c => c.status === 'active').map(c => (
              <CycleKpiRow key={c.id} cycle={c} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function CycleKpiRow({ cycle }: { cycle: Cycle }) {
  const { t } = useAppLang()
  const { data: k, isLoading } = useQuery<CycleKpis>({
    queryKey: ['perf-cycle-kpi', cycle.id],
    queryFn: () => performanceApi.cycleKpis(cycle.id).then(r => r.data),
  })
  if (isLoading || !k) return <Spinner />

  const rate = k.completion_rate
  const color = rate >= 70 ? 'var(--success)' : rate >= 40 ? 'var(--accent)' : 'var(--warning)'

  return (
    <div className="ds-row-between performance-reviews-page-e14">
      <div className="performance-reviews-page-e8">
        <div className="performance-reviews-page-e16">
          {k.cycle_name}
        </div>
        <div className="ds-muted u-xs">
          {t('pagina_perf.enviadas_de', { enviadas: k.submitted, total: k.total_reviews })}
          {k.days_to_close != null && t('pagina_perf.cierra_en_dias', { days_to_close: k.days_to_close })}
          {k.avg_days_to_submit != null && t('pagina_perf.media_d', { avg_days_to_submit: k.avg_days_to_submit })}
        </div>
        {k.top_stalled_reviewers?.length > 0 && (
          <div className="ds-row-wrap perf-box-16">
            {k.top_stalled_reviewers.slice(0, 5).map(s => (
              <span key={s.user_id} className="perf-card-2">
                {s.user_name} · {s.pending}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="perf-box-32">
        <ScoreBar value={rate / 20} max={5} />
        <div className="perf-box-33 performance-reviews-page-e2" style={{ '--performance-reviews-page-color': color } as CSSProperties}>
          {rate}%
        </div>
      </div>
    </div>
  )
}
