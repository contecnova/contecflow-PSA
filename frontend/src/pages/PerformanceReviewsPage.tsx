/**
 * PerformanceReviewsPage — Evaluaciones de rendimiento 360°
 *
 * Flujo completo:
 *   1) HR/Admin crea un ciclo (Q1 2025, Annual…) → status `draft`
 *      ↳ El ciclo nace con una plantilla de preguntas por defecto (5 ratings + 3 textos)
 *      ↳ HR/Admin puede personalizar la plantilla mientras el ciclo siga en borrador
 *   2) HR/Admin activa el ciclo                  → status `active`
 *   3) HR/Admin asigna evaluaciones (quién evalúa a quién)
 *      ↳ Al elegir un tipo (manager/par/upward) la UI restringe el evaluador
 *        al pool elegible según organigrama (manager_id) y equipo/departamento.
 *      ↳ Si un tipo no aplica para esa persona se deshabilita con explicación.
 *   4) Cada evaluador rellena su evaluación según las preguntas de la plantilla
 *   5) Evaluador envía → status `submitted`
 *   6) HR/Admin cierra el ciclo                  → status `closed` (read-only)
 */
import { useAppLang } from '../i18n/AppLangContext'
import type { CSSProperties } from 'react'
import { useState, useEffect, useMemo, useId } from 'react'
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { performanceApi, usersApi } from '../services/api'
import type { Campana360, CicloDeEvaluacion, EvaluacionDeDesempeno, EvaluadoresElegibles, Historico360, KpisDeCiclo, KpisDeDesempeno, PanelDeCampana360, PlanDeDesarrollo, PreguntaDeEvaluacion, RespuestasDeEvaluacion } from '../services/api/tipos-rendimiento'
import { Button, Checkbox, KpiCard, Modal, Pulsable, Select, Spinner, EmptyState, Page, Tabs, useErroresDeCampo } from '../components/ui'
import {
  Star, Plus, ChevronRight, ChevronDown, Clock, CheckCircle2,
  User, Users as UsersIcon, Crown, ArrowUp, UserPlus, Save, Send,
  Pencil, Trash2, AlertCircle, ListChecks, Target, BarChart3,
  Lock, X, TrendingUp, History,
  Activity, Bell, AlertTriangle, Map as MapIcon, Flag, FileDown,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { confirmar } from '../context/ConfirmContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import DateInput from '../components/ui/DateInput'
import { SELECTOR_LIST_SIZE } from '../constants/pagination'
import './PerformanceReviewsPage.css'

const NO_PERMISSION_TIP = 'pagina_perf.solo_admin_rr_hh'

// ── Formas de la API: services/api/tipos-rendimiento.ts ────────────────────
type Cycle = CicloDeEvaluacion
type Review = EvaluacionDeDesempeno
type Question = PreguntaDeEvaluacion
type AnswerMap = RespuestasDeEvaluacion
/** Cuerpo de `ReviewQuestionIn` / `ReviewQuestionUpdate`. */
type QuestionPayload = Partial<Pick<Question, 'key' | 'label' | 'hint' | 'kind' | 'required' | 'scale_min' | 'scale_max'>>
type EligiblePool = EvaluadoresElegibles
type EligibleUser = EvaluadoresElegibles['users'][number]
type Campaign = Campana360
type CampaignDashboard = PanelDeCampana360
type History360 = Historico360
type HistoryPoint = Historico360['series'][number]
type OrgKpis = KpisDeDesempeno
type CycleKpis = KpisDeCiclo
type DevPlan = PlanDeDesarrollo

interface HistoryQuestion {
  key: string
  label: string
  max: number
}

// ── Estilos compartidos ────────────────────────────────────────────────────
// Se extraen aquí los patrones inline más repetidos para reducir ruido en JSX
// y unificar el look. NO cambian el comportamiento visible.

// Genera estilo de chip toggle activo/inactivo (botones de selección de tipo,
// pares, upward, plantilla, etc.). El tamaño se pasa explícitamente para no
// alterar la apariencia.
// ── Catálogos ──────────────────────────────────────────────────────────────
const STATUS_CFG = {
  draft:  { kind: 'neutral', label: 'pagina_perf.borrador' },
  active: { kind: 'accent',  label: 'pagina_perf.activo' },
  closed: { kind: 'success', label: 'pagina_perf.cerrado' },
}

const REVIEW_TYPES = [
  { id: 'self',    Icon: User,      label: 'pagina_perf.autoevaluacion', help: 'pagina_perf.el_propio_empleado_se_evalua' },
  { id: 'peer',    Icon: UsersIcon, label: 'pagina_perf.par',            help: 'pagina_perf.companeros_del_mismo_equipo_o_departamento' },
  { id: 'manager', Icon: Crown,     label: 'pagina_perf.manager',        help: 'pagina_perf.el_responsable_directo_segun_organigrama' },
  { id: 'upward',  Icon: ArrowUp,   label: 'pagina_perf.upward',         help: 'pagina_perf.reportes_directos_evaluan_a_su_responsable' },
]
const TYPE_BY_ID = Object.fromEntries(REVIEW_TYPES.map(t => [t.id, t]))

const QUESTION_KINDS = [
  { id: 'rating_5',     label: 'pagina_perf.puntuacion_1_5' },
  { id: 'rating_10',    label: 'pagina_perf.puntuacion_1_10' },
  { id: 'scale_likert', label: 'pagina_perf.likert_1_5' },
  { id: 'yes_no',       label: 'pagina_perf.si_no' },
  { id: 'text_short',   label: 'pagina_perf.texto_corto' },
  { id: 'text_long',    label: 'pagina_perf.texto_largo' },
]
const KIND_LABEL = Object.fromEntries(QUESTION_KINDS.map(k => [k.id, k.label]))

const isRatingKind = (k: string) => k === 'rating_5' || k === 'rating_10' || k === 'scale_likert'
const ratingMax = (q: Question) => q.scale_max ?? (q.kind === 'rating_10' ? 10 : 5)
const ratingMin = (q: Question) => q.scale_min ?? 1

// ── ScoreBar ────────────────────────────────────────────────────────────────
function ScoreBar({ value, max = 5 }: { value: number | null | undefined; max?: number }) {
  const pct = value ? (value / max) * 100 : 0
  const color = pct >= 80 ? 'var(--success)'
              : pct >= 60 ? 'var(--accent)'
              : pct >= 40 ? 'var(--warning)'
              : 'var(--danger)'
  return (
    <div className="u-row-center-8">
      <div className="perf-card">
        <div className="perf-box performance-reviews-page-e1" style={{ '--performance-reviews-page-width': `${pct}%`, '--performance-reviews-page-background': color } as CSSProperties} />
      </div>
      <span className="perf-label performance-reviews-page-e2" style={{ '--performance-reviews-page-color': color } as CSSProperties}>{value ? Number(value).toFixed(1) : '—'}</span>
    </div>
  )
}

// ── ReviewForm: rellenar una evaluación dinámica según preguntas del ciclo ─
function ReviewForm({ review, onClose }: { review: Review; onClose: () => void }) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()

  const { data: questions = [], isLoading: loadingQs } = useQuery<Question[]>({
    queryKey: ['perf-cycle-questions', review.cycle_id],
    queryFn: () => performanceApi.listQuestions(review.cycle_id).then(r => r.data),
  })

  const [answers, setAnswers] = useState<AnswerMap>({})
  // Hidratamos respuestas con lo que venga del review (answers + legacy).
  // Solo re-hidratamos cuando cambia la review seleccionada (review.id):
  // depender de review.answers haría que cualquier re-render del padre con
  // una nueva referencia del objeto pisara las ediciones locales del usuario.
  useEffect(() => {
    setAnswers(review.answers || {})
    // eslint-disable-next-line react-hooks/exhaustive-deps -- omisión deliberada, ver arriba
  }, [review.id])

  const cleanAnswers = () => {
    const out: AnswerMap = {}
    for (const [k, v] of Object.entries(answers)) {
      out[k] = v === '' ? null : v
    }
    return out
  }

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: () => performanceApi.updateReview(review.id, { answers: cleanAnswers() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-my-reviews'] })
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', review.cycle_id] })
      toast.success(t('pagina_perf.borrador_guardado'))
    },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_guardar'))),
  })
  const { mutate: submit, isPending: submitting } = useMutation({
    mutationFn: async () => {
      // Encadenado: guarda primero los cambios, luego envía
      await performanceApi.updateReview(review.id, { answers: cleanAnswers() })
      return performanceApi.submitReview(review.id)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-my-reviews'] })
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', review.cycle_id] })
      toast.success(t('pagina_perf.evaluacion_enviada'))
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_enviar'))),
  })

  const typeCfg = TYPE_BY_ID[review.review_type] || TYPE_BY_ID.peer
  const TypeIcon = typeCfg.Icon
  const ratingQs = questions.filter(q => isRatingKind(q.kind))
  const otherQs  = questions.filter(q => !isRatingKind(q.kind))
  const filledRatings = ratingQs.filter(q => answers[q.key] != null && answers[q.key] !== '').length
  const missingRequired = questions.filter(q => q.required && (answers[q.key] == null || answers[q.key] === ''))

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <TypeIcon size={16} />{' '}{t('pagina_perf.evaluar_a')}{' '}{review.reviewee_name}
      </span>}
      subtitle={t('pagina_perf.de_puntuaciones_rellenas', { label: t(typeCfg.label), filledRatings, v3: ratingQs.length || '—' })}
      width={620}>
      {loadingQs ? <Spinner /> : (
        <div className="ds-stack perf-box-2">
          {/* Ratings agrupadas */}
          {ratingQs.length > 0 && (
            <div className="ds-card--inset perf-stack">
              <div className="ds-eyebrow">{t('pagina_perf.puntuaciones')}</div>
              {ratingQs.map(q => {
                const min = ratingMin(q)
                const max = ratingMax(q)
                const buttons = []
                for (let n = min; n <= max; n++) buttons.push(n)
                return (
                  <div key={q.id} className="ds-row-between perf-box-3">
                    <div className="performance-reviews-page-e8">
                      <div className="performance-reviews-page-e9">
                        {q.label}{q.required && <span className="performance-reviews-page-e10"> *</span>}
                      </div>
                      {q.hint && <div className="ds-muted u-xs">{q.hint}</div>}
                    </div>
                    <div className="perf-row">
                      {buttons.map(n => {
                        const active = Number(answers[q.key]) >= n
                        return (
                          <Pulsable key={n}
                            onClick={() => setAnswers(s => ({ ...s, [q.key]: n }))}
                            aria-label={t('pagina_perf.de', { label: q.label, n, max })}
                            className={`perf-btn performa-sx1 ${active ? 'performa-sx2' : 'performa-sx3'} performance-reviews-page-e3`} style={{ '--performance-reviews-page-border': `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                            {n}
                          </Pulsable>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Preguntas no-rating: yes_no + text_short + text_long */}
          {otherQs.map(q => {
            if (q.kind === 'yes_no') {
              const v = answers[q.key]
              return (
                <div key={q.id} className="ds-field">
                  <label className="ds-field__label">
                    {q.label}{q.required && <span className="performance-reviews-page-e10"> *</span>}
                  </label>
                  {q.hint && <div className="ds-field__hint">{q.hint}</div>}
                  <div className="ds-row-wrap perf-box-4">
                    {[{ k: 'yes', l: t('pagina_perf.si') }, { k: 'no', l: t('pagina_perf.no') }].map(({ k, l }) => (
                      <Pulsable key={k}
                        onClick={() => setAnswers(s => ({ ...s, [q.key]: k }))}
                        className={`perf-btn-2 performa-sx4 ${v === k ? 'performa-sx5' : 'performa-sx6'} performance-reviews-page-e3`} style={{ '--performance-reviews-page-border': `1px solid ${v === k ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                        {l}
                      </Pulsable>
                    ))}
                  </div>
                </div>
              )
            }
            const isLong = q.kind === 'text_long'
            return (
              <div key={q.id} className="ds-field">
                <label id={`${idCampo}-${q.id}-et`} htmlFor={`${idCampo}-${q.id}`} className="ds-field__label">
                  {q.label}{q.required && <span className="performance-reviews-page-e10"> *</span>}
                </label>
                {q.hint && <div className="ds-field__hint">{q.hint}</div>}
                {isLong ? (
                  <textarea id={`${idCampo}-${q.id}`} aria-labelledby={`${idCampo}-${q.id}-et`} value={answers[q.key] || ''}
                    onChange={e => setAnswers(s => ({ ...s, [q.key]: e.target.value }))}
                    rows={3} className="ds-input perf-input" />
                ) : (
                  <input id={`${idCampo}-${q.id}`} aria-labelledby={`${idCampo}-${q.id}-et`} type="text" value={answers[q.key] || ''}
                    onChange={e => setAnswers(s => ({ ...s, [q.key]: e.target.value }))}
                    className="ds-input" />
                )}
              </div>
            )
          })}

          {questions.length === 0 && (
            <div className="ds-card--inset perf-box-5">
              <div className="ds-muted">{traducir('performancereviews.este_ciclo_aun_no_tiene_preguntas_configuradas')}</div>
            </div>
          )}

          {missingRequired.length > 0 && (
            <div className="performance-reviews-page-e11">
              <AlertCircle size={12} />{' '}{t('pagina_perf.faltan_respuestas', { n: missingRequired.length })}
            </div>
          )}

          <div className="performance-reviews-page-e12">
            <Button variant="secondary" onClick={() => save()} disabled={saving || submitting} loading={saving}>
              <Save size={13} />{' '}{t('pagina_perf.guardar_borrador')}
            </Button>
            <Button onClick={() => submit()}
              disabled={saving || submitting || missingRequired.length > 0}
              loading={submitting}>
              <Send size={13} /> {traducir('performancereviews.enviar_evaluacion')}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ── AssignReviewModal: HR/Admin asigna quién evalúa a quién (smart 360°) ───
function AssignReviewModal({ cycle, onClose }: { cycle: Cycle; onClose: () => void }) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({ reviewer_id: '', reviewee_id: '', review_type: 'manager' })

  const { data: users = [] } = useQuery({
    queryKey: ['users-for-review-assign'],
    // `usersApi.list` ya devuelve el array (todasLasPaginas).
    queryFn: () => usersApi.list({ page_size: SELECTOR_LIST_SIZE }).then(r => r.data),
  })

  // Cuando hay reviewee, consultamos backend para conocer la elegibilidad por
  // tipo. Mostramos en paralelo los 4 tipos para activar/desactivar chips.
  const eligibilityQueries = useQueries({
    queries: REVIEW_TYPES.map(t => ({
      queryKey: ['perf-eligible', cycle.id, form.reviewee_id, t.id],
      queryFn: (): Promise<EligiblePool> => performanceApi.eligibleReviewers(cycle.id, form.reviewee_id, t.id).then(r => r.data),
      enabled: !!form.reviewee_id,
    })),
  })

  const elByType: Record<string, EligiblePool | undefined> = Object.fromEntries(REVIEW_TYPES.map((t, i) => [t.id, eligibilityQueries[i].data]))

  const currentTypePool: EligiblePool | undefined = elByType[form.review_type]
  const eligibleUsers = currentTypePool?.users || []
  const blockedReason = currentTypePool?.reason_blocked

  // Si cambia el reviewee, reseteamos el reviewer_id por seguridad
  useEffect(() => {
    if (!form.reviewee_id) return
    if (form.review_type === 'self') {
      setForm(f => ({ ...f, reviewer_id: f.reviewee_id }))
    } else {
      setForm(f => ({ ...f, reviewer_id: '' }))
    }
  }, [form.reviewee_id, form.review_type])

  const camposD = useErroresDeCampo()
  const msgD = (k: string) => camposD.de(k) ? <div className="u-field-error">{camposD.de(k)}</div> : null
  const { mutate: assign, isPending } = useMutation({
    onMutate: () => camposD.limpiar(),
    mutationFn: () => performanceApi.createReview(cycle.id, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', cycle.id] })
      qc.invalidateQueries({ queryKey: ['perf-cycles'] })
      toast.success(t('pagina_perf.evaluacion_asignada'))
      onClose()
    },
    onError: (e: unknown) => { if (!camposD.recoger(e)) toast.error(extractErr(e, t('pagina_perf.error_al_asignar'))) },
  })

  const isSelfType = form.review_type === 'self'
  const canSubmit = !!form.reviewee_id && !!form.reviewer_id && !!form.review_type && !blockedReason

  return (
    <Modal open onClose={onClose}
      title={traducir('performancereviews.asignar_evaluacion')}
      subtitle={t('pagina_perf.ciclo', { name: cycle.name })}
      width={560}>
      <div className="ds-stack perf-box-2">
        {/* Persona evaluada (primero, para poder calcular elegibilidad) */}
        <div className="ds-field">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{t('pagina_perf.persona_evaluada')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.reviewee_id}
            onChange={e => { camposD.limpiar('reviewee_id'); setForm(f => ({ ...f, reviewee_id: e.target.value })) }}>
            <option value="">{t('pagina_perf.selecciona')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>{msgD('reviewee_id')}
        </div>

        {/* Tipo de evaluación */}
        <div className="ds-field" role="group" aria-labelledby={`${idCampo}-tipo-et`}>
          <div id={`${idCampo}-tipo-et`} className="ds-field__label">{t('pagina_perf.tipo')}</div>
          <div className="ds-row-wrap">
            {REVIEW_TYPES.map(({ id, Icon, label }) => {
              const active = form.review_type === id
              const pool = elByType[id]
              const disabled = !!form.reviewee_id && !!pool && (pool.users?.length || 0) === 0 && id !== 'self'
              const tip = disabled ? (pool?.reason_blocked || t('pagina_perf.no_hay_evaluadores_elegibles')) : undefined
              return (
                <span key={id} title={tip} className="perf-row-2">
                  <Pulsable
                    onClick={() => !disabled && setForm(f => ({
                      ...f, review_type: id,
                      reviewer_id: id === 'self' ? f.reviewee_id : '',
                    }))}
                    disabled={disabled}
                    className={`perf-chip ${active ? 'perf-chip--activo' : ''} ${disabled ? 'perf-chip--inactivo' : ''}`}>
                    <Icon size={13} /> {t(label)}
                  </Pulsable>
                </span>
              )
            })}
          </div>
          <div className="ds-field__hint">{TYPE_BY_ID[form.review_type] && t(TYPE_BY_ID[form.review_type].help)}</div>
          {blockedReason && (
            <div className="performance-reviews-page-e4">
              <AlertCircle size={12} /> {blockedReason}
            </div>
          )}
        </div>

        {/* Evaluador (oculto si es 'self') — restringido al pool elegible */}
        {!isSelfType && (
          <div className="ds-field">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">{t('pagina_perf.evaluador')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.reviewer_id}
              onChange={e => { camposD.limpiar('reviewer_id'); setForm(f => ({ ...f, reviewer_id: e.target.value })) }}
              disabled={!form.reviewee_id || !!blockedReason}>
              <option value="">{form.reviewee_id ? t('pagina_perf.selecciona') : t('pagina_perf.elige_primero_la_persona_evaluada')}</option>
              {eligibleUsers.map(u => (
                <option key={u.id} value={u.id}>
                  {u.full_name}{u.team ? ` · ${u.team}` : (u.department ? ` · ${u.department}` : '')}
                </option>
              ))}
            </Select>{msgD('reviewer_id')}
            {form.reviewee_id && !blockedReason && eligibleUsers.length > 0 && (
              <div className="ds-field__hint">
                {eligibleUsers.length} {traducir('performancereviews.evaluador_es_elegible_s_segun_organigrama_y')}
              </div>
            )}
          </div>
        )}

        <div className="performance-reviews-page-e12">
          <Button variant="secondary" onClick={onClose}>{t('pagina_perf.cancelar')}</Button>
          <Button onClick={() => assign()} disabled={!canSubmit || isPending} loading={isPending}>
            <UserPlus size={13} />{' '}{t('pagina_perf.asignar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── QuestionsEditor: edita la plantilla de preguntas de un ciclo en draft ───
function QuestionsEditor({ cycleId, cycleStatus }: { cycleId: string; cycleStatus: string }) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const editable = cycleStatus === 'draft'

  const { data: questions = [], isLoading } = useQuery<Question[]>({
    queryKey: ['perf-cycle-questions', cycleId],
    queryFn: () => performanceApi.listQuestions(cycleId).then(r => r.data),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['perf-cycle-questions', cycleId] })

  const { mutate: addQ } = useMutation({
    mutationFn: (data: QuestionPayload) => performanceApi.addQuestion(cycleId, data),
    onSuccess: () => { invalidate(); toast.success(t('pagina_perf.pregunta_anadida')) },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_anadir'))),
  })
  const { mutate: updateQ } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: QuestionPayload }) => performanceApi.updateQuestion(id, data),
    onSuccess: () => { invalidate(); toast.success(t('pagina_perf.pregunta_actualizada')) },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_actualizar'))),
  })
  const { mutate: removeQ } = useMutation({
    mutationFn: (id: string) => performanceApi.deleteQuestion(id),
    onSuccess: () => { invalidate(); toast.success(t('pagina_perf.pregunta_eliminada')) },
    onError: e => toast.error(extractErr(e, t('pagina_perf.error_al_eliminar'))),
  })

  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Question | null>(null)

  if (isLoading) return <Spinner />

  return (
    <div className="ds-card--inset perf-stack-2">
      <div className="ds-row-between">
        <div className="ds-eyebrow performance-reviews-page-e13">
          <ListChecks size={12} /> {traducir('performancereviews.plantilla_de_preguntas')}{questions.length})
        </div>
        {editable && (
          <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
            <Plus size={11} /> {traducir('performancereviews.anadir')}
          </Button>
        )}
      </div>
      {questions.length === 0 ? (
        <div className="ds-muted u-sm">
          {traducir('performancereviews.sin_preguntas')} {editable && t('pagina_perf.anade_alguna_o_siembra_las_predeterminadas')}
        </div>
      ) : (
        <div className="ds-stack-sm">
          {questions.map(q => (
            <div key={q.id} className="ds-row-between performance-reviews-page-e14">
              <div className="performance-reviews-page-e8">
                <div className="performance-reviews-page-e9">
                  {q.label}{q.required && <span className="performance-reviews-page-e10"> *</span>}
                </div>
                <div className="ds-muted u-xs">
                  {KIND_LABEL[q.kind] ? t(KIND_LABEL[q.kind]) : q.kind}{' '}{t('pagina_perf.key')}{q.key}
                </div>
              </div>
              {editable && (
                <div className="perf-row-3">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(q)} aria-label={t('pagina_perf.editar')}>
                    <Pencil size={11} />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={async () => {
                    if (await confirmar({ message: t('pagina_perf.eliminar_pregunta', { label: q.label }), danger: true, confirmLabel: t('pagina_perf.eliminar') })) removeQ(q.id)
                  }} aria-label={t('pagina_perf.eliminar')}>
                    <Trash2 size={11} />
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {!editable && (
        <div className="ds-muted u-xs">
          {traducir('performancereviews.la_plantilla_solo_es_editable_mientras_el')}
        </div>
      )}
      {adding && (
        <QuestionEditModal
          onClose={() => setAdding(false)}
          onSave={data => { addQ(data); setAdding(false) }}
        />
      )}
      {editing && (
        <QuestionEditModal
          question={editing}
          onClose={() => setEditing(null)}
          onSave={data => { updateQ({ id: editing.id, data }); setEditing(null) }}
        />
      )}
    </div>
  )
}

function QuestionEditModal({ question, onClose, onSave }: {
  question?: Question; onClose: () => void; onSave: (data: QuestionPayload) => void
}) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const isEdit = !!question
  const [form, setForm] = useState(() => ({
    key:       question?.key       || '',
    label:     question?.label     || '',
    hint:      question?.hint      || '',
    kind:      question?.kind      || 'rating_5',
    required:  question?.required  || false,
    scale_min: question?.scale_min ?? '',
    scale_max: question?.scale_max ?? '',
  }))

  const submit = () => {
    const data: QuestionPayload = {
      label: form.label.trim(),
      hint:  form.hint.trim() || null,
      kind:  form.kind,
      required: !!form.required,
      scale_min: form.scale_min === '' ? null : Number(form.scale_min),
      scale_max: form.scale_max === '' ? null : Number(form.scale_max),
    }
    if (!isEdit) {
      data.key = form.key.trim() || form.label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 60)
    }
    onSave(data)
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? t('pagina_perf.editar_pregunta') : t('pagina_perf.nueva_pregunta')} width={520}>
      <div className="ds-stack">
        {!isEdit && (
          <div className="ds-field">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{t('pagina_perf.identificador_opcional')}</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.key} onChange={e => setForm(f => ({ ...f, key: e.target.value }))}
              className="ds-input" placeholder={traducir('performancereviews.se_genera_del_titulo_si_lo_dejas')} />
          </div>
        )}
        <div className="ds-field">
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">{t('pagina_perf.pregunta')}</label>
          <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
            className="ds-input" placeholder={traducir('performancereviews.ej_calidad_del_trabajo')} autoFocus />
        </div>
        <div className="ds-field">
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="ds-field__label">{t('pagina_perf.ayuda_opcional')}</label>
          <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.hint} onChange={e => setForm(f => ({ ...f, hint: e.target.value }))}
            className="ds-input" placeholder={traducir('performancereviews.texto_pequeno_de_apoyo_bajo_la_pregunta')} />
        </div>
        <div className="performance-reviews-page-e15">
          <div className="ds-field">
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="ds-field__label">{t('pagina_perf.tipo')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.kind} onChange={e => setForm(f => ({ ...f, kind: e.target.value }))}>
              {QUESTION_KINDS.map(k => <option key={k.id} value={k.id}>{t(k.label)}</option>)}
            </Select>
          </div>
          <div className="ds-field perf-box-6">
            <Checkbox className="perf-label-2" checked={!!form.required}
              onChange={v => setForm(f => ({ ...f, required: v }))} label={t('pagina_perf.obligatoria')} />
          </div>
        </div>
        {isRatingKind(form.kind) && (
          <div className="performance-reviews-page-e15">
            <div className="ds-field">
              <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="ds-field__label">{traducir('performancereviews.escala_min')}</label>
              <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} type="number" value={form.scale_min}
                onChange={e => setForm(f => ({ ...f, scale_min: e.target.value }))}
                className="ds-input" placeholder="1" />
            </div>
            <div className="ds-field">
              <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="ds-field__label">{traducir('performancereviews.escala_max')}</label>
              <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="number" value={form.scale_max}
                onChange={e => setForm(f => ({ ...f, scale_max: e.target.value }))}
                className="ds-input" placeholder={form.kind === 'rating_10' ? '10' : '5'} />
            </div>
          </div>
        )}
        <div className="performance-reviews-page-e12">
          <Button variant="secondary" onClick={onClose}>{t('pagina_perf.cancelar')}</Button>
          <Button onClick={submit} disabled={!form.label.trim()}>
            <Save size={13} />{' '}{t('pagina_perf.guardar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── New360CampaignModal: wizard que crea una campaña con todos sus evaluadores
function New360CampaignModal({ cycle, onClose }: { cycle: Cycle; onClose: () => void }) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()

  // Estado de la campaña agrupado en un único objeto. Se exponen setters
  // específicos para preservar la legibilidad de los handlers existentes.
  const [campaign, setCampaign] = useState<{
    subjectId: string; selfReview: boolean; managerId: string
    peerIds: string[]; upwardIds: string[]; threshold: number | string
  }>({
    subjectId: '',
    selfReview: true,
    managerId: '',
    peerIds: [],
    upwardIds: [],
    threshold: 3,
  })
  const { subjectId, selfReview, managerId, peerIds, upwardIds, threshold } = campaign
  const setSubjectId  = (v: string) => setCampaign(s => ({ ...s, subjectId: v }))
  const setSelfReview = (v: boolean) => setCampaign(s => ({ ...s, selfReview: v }))
  const setManagerId  = (v: string) => setCampaign(s => ({ ...s, managerId: v }))
  const setPeerIds    = (updater: string[] | ((prev: string[]) => string[])) => setCampaign(s => ({
    ...s, peerIds: typeof updater === 'function' ? updater(s.peerIds) : updater,
  }))
  const setUpwardIds  = (updater: string[] | ((prev: string[]) => string[])) => setCampaign(s => ({
    ...s, upwardIds: typeof updater === 'function' ? updater(s.upwardIds) : updater,
  }))
  const setThreshold  = (v: string) => setCampaign(s => ({ ...s, threshold: v }))

  const { data: users = [] } = useQuery({
    queryKey: ['users-for-360-campaign'],
    // `usersApi.list` ya devuelve el array (todasLasPaginas).
    queryFn: () => usersApi.list({ page_size: SELECTOR_LIST_SIZE }).then(r => r.data),
  })

  // Para cada tipo (excepto self) calculamos elegibilidad cuando hay subject
  const elQueries = useQueries({
    queries: ['manager', 'peer', 'upward'].map(t => ({
      queryKey: ['perf-eligible', cycle.id, subjectId, t],
      queryFn: (): Promise<EligiblePool> => performanceApi.eligibleReviewers(cycle.id, subjectId, t).then(r => r.data),
      enabled: !!subjectId,
    })),
  })
  const [managerData, peerData, upwardData] = elQueries.map(q => q.data)
  const managerOptions: EligibleUser[] = managerData?.users || []
  const peerOptions: EligibleUser[]    = peerData?.users    || []
  const upwardOptions: EligibleUser[]  = upwardData?.users  || []

  // Si hay un único manager elegible, lo preseleccionamos.
  // Omitimos managerId y setManagerId a propósito: managerId solo se usa para
  // evitar pisar una selección manual (la guard `!managerId` ya lo cubre);
  // incluirlo dispararía el efecto cuando el usuario eligiese, y setManagerId
  // es una función creada en cada render que provocaría re-ejecuciones inútiles.
  useEffect(() => {
    if (managerOptions.length === 1 && !managerId) setManagerId(managerOptions[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- omisión deliberada, ver arriba
  }, [managerOptions])

  // Cuando cambia el subject reseteamos selecciones derivadas
  useEffect(() => {
    setManagerId('')
    setPeerIds([])
    setUpwardIds([])
  }, [subjectId])

  const togglePeer   = (id: string) => setPeerIds  (s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])
  const toggleUpward = (id: string) => setUpwardIds(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  const totalReviewers = (selfReview ? 1 : 0) + (managerId ? 1 : 0) + peerIds.length + upwardIds.length

  const { mutate: create, isPending } = useMutation({
    mutationFn: () => performanceApi.createCampaign(cycle.id, {
      subject_id: subjectId,
      self_review: selfReview,
      manager_reviewer_id: managerId || null,
      peer_reviewer_ids: peerIds,
      upward_reviewer_ids: upwardIds,
      anonymity_threshold: Number(threshold) || 3,
      auto_activate: true,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['perf-campaigns', cycle.id] })
      qc.invalidateQueries({ queryKey: ['perf-cycle-reviews', cycle.id] })
      toast.success(t('pagina_perf.campana_360_creada_con_evaluador_es', { totalReviewers }))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_perf.error_al_crear_campana'))),
  })

  const canCreate = !!subjectId && totalReviewers > 0 && !isPending

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <Target size={16} /> {traducir('performancereviews.nueva_campana_360')}
      </span>}
      subtitle={t('pagina_perf.ciclo', { name: cycle.name })}
      width={680}>
      <div className="ds-stack perf-box-2">
        {/* Subject */}
        <div className="ds-field">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{t('pagina_perf.persona_evaluada')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-1`} value={subjectId}
            onChange={e => setSubjectId(e.target.value)}>
            <option value="">{t('pagina_perf.selecciona')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
        </div>

        {!subjectId ? (
          <div className="ds-card--inset perf-box-5">
            <div className="ds-muted">{traducir('performancereviews.selecciona_primero_la_persona_a_evaluar_para')}</div>
          </div>
        ) : (
          <>
            {/* Self */}
            <div className="ds-card--inset perf-row-4">
              <Checkbox id="self-review-cb" className="perf-label-3" checked={!!selfReview} onChange={setSelfReview}
                label={<div className="perf-box-7">
                  <User size={12} className="perf-box-38" /> {traducir('performancereviews.autoevaluacion')}
                </div>}
                ayuda={traducir('performancereviews.la_propia_persona_se_evalua_recomendado_en')} />
            </div>

            {/* Manager */}
            <div className="ds-field">
              <label id={`${idCampo}-manager-et`} htmlFor={`${idCampo}-manager`} className="ds-field__label">
                <Crown size={11} className="perf-box-38" />{' '}{t('pagina_perf.manager')}
              </label>
              {managerData?.reason_blocked ? (
                <div className="performance-reviews-page-e11">
                  <AlertCircle size={12} /> {managerData.reason_blocked}
                </div>
              ) : (
                <Select suelto placeholder={false} id={`${idCampo}-manager`} value={managerId} onChange={e => setManagerId(e.target.value)}>
                  <option value="">{traducir('performancereviews.sin_manager')}</option>
                  {managerOptions.map(u => (
                    <option key={u.id} value={u.id}>{u.full_name}</option>
                  ))}
                </Select>
              )}
            </div>

            {/* Peers */}
            <div className="ds-field">
              <label className="ds-field__label">
                <UsersIcon size={11} className="perf-box-38" />{' '}{t('pagina_perf.pares')}
                <span className="ds-muted perf-label-4">
                  {t('pagina_perf.pares_seleccionados', { n: peerIds.length, total: peerOptions.length })}
                </span>
              </label>
              {peerData?.reason_blocked ? (
                <div className="performance-reviews-page-e11">
                  <AlertCircle size={12} /> {peerData.reason_blocked}
                </div>
              ) : peerOptions.length === 0 ? (
                <div className="ds-muted u-xs">
                  {traducir('performancereviews.sin_pares_elegibles')}
                </div>
              ) : (
                <div className="ds-row-wrap perf-box-8">
                  {peerOptions.map(u => {
                    const sel = peerIds.includes(u.id)
                    return (
                      <Pulsable key={u.id} onClick={() => togglePeer(u.id)}
                        className={`perf-btn-3 performa-sx4 ${sel ? 'performa-sx5' : 'performa-sx6'} performance-reviews-page-e3`} style={{ '--performance-reviews-page-border': `1px solid ${sel ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                        {u.full_name}
                        {u.team && <span className="perf-label-5">· {u.team}</span>}
                      </Pulsable>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Upward */}
            <div className="ds-field">
              <label className="ds-field__label">
                <ArrowUp size={11} className="perf-box-38" />{' '}{t('pagina_perf.reportes_directos_upward')}
                <span className="ds-muted perf-label-4">
                  ({upwardIds.length}/{upwardOptions.length})
                </span>
              </label>
              {upwardData?.reason_blocked ? (
                <div className="perf-row-5">
                  <AlertCircle size={12} /> {upwardData.reason_blocked}
                </div>
              ) : upwardOptions.length === 0 ? (
                <div className="ds-muted u-xs">
                  {traducir('performancereviews.sin_reportes_directos')}
                </div>
              ) : (
                <div className="ds-row-wrap perf-box-8">
                  {upwardOptions.map(u => {
                    const sel = upwardIds.includes(u.id)
                    return (
                      <Pulsable key={u.id} onClick={() => toggleUpward(u.id)}
                        className={`perf-btn-3 performa-sx4 ${sel ? 'performa-sx5' : 'performa-sx6'} performance-reviews-page-e3`} style={{ '--performance-reviews-page-border': `1px solid ${sel ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                        {u.full_name}
                      </Pulsable>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Anonimización */}
            <div className="ds-field">
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">
                <Lock size={11} className="perf-box-38" /> {traducir('performancereviews.umbral_de_anonimizacion')}
              </label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" min={1} max={20} value={threshold}
                onChange={e => setThreshold(e.target.value)}
                className="ds-input perf-input-2" />
              <div className="ds-field__hint">
                {traducir('performancereviews.cuando_un_grupo_pares_upward_tenga_menos')}
              </div>
            </div>
          </>
        )}

        <div className="ds-row-between perf-box-9">
          <div className="ds-muted u-sm">
            {t('pagina_perf.total')}{' '}<strong className="u-text1">{totalReviewers}</strong>{' '}{t('pagina_perf.evaluador_es')}
          </div>
          <div className="perf-row-6">
            <Button variant="secondary" onClick={onClose}>{t('pagina_perf.cancelar')}</Button>
            <Button onClick={() => create()} disabled={!canCreate} loading={isPending}>
              <Target size={13} /> {traducir('performancereviews.crear_campana_360')}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

// ── Campaign360Dashboard: panel agregado y anonimizado por subject ─────────
function Campaign360Dashboard({ campaignId, onClose, onOpenHistory }: {
  campaignId: string; onClose: () => void; onOpenHistory?: (id: string, name: string) => void
}) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const toast = useToast()
  const { data, isLoading } = useQuery<CampaignDashboard>({
    queryKey: ['perf-campaign-dashboard', campaignId],
    queryFn: () => performanceApi.campaignDashboard(campaignId).then(r => r.data),
  })

  const downloadPdf = async () => {
    try {
      const res = await performanceApi.campaignDashboardPdf(campaignId)
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const name = data?.campaign?.subject_name?.replace(/\s+/g, '_') || 'subject'
      a.download = `360_${name}_${campaignId.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      toast.error(extractErr(e, t('pagina_perf.error_al_descargar_pdf')))
    }
  }

  if (isLoading || !data) {
    return (
      <Modal open onClose={onClose} title={t('pagina_perf.dashboard_360')} width={760}>
        <Spinner />
      </Modal>
    )
  }

  const c = data.campaign
  const groups = data.groups || {}
  const ratingQs = (data.questions || []).filter(q => isRatingKind(q.kind))
  const textQs   = (data.questions || []).filter(q => !isRatingKind(q.kind))

  const GROUP_META = [
    { id: 'self',    label: t('pagina_perf.self'),    Icon: User },
    { id: 'manager', label: t('pagina_perf.manager'), Icon: Crown },
    { id: 'peer',    label: t('pagina_perf.pares'),   Icon: UsersIcon },
    { id: 'upward',  label: t('pagina_perf.upward'),  Icon: ArrowUp },
  ]

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <BarChart3 size={16} />{' '}{t('pagina_perf.dashboard_360_2')}{' '}{c.subject_name}
      </span>}
      subtitle={t('pagina_perf.respuestas_umbral', { enviadas: data.total_submitted, total: data.total_assigned, umbral: data.anonymity_threshold })}
      width={760}>
      <div className="ds-stack perf-box-2">
        {/* Resumen por grupo */}
        <div className="ds-grid-cards perf-box-10">
          {GROUP_META.map(({ id, label, Icon }) => {
            const g = groups[id] || { count: 0, anonymized: false }
            return (
              <div key={id} className="ds-card--inset perf-box-5">
                <div className="perf-row-5">
                  <Icon size={11} /> {label}
                </div>
                <div className="perf-box-11">
                  {g.count}
                </div>
                {g.anonymized && (
                  <div className="perf-row-7">
                    <Lock size={9} />{' '}{t('pagina_perf.anonimizado')}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Comparación por pregunta tipo rating */}
        {ratingQs.length > 0 && (
          <div className="ds-card--inset perf-stack">
            <div className="ds-eyebrow">{traducir('performancereviews.comparacion_por_pregunta')}</div>
            {ratingQs.map(q => {
              const max = ratingMax(q)
              const cmp = data.comparison?.[q.key] || {}
              const selfVal = cmp.self
              const peersVal = cmp.peers
              const managerVal = cmp.manager
              const upwardVal = cmp.upward
              // Detectar gap self vs others (blind spot / hidden strength)
              const others = [peersVal, managerVal, upwardVal].filter(v => v != null)
              const othersAvg = others.length ? others.reduce((s, v) => s + v, 0) / others.length : null
              let gapBadge = null
              if (selfVal != null && othersAvg != null) {
                const diff = selfVal - othersAvg
                if (Math.abs(diff) >= 1) {
                  gapBadge = diff > 0
                    ? { text: t('pagina_perf.punto_ciego'), color: 'var(--warning)' }
                    : { text: t('pagina_perf.fortaleza_no_percibida'), color: 'var(--success)' }
                }
              }
              return (
                <div key={q.id}>
                  <div className="ds-row-between perf-box-12">
                    <div className="performance-reviews-page-e9">
                      {q.label}
                    </div>
                    {gapBadge && (
                      <span className="perf-label-6 performance-reviews-page-e2" style={{ '--performance-reviews-page-color': gapBadge.color } as CSSProperties}>
                        {gapBadge.text}
                      </span>
                    )}
                  </div>
                  <div className="perf-grid">
                    {GROUP_META.map(({ id, label }) => {
                      const key = id === 'peer' ? 'peers' : id
                      const v = cmp[key]
                      if (v == null) {
                        return (
                          <div key={id} className="ds-row perf-box-13">
                            <span className="perf-label-7">{label}</span>
                            <span className="ds-muted u-xs">—</span>
                          </div>
                        )
                      }
                      return (
                        <div key={id} className="ds-row perf-box-13">
                          <span className="perf-label-7">{label}</span>
                          <div className="u-flex1">
                            <ScoreBar value={v} max={max} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Comentarios de texto, agrupados y anonimizados si procede */}
        {textQs.length > 0 && (
          <div className="ds-stack-sm">
            <div className="ds-eyebrow">{t('pagina_perf.comentarios_cualitativos')}</div>
            {textQs.map(q => (
              <div key={q.id} className="ds-card--inset perf-box-14">
                <div className="perf-box-15">
                  {q.label}
                </div>
                {GROUP_META.map(({ id, label, Icon }) => {
                  const g = groups[id]
                  if (!g) return null
                  const items = g.text_by_question?.[q.key] || []
                  return (
                    <div key={id} className="perf-box-16">
                      <div className="ds-row perf-box-17">
                        <Icon size={11} /> {label}
                        {g.anonymized && (
                          <span className="perf-row-8">
                            <Lock size={9} />{' '}{t('pagina_perf.oculto_umbral', { n: g.count, umbral: data.anonymity_threshold })}
                          </span>
                        )}
                      </div>
                      {!g.anonymized && items.length === 0 && (
                        <div className="ds-muted perf-box-18">
                          {traducir('performancereviews.sin_respuestas')}
                        </div>
                      )}
                      {!g.anonymized && items.map((it, idx: number) => (
                        <div key={idx} className="perf-box-19">
                          {String(it.text)}
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        )}

        <div className="perf-row-9">
          <div className="perf-row-6">
            <Button variant="secondary"
              onClick={() => onOpenHistory?.(c.subject_id, c.subject_name)}>
              <TrendingUp size={13} /> {traducir('performancereviews.ver_evolucion_historica')}
            </Button>
            <Button variant="secondary" onClick={downloadPdf}>
              <FileDown size={13} />{' '}{t('pagina_perf.descargar_pdf')}
            </Button>
          </div>
          <Button variant="secondary" onClick={onClose}>
            <X size={13} />{' '}{t('pagina_perf.cerrar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── History360Modal: evolución del subject a lo largo de varios ciclos ────
function History360Modal({ subjectId, subjectName, onClose }: {
  subjectId?: string; subjectName?: string; onClose: () => void
}) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const { data, isLoading } = useQuery<History360>({
    queryKey: ['perf-360-history', subjectId],
    queryFn: () => performanceApi.history360(subjectId).then(r => r.data),
  })

  // useMemo (auditoría 2026-08, P1-6): con `?? []` / `|| []` esto creaba un
  // array nuevo en cada render, así que los useMemo/useEffect que lo tienen
  // como dependencia se reejecutaban SIEMPRE — no memoizaban nada.
  const series: HistoryPoint[] = useMemo(() => data?.series || [], [data?.series])
  // Recopilamos todas las question keys que aparecen al menos una vez
  const allQs = useMemo<HistoryQuestion[]>(() => {
    const map = new Map<string, HistoryQuestion>()
    for (const s of series) {
      for (const [k, v] of Object.entries(s.ratings || {})) {
        if (!map.has(k)) map.set(k, { key: k, label: v.label, max: v.scale_max })
      }
    }
    return [...map.values()]
  }, [series])

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <TrendingUp size={16} /> {traducir('performancereviews.evolucion_360')} {subjectName || data?.subject_name}
      </span>}
      subtitle={t('pagina_perf.campanas_con_respuestas', { length: series.length })}
      width={780}>
      {isLoading ? <Spinner /> : series.length === 0 ? (
        <EmptyState icon={<History size={28} />}
          title={traducir('performancereviews.sin_historico_aun')}
          description={t('pagina_perf.cuando_se_cierren_campanas_con_respuestas')} />
      ) : (
        <div className="ds-stack perf-box-3">
          {/* Cabecera con cycles */}
          <div className="perf-grid-2 performance-reviews-page-e5" style={{ '--performance-reviews-page-grid-template-columns': `220px repeat(${series.length}, 1fr)` } as CSSProperties}>
            <div className="ds-eyebrow perf-box-20">{t('pagina_perf.pregunta_2')}</div>
            {series.map(s => (
              <div key={s.campaign_id} className="perf-box-21">
                <div className="perf-box-22">
                  {s.cycle_name}
                </div>
                <div className="ds-muted perf-box-23">
                  {s.created_at}
                </div>
              </div>
            ))}
          </div>

          {/* Filas: una por pregunta de rating */}
          {allQs.map(q => (
            <div key={q.key} className="perf-grid-3 performance-reviews-page-e5" style={{ '--performance-reviews-page-grid-template-columns': `220px repeat(${series.length}, 1fr)` } as CSSProperties}>
              <div className="performance-reviews-page-e9">
                {q.label}
              </div>
              {series.map(s => {
                const r = s.ratings?.[q.key]
                if (!r) {
                  return <div key={s.campaign_id} className="ds-muted perf-box-24"
                   >—</div>
                }
                const others = r.others
                const self   = r.self
                return (
                  <div key={s.campaign_id} className="perf-stack-3">
                    {others != null && (
                      <div className="perf-row-10">
                        <span className="perf-label-8">{t('pagina_perf.otros')}</span>
                        <div className="u-flex1">
                          <ScoreBar value={others} max={q.max} />
                        </div>
                      </div>
                    )}
                    {self != null && (
                      <div className="perf-row-10">
                        <span className="perf-label-8">{t('pagina_perf.autoevaluacion')}</span>
                        <div className="u-flex1">
                          <ScoreBar value={self} max={q.max} />
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      )}
      <div className="perf-row-11">
        <Button variant="secondary" onClick={onClose}>
          <X size={13} />{' '}{t('pagina_perf.cerrar')}
        </Button>
      </div>
    </Modal>
  )
}

// ── CampaignsList: campañas 360° dentro de un ciclo ───────────────────────
function CampaignsList({ cycle, isManager, onCreate, onOpenDashboard }: {
  cycle: Cycle; isManager: boolean; onCreate: (cycle: Cycle) => void; onOpenDashboard: (id: string) => void
}) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const { data: campaigns = [], isLoading } = useQuery<Campaign[]>({
    queryKey: ['perf-campaigns', cycle.id],
    queryFn: () => performanceApi.listCampaigns(cycle.id).then(r => r.data).catch(() => []),
  })

  return (
    <div className="ds-card--inset perf-stack-2">
      <div className="ds-row-between">
        <div className="ds-eyebrow performance-reviews-page-e13">
          <Target size={12} /> {traducir('performancereviews.campanas_360')}{campaigns.length})
        </div>
        {cycle.status !== 'closed' && (
          <span title={!isManager ? t(NO_PERMISSION_TIP) : undefined} className="perf-row-2">
            <Button size="sm" onClick={() => onCreate(cycle)} disabled={!isManager}>
              <Plus size={11} /> {traducir('performancereviews.nueva_campana')}
            </Button>
          </span>
        )}
      </div>
      {isLoading ? <Spinner /> : campaigns.length === 0 ? (
        <div className="ds-muted u-sm">
          {traducir('performancereviews.sin_campanas_una_campana_agrupa_autoevaluacion_manager')}
        </div>
      ) : (
        <div className="ds-stack-sm">
          {campaigns.map(camp => {
            const total = camp.total_reviewers || 0
            const submitted = camp.submitted || 0
            const pct = total ? Math.round((submitted / total) * 100) : 0
            return (
              // Auditoría 2026-08 (P1-6): fila clicable sin vía de teclado.
              <div key={camp.id} className="ds-row-between performance-reviews-page-e6"
                role="button"
                tabIndex={0}
                aria-label={t('pagina_perf.abrir_campana_de', { subject_name: camp.subject_name })}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenDashboard(camp.id) }
                }}
                onClick={() => onOpenDashboard(camp.id)}>
                <div className="performance-reviews-page-e8">
                  <div className="performance-reviews-page-e16">
                    {camp.subject_name}
                  </div>
                  <div className="ds-muted u-xs">
                    {submitted}/{total}{' '}{t('pagina_perf.respuestas')}{pct}%) · {camp.status}
                    {' · '}
                    {Object.entries(camp.by_type || {})
                      .filter(([, n]) => n > 0)
                      .map(([t, n]) => `${t}:${n}`).join(' ')}
                  </div>
                </div>
                <div className="perf-row-12">
                  <BarChart3 size={13} />
                  <span className="perf-label-9">{t('pagina_perf.dashboard')}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── CycleCard: tarjeta de un ciclo con sus evaluaciones ────────────────────
function CycleCard({ cycle, isManager, onActivate, onCloseCycle, onAssign, onCreateCampaign, onOpenDashboard }: {
  cycle: Cycle; isManager: boolean
  onActivate: (id: string) => void; onCloseCycle: (id: string) => void
  onAssign: (cycle: Cycle) => void; onCreateCampaign: (cycle: Cycle) => void; onOpenDashboard: (id: string) => void
}) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const [expanded, setExpanded] = useState(false)
  const { data: reviews = [], isLoading } = useQuery<Review[]>({
    queryKey: ['perf-cycle-reviews', cycle.id],
    queryFn: () => performanceApi.cycleReviews(cycle.id).then(r => r.data).catch(() => []),
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
function NewCycleModal({ existingCycles, onClose }: { existingCycles: Cycle[]; onClose: () => void }) {
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
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{t('pagina_perf.nombre')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => { camposB.limpiar('name'); setForm(f => ({ ...f, name: e.target.value })) }}
            className="ds-input" placeholder={traducir('performancereviews.ej_evaluacion_q1_2026')} autoFocus />{msgB('name')}
        </div>
        <div className="performance-reviews-page-e15">
          <div className="ds-field">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">{t('pagina_perf.inicio')}</label>
            <DateInput id={`${idCampo}-2`} value={form.start_date}
              onChange={e => { camposB.limpiar('start_date'); setForm(f => ({ ...f, start_date: e.target.value })) }}
              className="ds-input" />{msgB('start_date')}
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="ds-field__label">{t('pagina_perf.fin')}</label>
            <DateInput id={`${idCampo}-3`} value={form.end_date}
              onChange={e => { camposB.limpiar('end_date'); setForm(f => ({ ...f, end_date: e.target.value })) }}
              className="ds-input" />{msgB('end_date')}
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
function KPIDashboardTab({ cycles }: { cycles: Cycle[] }) {
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

// ── DevPlansTab: planes de desarrollo del usuario actual ───────────────────
const PLAN_STATUS_CFG = {
  draft:     { label: 'pagina_perf.borrador', color: 'var(--text-3)' },
  active:    { label: 'pagina_perf.activo',   color: 'var(--accent)' },
  completed: { label: 'pagina_perf.completado_4', color: 'var(--success)' },
  archived:  { label: 'pagina_perf.archivado', color: 'var(--text-4)' },
}
const GOAL_STATUS_CFG = {
  pending:     { label: 'pagina_perf.pendiente',   color: 'var(--text-3)' },
  in_progress: { label: 'pagina_perf.en_curso',    color: 'var(--accent)' },
  done:        { label: 'pagina_perf.completado_4',  color: 'var(--success)' },
  blocked:     { label: 'pagina_perf.bloqueado',   color: 'var(--warning)' },
  cancelled:   { label: 'pagina_perf.cancelado',   color: 'var(--text-4)' },
}

function DevPlansTab({ subjectId, subjectName }: { subjectId?: string; subjectName?: string }) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const [openPlanId, setOpenPlanId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const { data: plans = [], isLoading } = useQuery<DevPlan[]>({
    queryKey: ['dev-plans', subjectId],
    queryFn: () => performanceApi.listUserPlans(subjectId).then(r => r.data),
    enabled: !!subjectId,
  })

  return (
    <div className="ds-stack perf-box-3">
      <div className="ds-row-between">
        <div className="ds-eyebrow performance-reviews-page-e13">
          <MapIcon size={12} /> {traducir('performancereviews.planes_de_desarrollo_de')} {subjectName}
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus size={11} /> {traducir('performancereviews.nuevo_plan')}
        </Button>
      </div>

      {isLoading ? <Spinner /> : plans.length === 0 ? (
        <EmptyState icon={<MapIcon size={28} />}
          title={traducir('performancereviews.sin_planes_aun')}
          description={t('pagina_perf.tras_una_campana_360_crea_un')} />
      ) : (
        <div className="ds-stack-sm">
          {plans.map(p => {
            const cfg = PLAN_STATUS_CFG[p.status as keyof typeof PLAN_STATUS_CFG] || PLAN_STATUS_CFG.draft
            return (
              // Auditoría 2026-08 (P1-6): tarjeta clicable sin vía de teclado.
              <div key={p.id} className="ds-card perf-box-34" onClick={() => setOpenPlanId(p.id)}
                role="button"
                tabIndex={0}
                aria-label={t('pagina_perf.abrir_plan', { title: p.title })}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpenPlanId(p.id) }
                }}
               >
                <div className="ds-row-between">
                  <div className="performance-reviews-page-e8">
                    <div className="performance-reviews-page-e17">
                      {p.title}
                    </div>
                    <div className="ds-row-wrap perf-box-4">
                      <span className="perf-label-11 performance-reviews-page-e2" style={{ '--performance-reviews-page-color': cfg.color } as CSSProperties}>
                        {t(cfg.label)}
                      </span>
                      <span className="ds-muted u-xs">
                        {t('pagina_perf.n_objetivos', { n: (p.goals || []).length })}
                      </span>
                      {p.target_date && (
                        <span className="ds-muted u-xs">
                          {t('pagina_perf.objetivo')}{' '}{p.target_date}
                        </span>
                      )}
                      {p.next_review_at && (
                        <span className="perf-label-12">
                          {traducir('performancereviews.proxima_revision')} {p.next_review_at}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="perf-input-2">
                    <ScoreBar value={p.progress_pct / 20} max={5} />
                    <div className={`perf-box-33 ${p.progress_pct >= 70 ? 'performa-sx7' : 'performa-sx11'}`}>
                      {p.progress_pct}%
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {creating && (
        <NewDevPlanModal subjectId={subjectId} onClose={() => setCreating(false)} />
      )}
      {openPlanId && (
        <DevPlanModal planId={openPlanId} onClose={() => setOpenPlanId(null)} />
      )}
    </div>
  )
}

function NewDevPlanModal({ subjectId, onClose }: { subjectId?: string; onClose: () => void }) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<{
    title: string; summary: string; target_date: string; next_review_at: string
    goals: { title: string; due_date: string }[]
  }>({
    title: '', summary: '', target_date: '', next_review_at: '',
    goals: [{ title: '', due_date: '' }],
  })

  const setGoal = (idx: number, key: string, value: string) => setForm(f => ({
    ...f, goals: f.goals.map((g, i) => i === idx ? { ...g, [key]: value } : g),
  }))
  const addRow = () => setForm(f => ({ ...f, goals: [...f.goals, { title: '', due_date: '' }] }))
  const removeRow = (idx: number) => setForm(f => ({ ...f, goals: f.goals.filter((_, i) => i !== idx) }))

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => performanceApi.createPlan({
      subject_id: subjectId,
      title: form.title.trim(),
      summary: form.summary.trim() || null,
      target_date: form.target_date || null,
      next_review_at: form.next_review_at || null,
      goals: form.goals.filter(g => g.title.trim()).map(g => ({
        title: g.title.trim(), due_date: g.due_date || null,
      })),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dev-plans', subjectId] })
      toast.success(t('pagina_perf.plan_creado'))
      onClose()
    },
    onError: (e: unknown) => { campos.recoger(e); toast.error(extractErr(e, t('pagina_perf.error_al_crear_plan'))) },
  })

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <MapIcon size={16} /> {traducir('performancereviews.nuevo_plan_de_desarrollo')}
      </span>}
      width={560}>
      <div className="ds-stack">
        <div className="ds-field">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{traducir('performancereviews.titulo')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title}
            onChange={e => { campos.limpiar('title'); setForm(f => ({ ...f, title: e.target.value })) }}
            className="ds-input" placeholder={traducir('performancereviews.ej_mejora_comunicacion_2026')} autoFocus />{msg('title')}
        </div>
        <div className="ds-field">
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">{t('pagina_perf.resumen_contexto')}</label>
          <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.summary}
            onChange={e => { campos.limpiar('summary'); setForm(f => ({ ...f, summary: e.target.value })) }}
            rows={3} className="ds-input perf-input"
            placeholder={traducir('performancereviews.resumen_del_360_y_areas_de_mejora')} />{msg('summary')}
        </div>
        <div className="performance-reviews-page-e15">
          <div className="ds-field">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="ds-field__label">{t('pagina_perf.fecha_objetivo')}</label>
            <DateInput id={`${idCampo}-3`} value={form.target_date}
              onChange={e => { campos.limpiar('target_date'); setForm(f => ({ ...f, target_date: e.target.value })) }}
              className="ds-input" />{msg('target_date')}
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="ds-field__label">{traducir('performancereviews.proxima_revision_2')}</label>
            <DateInput id={`${idCampo}-4`} value={form.next_review_at}
              onChange={e => { campos.limpiar('next_review_at'); setForm(f => ({ ...f, next_review_at: e.target.value })) }}
              className="ds-input" />{msg('next_review_at')}
          </div>
        </div>
        <div className="ds-field" role="group" aria-labelledby={`${idCampo}-objetivos-et`}>
          <div id={`${idCampo}-objetivos-et`} className="ds-field__label">
            <Flag size={11} className="perf-box-38" />{' '}{t('pagina_perf.objetivos_iniciales')}
          </div>
          {form.goals.map((g, idx) => (
            <div key={idx} className="perf-row-15">
              <input aria-label={t('pagina_perf.objetivo_2', { v1: idx + 1 })} value={g.title}
                onChange={e => setGoal(idx, 'title', e.target.value)}
                className="ds-input u-flex1" placeholder={t('pagina_perf.objetivo_2', { v1: idx + 1 })}
                 />
              <DateInput value={g.due_date}
                onChange={e => setGoal(idx, 'due_date', e.target.value)}
                className="ds-input perf-box-39" />
              {form.goals.length > 1 && (
                <Button size="sm" variant="ghost" onClick={() => removeRow(idx)}
                  aria-label={t('pagina_perf.quitar')}>
                  <X size={12} />
                </Button>
              )}
            </div>
          ))}
          <Button size="sm" variant="ghost" onClick={addRow}>
            <Plus size={11} /> {traducir('performancereviews.anadir_objetivo')}
          </Button>
        </div>
        <div className="performance-reviews-page-e12">
          <Button variant="secondary" onClick={onClose}>{t('pagina_perf.cancelar')}</Button>
          <Button onClick={() => mutate()} disabled={!form.title.trim() || isPending}
            loading={isPending}>
            <Save size={13} />{' '}{t('pagina_perf.crear_plan')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function DevPlanModal({ planId, onClose }: { planId: string; onClose: () => void }) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [newGoal, setNewGoal] = useState('')

  const { data: plan, isLoading } = useQuery<DevPlan>({
    queryKey: ['dev-plan', planId],
    queryFn: () => performanceApi.getPlan(planId).then(r => r.data),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['dev-plan', planId] })
    if (plan?.subject_id) qc.invalidateQueries({ queryKey: ['dev-plans', plan.subject_id] })
  }

  const { mutate: setStatus } = useMutation({
    mutationFn: (status: string) => performanceApi.updatePlan(planId, { status }),
    onSuccess: () => { invalidate(); toast.success(t('pagina_perf.estado_actualizado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: setGoalStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => performanceApi.updateGoal(id, { status }),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: addG } = useMutation({
    mutationFn: (title: string) => performanceApi.addGoal(planId, { title }),
    onSuccess: () => { invalidate(); setNewGoal('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: removeG } = useMutation({
    mutationFn: (id: string) => performanceApi.deleteGoal(id),
    onSuccess: invalidate,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading || !plan) return (
    <Modal open onClose={onClose} title={t('pagina_perf.plan')} width={640}><Spinner /></Modal>
  )

  return (
    <Modal open onClose={onClose}
      title={<span className="performance-reviews-page-e7">
        <MapIcon size={16} /> {plan.title}
      </span>}
      subtitle={t('pagina_perf.completado_2', { subject_name: plan.subject_name, progress_pct: plan.progress_pct })}
      width={680}>
      <div className="ds-stack perf-box-3">
        <div className="ds-row-wrap">
          {Object.entries(PLAN_STATUS_CFG).map(([k, v]) => (
            <Pulsable key={k} onClick={() => setStatus(k)}
              className={`perf-btn-3 performa-sx4 ${plan.status === k ? 'performa-sx5' : 'performa-sx6'} performance-reviews-page-e3`} style={{ '--performance-reviews-page-border': `1px solid ${plan.status === k ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
              {t(v.label)}
            </Pulsable>
          ))}
        </div>

        {plan.summary && (
          <div className="ds-card--inset perf-box-14">
            <div className="ds-eyebrow">{t('pagina_perf.contexto')}</div>
            <div className="u-text2-sm">
              {plan.summary}
            </div>
          </div>
        )}

        <div className="ds-card--inset perf-box-14">
          <div className="ds-eyebrow">{t('pagina_perf.objetivos')}</div>
          {plan.goals.length === 0 ? (
            <div className="ds-muted u-sm">{traducir('performancereviews.sin_objetivos_aun')}</div>
          ) : (
            <div className="ds-stack-sm">
              {plan.goals.map(g => {
                return (
                  <div key={g.id} className="ds-row-between perf-card-3">
                    <div className="performance-reviews-page-e8">
                      <div className="performance-reviews-page-e9">
                        {g.title}
                      </div>
                      <div className="ds-muted u-xs">
                        {g.due_date && t('pagina_perf.vence', { due_date: fmtDate(g.due_date) })}
                        {g.completed_at && t('pagina_perf.completado_3', { completed_at: fmtDate(g.completed_at) })}
                      </div>
                    </div>
                    <Select suelto placeholder={false} value={g.status}
                      onChange={e => setGoalStatus({ id: g.id, status: e.target.value })} className="perf-input-3">
                      {Object.entries(GOAL_STATUS_CFG).map(([k, v]) => (
                        <option key={k} value={k}>{t(v.label)}</option>
                      ))}
                    </Select>
                    <Button size="sm" variant="ghost"
                      onClick={async () => { if (await confirmar({ message: t('pagina_perf.eliminar_objetivo'), danger: true, confirmLabel: t('pagina_perf.eliminar') })) removeG(g.id) }}
                      aria-label={t('pagina_perf.eliminar')}>
                      <Trash2 size={11} />
                    </Button>
                  </div>
                )
              })}
            </div>
          )}
          <div className="perf-row-16">
            <input aria-label={traducir('performancereviews.anadir_nuevo_objetivo_y_pulsar_enter')} value={newGoal}
              onChange={e => setNewGoal(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && newGoal.trim() && addG(newGoal.trim())}
              className="ds-input u-flex1"
              placeholder={traducir('performancereviews.anadir_nuevo_objetivo_y_pulsar_enter')} />
            <Button size="sm" onClick={() => newGoal.trim() && addG(newGoal.trim())}
              disabled={!newGoal.trim()}>
              <Plus size={11} /> {traducir('performancereviews.anadir')}
            </Button>
          </div>
        </div>

        <div className="u-row-end">
          <Button variant="secondary" onClick={onClose}>
            <X size={13} />{' '}{t('pagina_perf.cerrar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────
export default function PerformanceReviewsPage() {
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user } = useAuth()
  const isManager = ['admin', 'hr'].includes(user?.role ?? '')

  const [tab, setTab] = useState('cycles')

  // Estado de modales agrupado. Cada propiedad es independiente y se asigna
  // mediante helpers locales para mantener una API similar a setState.
  const [modals, setModals] = useState<{
    showNewCycle: boolean
    editingReview: Review | null
    assigningCycle: Cycle | null
    campaigningCycle: Cycle | null
    openDashboardId: string | null
    historySubject: { id?: string; name?: string } | null
  }>({
    showNewCycle:     false,
    editingReview:    null,
    assigningCycle:   null,
    campaigningCycle: null,
    openDashboardId:  null,
    historySubject:   null,  // {id, name}
  })
  const setModal = (key: string, value: unknown) => setModals(m => ({ ...m, [key]: value }))
  const setShowNewCycle     = (v: boolean) => setModal('showNewCycle', v)
  const setEditingReview    = (v: Review | null) => setModal('editingReview', v)
  const setAssigningCycle   = (v: Cycle | null) => setModal('assigningCycle', v)
  const setCampaigningCycle = (v: Cycle | null) => setModal('campaigningCycle', v)
  const setOpenDashboardId  = (v: string | null) => setModal('openDashboardId', v)
  const setHistorySubject   = (v: { id?: string; name?: string } | null) => setModal('historySubject', v)
  const {
    showNewCycle, editingReview, assigningCycle,
    campaigningCycle, openDashboardId, historySubject,
  } = modals

  const { data: cycles = [], isLoading: loadingCycles } = useQuery<Cycle[]>({
    queryKey: ['perf-cycles'],
    queryFn: () => performanceApi.cycles().then(r => r.data).catch(() => []),
  })
  const { data: myReviews = [], isLoading: loadingMine } = useQuery<Review[]>({
    queryKey: ['perf-my-reviews'],
    queryFn: () => performanceApi.myReviews().then(r => r.data).catch(() => []),
  })

  const { mutate: activate } = useMutation({
    mutationFn: (id: string) => performanceApi.activateCycle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-cycles'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: closeCycle } = useMutation({
    mutationFn: (id: string) => performanceApi.closeCycle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['perf-cycles'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  // 16-11-2026: título = el del menú ("Evaluaciones de desempeño"); pestañas
  // con Tabs del kit (antes un control segmentado relleno propio); vacíos con
  // EmptyState e icono de 28 px como el resto; KPIs del panel con KpiCard.
  return (
    <Page
      icon={<Star size={18} />}
      title={t('nav.performance_reviews')}
      subtitle={t('performance.subtitle') || t('pagina_perf.ciclos_de_evaluacion_360_autoevaluacion_par')}
      rightActions={
        tab === 'cycles' && (
          <span title={!isManager ? t(NO_PERMISSION_TIP) : undefined} className="perf-row-2">
            <Button icon={<Plus size={14} />} onClick={() => setShowNewCycle(true)} disabled={!isManager}>
              {traducir('performancereviews.nuevo_ciclo')}
            </Button>
          </span>
        )
      }
    >
      <Tabs
        ariaLabel={t('nav.performance_reviews')}
        active={tab}
        onChange={setTab}
        items={[
          { id: 'cycles',  label: t('pagina_perf.ciclos'), icon: <ListChecks size={14} /> },
          { id: 'pending', label: t('pagina_perf.mis_evaluaciones'), icon: <Clock size={14} />, count: myReviews.length || undefined },
          { id: 'plans',   label: t('pagina_perf.mi_plan'), icon: <MapIcon size={14} /> },
          ...(isManager ? [{ id: 'kpis', label: t('pagina_perf.panel_hr'), icon: <Activity size={14} /> }] : []),
        ]}
      />

      {/* Panel KPIs (solo admin/HR) */}
      {tab === 'kpis' && isManager && <KPIDashboardTab cycles={cycles} />}

      {/* Plan de desarrollo (todos los usuarios ven el suyo) */}
      {tab === 'plans' && user && (
        <DevPlansTab subjectId={user.id} subjectName={user.full_name || t('pagina_perf.mi_plan')} />
      )}

      {/* Ciclos */}
      {tab === 'cycles' && (
        loadingCycles ? <Spinner /> : cycles.length === 0 ? (
          <EmptyState icon={<Star size={28} />}
            title={traducir('performancereviews.sin_ciclos_de_evaluacion')}
            description={isManager
              ? t('pagina_perf.crea_el_primer_ciclo_para_iniciar')
              : t('pagina_perf.cuando_rr_hh_inicie_un_ciclo')} />
        ) : (
          <div data-export-table="performance-cycles-list" className="ds-stack">
            {cycles.map(c => (
              <CycleCard key={c.id} cycle={c} isManager={isManager}
                onActivate={activate}
                onCloseCycle={closeCycle}
                onAssign={setAssigningCycle}
                onCreateCampaign={setCampaigningCycle}
                onOpenDashboard={setOpenDashboardId}
              />
            ))}
          </div>
        )
      )}

      {/* Mis evaluaciones pendientes */}
      {tab === 'pending' && (
        <>
          {/* Acceso a mi evolución 360° (siempre visible en la pestaña) */}
          <div className="ds-card--inset perf-row-17">
            <div>
              <div className="performance-reviews-page-e16">
                {traducir('performancereviews.mi_evolucion_360')}
              </div>
              <div className="ds-muted u-xs">
                {traducir('performancereviews.compara_tus_puntuaciones_others_vs_self_a')}
              </div>
            </div>
            <Button variant="secondary" size="sm"
              onClick={() => setHistorySubject({ id: user?.id, name: user?.full_name ?? undefined })}>
              <TrendingUp size={12} /> {traducir('performancereviews.ver_evolucion')}
            </Button>
          </div>

          {loadingMine ? <Spinner /> : myReviews.length === 0 ? (
            <EmptyState icon={<CheckCircle2 size={28} />}
              title={traducir('performancereviews.sin_evaluaciones_pendientes')}
              description={t('pagina_perf.cuando_alguien_te_asigne_una_evaluacion')} />
          ) : (
          <div data-export-table="performance-pending-list" className="ds-stack-sm">
            {myReviews.map(r => {
              const tipo = TYPE_BY_ID[r.review_type] || TYPE_BY_ID.peer
              const TypeIcon = tipo.Icon
              return (
                <div key={r.id} className="ds-card perf-box-36">
                  <div className="perf-row-18">
                    <TypeIcon size={16} />
                  </div>
                  <div className="u-flex1-min0">
                    <div className="perf-box-37">
                      {t('pagina_perf.evaluar_a')} {r.reviewee_name}
                    </div>
                    <div className="ds-muted">{t(tipo.label)} · {t(tipo.help)}</div>
                  </div>
                  <Button onClick={() => setEditingReview(r)}>{traducir('performancereviews.rellenar_evaluacion')}</Button>
                </div>
              )
            })}
          </div>
          )}
        </>
      )}

      {showNewCycle && <NewCycleModal existingCycles={cycles} onClose={() => setShowNewCycle(false)} />}
      {editingReview && <ReviewForm review={editingReview} onClose={() => setEditingReview(null)} />}
      {assigningCycle && <AssignReviewModal cycle={assigningCycle} onClose={() => setAssigningCycle(null)} />}
      {campaigningCycle && (
        <New360CampaignModal cycle={campaigningCycle}
          onClose={() => setCampaigningCycle(null)} />
      )}
      {openDashboardId && (
        <Campaign360Dashboard campaignId={openDashboardId}
          onClose={() => setOpenDashboardId(null)}
          onOpenHistory={(id, name) => setHistorySubject({ id, name })} />
      )}
      {historySubject && (
        <History360Modal subjectId={historySubject.id}
          subjectName={historySubject.name}
          onClose={() => setHistorySubject(null)} />
      )}
    </Page>
  )
}
