/**
 * ChangeRolloutPanel — planes de despliegue por fases de un cambio.
 *
 * Backend endpoints:
 *   GET  /sd/changes/{cr_id}/rollout-plans
 *   POST /sd/changes/{cr_id}/rollout-plans
 *     body: { title, rollout_phases: [{name, description, target_pct, gate_criteria, duration_minutes}], rollback_steps, ... }
 *   POST /sd/changes/rollout-plans/{plan_id}/approve
 *   POST /sd/changes/rollout-plans/{plan_id}/advance-phase   { phase_notes }
 *   POST /sd/changes/{cr_id}/rollout-plans/{plan_id}/simulate
 *   POST /sd/changes/{cr_id}/rollback                         { reason }
 *
 * 16-11-2026 (pasada de diseño): todo texto pasa por t() en es/en/zh (antes
 * estados, estrategias, fases, avisos y diálogos fijos en castellano, y claves
 * `sd.rollout.*` que no existían); estados con <StatusBadge> y valores crudos
 * (`ready`, `high`, `required`) traducidos; seleccionado en --accent (antes
 * --purple) y sin cambiar el borde con JS; campos con `ds-input`; vacíos con
 * icono lucide; fechas con el formateador de la app; sin «🎉».
 */
import { type CSSProperties, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { changeRolloutApi } from '../../services/api'
import type { FaseDeDespliegue, PlanDeDespliegue, SimulacionDeDespliegue } from '../../services/api/tipos-cambios'
import { useAppT } from '../../i18n/AppLangContext'
import { GitBranch, ChevronRight, CheckCircle, AlertTriangle, RotateCcw, Play, Plus, Search, Check, X } from 'lucide-react'
import { Card, Button, Pulsable, Select, Spinner, EmptyState, StatusBadge, Input } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { pedirTexto } from '../../context/ConfirmContext'
import { fmtDate } from '../../utils/helpers'
import { usePropuestas, type Propuestas } from '../../hooks/useOrgSettings'
import './ChangeRolloutPanel.css'

/** Fase que se manda al crear el plan (`RolloutPhaseIn` en endpoints/service_desk/change_rollout.py). */
type FaseNueva = Pick<FaseDeDespliegue, 'name' | 'description' | 'target_pct' | 'duration_minutes' | 'gate_criteria'>

type RolloutPlan = PlanDeDespliegue

interface RolloutForm {
  change_request_id: string
  strategy: string
  phases: number
  name: string
}

type SimulateResult = SimulacionDeDespliegue

type ApiError = { response?: { data?: { detail?: string } } }

type T = (clave: string, params?: Record<string, unknown> | string) => string

const STATUS_KIND: Record<string, StatusBadgeKind> = {
  draft: 'neutral',
  approved: 'success',
  in_progress: 'accent',
  rolled_back: 'danger',
  completed: 'success',
}

const PHASE_KIND: Record<string, StatusBadgeKind> = { completed: 'success', ready: 'accent', pending: 'neutral' }

const RISK_KIND: Record<string, StatusBadgeKind> = { low: 'success', medium: 'warning', high: 'orange', critical: 'danger' }

const ESTRATEGIAS = ['canary', 'blue_green', 'rolling', 'big_bang'] as const

/** Etiqueta traducida de un valor del servidor; si es uno nuevo, el valor tal cual. */
function etiqueta(t: T, prefijo: string, valor: string) {
  return t(`changerollout.${prefijo}_${valor}`, valor)
}

/** Rampa canaria y minutos de la empresa (`usePropuestas`). */
type Canario = Pick<Propuestas, 'change_canary_ramp_pct' | 'change_canary_minutes'>

/**
 * % y minutos de cada fase canaria (19-11-2026: rampa y minutos de la empresa,
 * `CHANGE_CANARY_*` en Configuración → Service desk; antes 1/5/25/50/100 y
 * 30/45/60 fijos aquí). La rampa se recorta a n-1 fases (mínimo dos) y se cierra
 * con un 100 %; la primera fase dura `first`, la última `last` y el resto `step`.
 */
export function fasesCanarias(canario: Canario, total: number | string): { pct: number; minutos: number }[] {
  const n = Math.max(1, Math.min(10, Number(total) || 3))
  const { first, step, last } = canario.change_canary_minutes
  const slice = canario.change_canary_ramp_pct.slice(0, Math.max(2, n - 1)).concat([100]).slice(0, n)
  return slice.map((pct, i) => ({ pct, minutos: i === 0 ? first : i === slice.length - 1 ? last : step }))
}

/**
 * Fases canónicas según la estrategia y el número de fases. Los nombres se
 * guardan con el plan, así que salen en el idioma de quien lo crea.
 */
function buildPhases(t: T, strategy: string, total: number | string, canario: Canario): FaseNueva[] {
  const n = Math.max(1, Math.min(10, Number(total) || 3))
  switch (strategy) {
    case 'canary': {
      const fases = fasesCanarias(canario, n)
      return fases.map(({ pct, minutos }, i) => ({
        name: t('changerollout.fase_canario', { pct }),
        description: i === 0 ? t('changerollout.canario_inicial') : i === fases.length - 1 ? t('changerollout.despliegue_completo') : t('changerollout.ampliacion', { pct }),
        target_pct: pct,
        duration_minutes: minutos,
        gate_criteria: i === 0 ? [t('changerollout.criterio_sin_errores'), t('changerollout.criterio_latencia')] : [],
      }))
    }
    case 'blue_green':
      return [
        { name: t('changerollout.preparar_verde'), description: t('changerollout.preparar_verde_desc'), target_pct: 100, duration_minutes: 30, gate_criteria: [t('changerollout.criterio_pruebas_basicas')] },
        { name: t('changerollout.conmutacion'), description: t('changerollout.conmutacion_desc'), target_pct: 100, duration_minutes: 15, gate_criteria: [t('changerollout.criterio_salud')] },
        { name: t('changerollout.retirar_azul'), description: t('changerollout.retirar_azul_desc'), target_pct: 100, duration_minutes: 30, gate_criteria: [t('changerollout.criterio_sin_vueltas')] },
      ].slice(0, n)
    case 'rolling': {
      const buckets = Array.from({ length: n }, (_, i) => Math.round(((i + 1) / n) * 100))
      return buckets.map((pct, i) => ({
        name: t('changerollout.tanda_n', { i: i + 1, n }),
        description: t('changerollout.tanda_desc', { pct }),
        target_pct: pct,
        duration_minutes: 30,
        gate_criteria: [],
      }))
    }
    case 'big_bang':
    default:
      return [
        { name: t('changerollout.estrategia_big_bang'), description: t('changerollout.todo_desc'), target_pct: 100, duration_minutes: 30, gate_criteria: [t('changerollout.criterio_pruebas_previas')] },
      ]
  }
}

export default function ChangeRolloutPanel() {
  const t = useAppT() as T
  const toast = useToast()
  const qc = useQueryClient()
  const canario = usePropuestas()

  const [selectedId, setSelectedId] = useState<string | number | null>(null)
  const [showCreate, setShowCreate] = useState<boolean>(false)
  const [changeRequestFilter, setChangeRequestFilter] = useState<string>('')
  const [form, setForm] = useState<RolloutForm>({ change_request_id: '', strategy: 'canary', phases: 3, name: '' })
  const [simulate, setSimulate] = useState<SimulateResult | null>(null)

  // El interceptor ya desenvuelve `{items, meta}`: `r.data` es el array (antes se leía
  // `.items` sobre él y la lista salía siempre vacía).
  const { data: plans = [], isLoading } = useQuery<RolloutPlan[]>({
    queryKey: ['change-rollout-plans', changeRequestFilter],
    queryFn: () => changeRolloutApi.listPlans(changeRequestFilter).then(r => r.data),
    enabled: Boolean(changeRequestFilter.trim()),
  })
  const selectedPlan = plans.find(p => p.id === selectedId)

  const createMutation = useMutation({
    mutationFn: (data: RolloutForm) => {
      const phases = buildPhases(t, data.strategy, data.phases, canario)
      return changeRolloutApi.createPlan(data.change_request_id, {
        title: data.name?.trim() || t('changerollout.plan_x', { estrategia: etiqueta(t, 'estrategia', data.strategy) }),
        rollout_phases: phases,
        rollback_steps: [
          t('changerollout.paso_detener'),
          t('changerollout.paso_restaurar'),
          t('changerollout.paso_avisar'),
        ],
      }).then(r => r.data)
    },
    onSuccess: (_res, data) => {
      toast.success(t('changerollout.plan_de_rollout_creado'))
      qc.invalidateQueries({ queryKey: ['change-rollout-plans'] })
      setChangeRequestFilter(data.change_request_id)
      setShowCreate(false)
      setForm({ change_request_id: '', strategy: 'canary', phases: 3, name: '' })
    },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || t('changerollout.error_crear')),
  })

  const approveMutation = useMutation({
    mutationFn: (id: string | number) => changeRolloutApi.approvePlan(id).then(r => r.data),
    onSuccess: () => {
      toast.success(t('changerollout.plan_aprobado'))
      qc.invalidateQueries({ queryKey: ['change-rollout-plans'] })
    },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || t('changerollout.error_aprobar')),
  })

  const advanceMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string | number; notes: string }) =>
      changeRolloutApi.advancePhase(id, { phase_notes: notes || null }).then(r => r.data),
    onSuccess: (data) => {
      toast.success(data.status === 'completed' ? t('changerollout.despliegue_terminado') : t('changerollout.fase_avanzada'))
      qc.invalidateQueries({ queryKey: ['change-rollout-plans'] })
    },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || t('changerollout.error_avanzar')),
  })

  const rollbackMutation = useMutation({
    mutationFn: ({ changeId, reason }: { changeId: string; reason: string }) =>
      changeRolloutApi.rollback(changeId, { reason }).then(r => r.data),
    onSuccess: () => {
      toast.success(t('changerollout.rollback_ejecutado'))
      qc.invalidateQueries({ queryKey: ['change-rollout-plans'] })
    },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || t('changerollout.error_vuelta')),
  })

  const handleSimulate = async (plan: RolloutPlan) => {
    try {
      const res = await changeRolloutApi.simulatePlan(plan.change_request_id, plan.id)
      setSimulate(res.data.simulation)
    } catch (e: unknown) {
      toast.error((e as ApiError)?.response?.data?.detail || t('changerollout.error_simular'))
    }
  }

  const handleAdvance = async (id: string | number) => {
    const notes = await pedirTexto({ title: t('changerollout.avanzar_fase'), message: t('changerollout.avanzar_msg'), label: t('changerollout.notas_opcional'), multiline: true, confirmLabel: t('changerollout.avanzar') })
    if (notes === null) return
    advanceMutation.mutate({ id, notes: notes.trim() })
  }

  const handleRollback = async (changeId: string) => {
    const reason = await pedirTexto({ title: t('changerollout.vuelta_titulo'), message: t('changerollout.vuelta_msg'), label: t('changerollout.vuelta_motivo'), required: true, multiline: true, danger: true, confirmLabel: t('changerollout.vuelta_atras') })
    if (!reason || !reason.trim()) return
    rollbackMutation.mutate({ changeId, reason: reason.trim() })
  }

  const vistaPrevia = buildPhases(t, form.strategy, form.phases, canario).map(p => `${p.target_pct}%`).join(' → ')

  return (
    <Card className="changero-sx1">
      <div className="chropa-row-1">
        <div className="u-row-center-8">
          <GitBranch size={18} className="changero-sx2" aria-hidden />
          <h2 className="chropa-box-1">{t('changerollout.titulo')}</h2>
        </div>
        <Button onClick={() => setShowCreate(v => !v)} variant={showCreate ? 'secondary' : 'primary'} icon={showCreate ? <X size={14} /> : <Plus size={14} />}>
          {showCreate ? t('common.close') : t('changerollout.nuevo_plan')}
        </Button>
      </div>

      <div className="chropa-filtro">
        <label className="chropa-fieldlabel" htmlFor="chropa-filtro">{t('changerollout.filtrar_por_change_request')}</label>
        <Input id="chropa-filtro" type="text" placeholder={t('changerollout.id_cambio')} value={changeRequestFilter} onChange={e => setChangeRequestFilter(e.target.value)} />
      </div>

      {showCreate && (
        <div className="chropa-box-8">
          <div className="chropa-fieldlabel">{t('changerollout.nuevo_plan_titulo')}</div>
          <div className="chropa-grid-1">
            <input aria-label={t('changerollout.id_cambio')}
              type="text"
              placeholder={t('changerollout.id_cambio')}
              value={form.change_request_id}
              onChange={e => setForm(f => ({ ...f, change_request_id: e.target.value }))}
              className="ds-input chropa-col-full"
            />
            <Input aria-label={t('changerollout.nombre_del_plan_opcional')} type="text" placeholder={t('changerollout.nombre_del_plan_opcional')} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <Select
              suelto
              placeholder={false}
              aria-label={t('changerollout.estrategia')}
              value={form.strategy}
              onChange={e => setForm(f => ({ ...f, strategy: e.target.value }))}
            >
              {ESTRATEGIAS.map(id => (
                <option key={id} value={id}>{etiqueta(t, 'estrategia', id)}</option>
              ))}
            </Select>
            <div className="chropa-row-2">
              <label className="u-text2-xs" htmlFor="chropa-fases">{t('changerollout.fases')}</label>
              <input
                id="chropa-fases"
                type="number" min={1} max={10}
                value={form.phases}
                onChange={e => setForm(f => ({ ...f, phases: Number(e.target.value) }))}
                className="ds-input chropa-fases"
              />
              <span className="u-text2-xs">{t('changerollout.vista_previa')} {vistaPrevia}</span>
            </div>
          </div>
          <div className="u-row-8">
            <Button
              onClick={() => createMutation.mutate(form)}
              disabled={!form.change_request_id.trim() || createMutation.isPending}
              loading={createMutation.isPending}
            >
              {t('changerollout.crear_plan')}
            </Button>
            <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('common.cancel')}</Button>
          </div>
        </div>
      )}

      <div className="chropa-grid-2">
        {/* Plans list */}
        <div>
          <div className="chropa-fieldlabel">{t('changerollout.planes')}</div>
          {!changeRequestFilter.trim() ? (
            <EmptyState icon={<Search size={28} />} title={t('changerollout.filtra_por_change_request_id')} description={t('changerollout.indica_el_id_del_change_request_para')} />
          ) : isLoading ? (
            <div className="chropa-row-3"><Spinner /></div>
          ) : !plans.length ? (
            <EmptyState icon={<GitBranch size={28} />} title={t('changerollout.sin_planes')} description={t('changerollout.sin_planes_desc')} action={<Button icon={<Plus size={14} />} onClick={() => { setForm(f => ({ ...f, change_request_id: changeRequestFilter.trim() })); setShowCreate(true) }}>{t('changerollout.nuevo_plan')}</Button>} />
          ) : (
            <div className="u-stack-6">
              {plans.map(plan => {
                const status = plan.status || 'draft'
                const isSel = selectedId === plan.id
                const totalPhases = plan.rollout_phases?.length ?? 0
                return (
                  <Pulsable className={`chropa-plan${isSel ? ' is-selected' : ''}`}
                    key={plan.id}
                    aria-pressed={isSel}
                    onClick={() => { setSelectedId(isSel ? null : plan.id); setSimulate(null) }}
                  >
                    <div className="chropa-row-4">
                      <span className="u-text1-sm-600 chropa-wrap">
                        {plan.title || plan.name || plan.id}
                      </span>
                      <StatusBadge kind={STATUS_KIND[status] ?? 'neutral'} caps={false}>{etiqueta(t, 'estado', status)}</StatusBadge>
                    </div>
                    <div className="chropa-row-5">
                      <span>{t('changerollout.fase_n_de', { actual: (plan.current_phase_index ?? 0) + (plan.status === 'completed' ? 0 : 1), total: totalPhases || '—' })}</span>
                      {plan.created_at && (
                        <span>{t('changerollout.creado_el', { fecha: fmtDate(plan.created_at) })}</span>
                      )}
                    </div>
                  </Pulsable>
                )
              })}
            </div>
          )}
        </div>

        {/* Plan detail */}
        {selectedPlan && (
          <div className="chropa-box-2">
            <div className="chropa-box-3">
              {selectedPlan.title || selectedPlan.name || selectedPlan.id}
            </div>
            <div className="chropa-box-4">
              {selectedPlan.id}
            </div>

            {/* Phases progress */}
            <div className="u-mb-14">
              <div className="chropa-fieldlabel">{t('changerollout.progreso_fases')}</div>
              {(selectedPlan.rollout_phases || []).length === 0 ? (
                <div className="u-text2-xs">{t('changerollout.sin_fases_definidas')}</div>
              ) : (
                <div className="u-stack-6">
                  {(selectedPlan.rollout_phases || []).map((phase, i) => {
                    const cur = selectedPlan.current_phase_index ?? 0
                    const phaseStatus = phase.status || (i < cur ? 'completed' : i === cur ? 'ready' : 'pending')
                    const color = phaseStatus === 'completed' ? 'var(--success)'
                      : phaseStatus === 'ready' ? 'var(--accent)'
                      : 'var(--text-3)'
                    return (
                      <div key={phase.id || i} className="chropa-row-6">
                        <div className="chropa-row-10 change-rollout-panel-e4" style={{ '--change-rollout-panel-color': color } as CSSProperties}>
                          {phaseStatus === 'completed' ? <Check size={12} aria-hidden /> : i + 1}
                        </div>
                        <div className="u-flex1-min0">
                          <div className="u-text1-sm-600">
                            {phase.name}
                            <span className="chropa-box-5">
                              {phase.target_pct}% · {t('changerollout.n_min', { n: phase.duration_minutes ?? 0 })}
                            </span>
                          </div>
                          {phase.description && (
                            <div className="chropa-fase-desc">
                              {phase.description}
                            </div>
                          )}
                        </div>
                        <StatusBadge kind={PHASE_KIND[phaseStatus] ?? 'neutral'} caps={false}>{etiqueta(t, 'fase', phaseStatus)}</StatusBadge>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="u-wrap-8">
              {selectedPlan.status === 'draft' && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => approveMutation.mutate(selectedPlan.id)}
                  loading={approveMutation.isPending}
                  icon={<CheckCircle size={13} />}
                >{t('changerollout.aprobar')}</Button>
              )}
              {(selectedPlan.status === 'approved' || selectedPlan.status === 'in_progress') && (
                <Button
                  size="sm"
                  onClick={() => handleAdvance(selectedPlan.id)}
                  loading={advanceMutation.isPending}
                  icon={<ChevronRight size={13} />}
                >{t('changerollout.avanzar_fase')}</Button>
              )}
              {['approved', 'in_progress'].includes(selectedPlan.status || '') && (
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => handleRollback(selectedPlan.change_request_id)}
                  loading={rollbackMutation.isPending}
                  icon={<RotateCcw size={13} />}
                >{t('changerollout.vuelta_atras')}</Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => handleSimulate(selectedPlan)}
                icon={<Play size={13} />}
              >{t('changerollout.simular')}</Button>
            </div>

            {/* Simulation result */}
            {simulate && (
              <div className="chropa-box-6">
                <div className="chropa-row-7">
                  <div className="chropa-fieldlabel2">{t('changerollout.simulacion')}</div>
                  {simulate.risk_label && (
                    <StatusBadge kind={RISK_KIND[simulate.risk_label] ?? 'neutral'} caps={false}>
                      {t('changerollout.riesgo_x', { nivel: etiqueta(t, 'riesgo', simulate.risk_label) })}
                      {simulate.risk_score != null && ` · ${Math.round(simulate.risk_score * 100)}%`}
                    </StatusBadge>
                  )}
                </div>
                <div className="chropa-row-8">
                  {simulate.estimated_duration_minutes != null && (
                    <span><span className="u-text3">{t('changerollout.duracion_estimada')}</span> <strong>{t('changerollout.n_min', { n: simulate.estimated_duration_minutes })}</strong></span>
                  )}
                  {simulate.recommended_window && (
                    <span><span className="u-text3">{t('changerollout.ventana')}</span> <strong>{simulate.recommended_window}</strong></span>
                  )}
                  {simulate.rollback_readiness && (
                    <span><span className="u-text3">{t('changerollout.vuelta_atras_label')}</span> <strong>{etiqueta(t, 'preparacion', simulate.rollback_readiness)}</strong></span>
                  )}
                </div>
                {Array.isArray(simulate.recommendations) && simulate.recommendations.length > 0 && (
                  <div className="chropa-stack-1">
                    {simulate.recommendations.map((r, i) => (
                      <div key={i} className="chropa-row-9">
                        <AlertTriangle size={12} className="changero-sx4" aria-hidden />
                        <span>{r}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}
