/**
 * Formulario de una evaluación y modal para asignar evaluaciones.
 * Troceado de PerformanceReviewsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { type CSSProperties, useState, useEffect, useId } from 'react'
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { performanceApi, usersApi } from '../../services/api'
import { Button, Modal, Pulsable, Select, Spinner, useErroresDeCampo, Textarea, Input } from '../../components/ui'
import { UserPlus, Save, Send, AlertCircle } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'
import {
  type AnswerMap,
  claveDeBloqueo,
  type Cycle,
  type EligiblePool,
  isRatingKind,
  type Question,
  ratingMax,
  ratingMin,
  type Review,
  REVIEW_TYPES,
  TYPE_BY_ID,
} from './compartido'

// ── ReviewForm: rellenar una evaluación dinámica según preguntas del ciclo ─
export function ReviewForm({ review, onClose }: { review: Review; onClose: () => void }) {
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
                  <Textarea id={`${idCampo}-${q.id}`} aria-labelledby={`${idCampo}-${q.id}-et`} value={answers[q.key] || ''} onChange={e => setAnswers(s => ({ ...s, [q.key]: e.target.value }))} rows={3} inputClassName="perf-input" />
                ) : (
                  <Input id={`${idCampo}-${q.id}`} aria-labelledby={`${idCampo}-${q.id}-et`} type="text" value={answers[q.key] || ''} onChange={e => setAnswers(s => ({ ...s, [q.key]: e.target.value }))} />
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
export function AssignReviewModal({ cycle, onClose }: { cycle: Cycle; onClose: () => void }) {
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
  // 23-11-2026: el servidor manda el motivo en castellano suelto; el texto sale de claves por tipo.
  const blockedReason = currentTypePool?.reason_blocked ? t(claveDeBloqueo(form.review_type)) : null

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
          <Select label={t('pagina_perf.persona_evaluada')} placeholder={false} id={`${idCampo}-1`} value={form.reviewee_id}
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
              const tip = disabled ? (pool?.reason_blocked ? t(claveDeBloqueo(id)) : t('pagina_perf.no_hay_evaluadores_elegibles')) : undefined
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
            <Select label={t('pagina_perf.evaluador')} placeholder={false} id={`${idCampo}-2`} value={form.reviewer_id}
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
