/**
 * Planes de desarrollo: pestaña, alta y detalle.
 * Troceado de PerformanceReviewsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { type CSSProperties, useState, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { performanceApi } from '../../services/api'
import { Button, Modal, Pulsable, Select, Spinner, EmptyState, useErroresDeCampo, Textarea, Input, IconButton } from '../../components/ui'
import { Plus, Save, Trash2, X, Map as MapIcon, Flag } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import DateInput from '../../components/ui/DateInput'
import { type DevPlan, ScoreBar } from './compartido'

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

export function DevPlansTab({ subjectId, subjectName }: { subjectId?: string; subjectName?: string }) {
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
          <Input label={traducir('performancereviews.titulo')} id={`${idCampo}-1`} value={form.title} onChange={e => { campos.limpiar('title'); setForm(f => ({ ...f, title: e.target.value })) }} placeholder={traducir('performancereviews.ej_mejora_comunicacion_2026')} autoFocus />{msg('title')}
        </div>
        <div className="ds-field">
          <Textarea label={t('pagina_perf.resumen_contexto')} id={`${idCampo}-2`} value={form.summary} onChange={e => { campos.limpiar('summary'); setForm(f => ({ ...f, summary: e.target.value })) }} rows={3} placeholder={traducir('performancereviews.resumen_del_360_y_areas_de_mejora')} />{msg('summary')}
        </div>
        <div className="performance-reviews-page-e15">
          <div className="ds-field">
            <DateInput label={t('pagina_perf.fecha_objetivo')} id={`${idCampo}-3`} value={form.target_date}
              onChange={e => { campos.limpiar('target_date'); setForm(f => ({ ...f, target_date: e.target.value })) }} />{msg('target_date')}
          </div>
          <div className="ds-field">
            <DateInput label={traducir('performancereviews.proxima_revision_2')} id={`${idCampo}-4`} value={form.next_review_at}
              onChange={e => { campos.limpiar('next_review_at'); setForm(f => ({ ...f, next_review_at: e.target.value })) }} />{msg('next_review_at')}
          </div>
        </div>
        <div className="ds-field" role="group" aria-labelledby={`${idCampo}-objetivos-et`}>
          <div id={`${idCampo}-objetivos-et`} className="ds-field__label">
            <Flag size={11} className="perf-box-38" />{' '}{t('pagina_perf.objetivos_iniciales')}
          </div>
          {form.goals.map((g, idx) => (
            <div key={idx} className="perf-row-15">
              <Input aria-label={t('pagina_perf.objetivo_2', { v1: idx + 1 })} value={g.title}
                onChange={e => setGoal(idx, 'title', e.target.value)}
                inputClassName="u-flex1" placeholder={t('pagina_perf.objetivo_2', { v1: idx + 1 })}
                 />
              <DateInput value={g.due_date}
                onChange={e => setGoal(idx, 'due_date', e.target.value)}
                className="ds-input perf-box-39" />
              {form.goals.length > 1 && (
                <IconButton variante="caja" tono="peligro" onClick={() => removeRow(idx)}
                  ariaLabel={t('pagina_perf.quitar')}>
                  <X size={12} />
                </IconButton>
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
                    <IconButton variante="caja" tono="peligro"
                      onClick={async () => { if (await confirmar({ message: t('pagina_perf.eliminar_objetivo'), danger: true, confirmLabel: t('pagina_perf.eliminar') })) removeG(g.id) }}
                      ariaLabel={t('pagina_perf.eliminar')}>
                      <Trash2 size={11} />
                    </IconButton>
                  </div>
                )
              })}
            </div>
          )}
          <div className="perf-row-16">
            <Input aria-label={traducir('performancereviews.anadir_nuevo_objetivo_y_pulsar_enter')} value={newGoal}
              onChange={e => setNewGoal(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && newGoal.trim() && addG(newGoal.trim())}
              inputClassName="u-flex1"
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
