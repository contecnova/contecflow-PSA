/**
 * ChangeRolloutPanel.jsx — Advanced change rollout management UI.
 *
 * Backend endpoints:
 *   GET  /sd/changes/{cr_id}/rollout-plans
 *   POST /sd/changes/{cr_id}/rollout-plans
 *     body: { title, rollout_phases: [{name, description, target_pct, gate_criteria, duration_minutes}], rollback_steps, ... }
 *   POST /sd/changes/rollout-plans/{plan_id}/approve
 *   POST /sd/changes/rollout-plans/{plan_id}/advance-phase   { phase_notes }
 *   POST /sd/changes/{cr_id}/rollout-plans/{plan_id}/simulate
 *   POST /sd/changes/{cr_id}/rollback                         { reason }
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { changeRolloutApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { GitBranch, ChevronRight, CheckCircle, AlertTriangle, RotateCcw, Play, Plus } from 'lucide-react'
import { Card, Button, Spinner, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'
import { pedirTexto } from '../../context/ConfirmContext'
import { localeActivo } from '../../utils/helpers'

// TODO type: changeRolloutApi rollout plan/phase payloads — needs shared types
interface RolloutPhase {
  id?: string | number
  name: string
  description?: string
  target_pct: number
  duration_minutes?: number
  gate_criteria?: string[]
  status?: string
}

interface RolloutPlan {
  id: string | number
  name?: string
  title?: string
  change_request_id: string
  strategy: string
  status?: string
  risk_level?: string
  current_phase_index?: number
  created_at?: string
  rollout_phases?: RolloutPhase[]
}

interface RolloutForm {
  change_request_id: string
  strategy: string
  phases: number
  name: string
}

// TODO type: simulate response — needs shared type
type SimulateResult = {
  [k: string]: unknown
  risk_label?: string
  risk_score?: number
  estimated_duration_minutes?: number
  recommended_window?: string
  rollback_readiness?: string
  recommendations?: string[]
}

type ApiError = { response?: { data?: { detail?: string } } }

const STATUS_META: Record<string, { label: string; color: string }> = {
  draft:        { label: 'Borrador',   color: 'var(--text-3)' },
  approved:     { label: 'Aprobado',   color: 'var(--success)' },
  in_progress:  { label: 'En curso',   color: 'var(--accent)' },
  rolled_back:  { label: 'Revertido',  color: 'var(--danger)' },
  completed:    { label: 'Completado', color: 'var(--success)' },
}

const RISK_COLOR: Record<string, string> = {
  low: 'var(--success)',
  medium: 'var(--warning)',
  high: 'var(--orange)',
  critical: 'var(--danger)',
}

const STRATEGY_LABEL: Record<string, string> = {
  canary:     'Canary',
  blue_green: 'Blue/Green',
  rolling:    'Rolling',
  big_bang:   'Big Bang',
}

const fieldLabel: React.CSSProperties = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
}
const inputBase: React.CSSProperties = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-sm)',
  fontFamily: 'inherit',
  outline: 'none',
  boxSizing: 'border-box',
}
const chip = (color: string): React.CSSProperties => ({
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color,
  background: `color-mix(in srgb, ${color} 15%, transparent)`,
  border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
  borderRadius: 'var(--radius-full, 999px)',
  padding: '2px 9px',
  whiteSpace: 'nowrap',
})

/**
 * Build canonical rollout_phases from strategy + total phases.
 * Each strategy maps to a sensible default progression.
 */
function buildPhases(strategy: string, total: number | string): RolloutPhase[] {
  const n = Math.max(1, Math.min(10, Number(total) || 3))
  switch (strategy) {
    case 'canary': {
      // 1% → 5% → 25% → 50% → 100% (sliced to n)
      const seed = [1, 5, 25, 50, 100]
      const ramp = seed.slice(0, Math.max(2, n - 1)).concat([100])
      const slice = ramp.slice(0, n)
      return slice.map((pct, i) => ({
        name: `Canary ${pct}%`,
        description: i === 0 ? 'Canary inicial' : i === slice.length - 1 ? 'Rollout completo' : `Expansión a ${pct}%`,
        target_pct: pct,
        duration_minutes: i === 0 ? 30 : i === slice.length - 1 ? 60 : 45,
        gate_criteria: i === 0 ? ['Sin errores en logs', 'Latencia p95 estable'] : [],
      }))
    }
    case 'blue_green':
      return [
        { name: 'Provisión Green', description: 'Levantar entorno paralelo', target_pct: 100, duration_minutes: 30, gate_criteria: ['Smoke tests OK'] },
        { name: 'Cutover', description: 'Conmutación de tráfico Blue → Green', target_pct: 100, duration_minutes: 15, gate_criteria: ['Healthcheck OK'] },
        { name: 'Decomisionar Blue', description: 'Retirada del entorno antiguo', target_pct: 100, duration_minutes: 30, gate_criteria: ['Sin rollbacks tras 1h'] },
      ].slice(0, n)
    case 'rolling': {
      const buckets = Array.from({ length: n }, (_, i) => Math.round(((i + 1) / n) * 100))
      return buckets.map((pct, i) => ({
        name: `Rolling ${i + 1}/${n}`,
        description: `Reemplazo progresivo (${pct}%)`,
        target_pct: pct,
        duration_minutes: 30,
        gate_criteria: [],
      }))
    }
    case 'big_bang':
    default:
      return [
        { name: 'Big Bang', description: 'Despliegue total simultáneo', target_pct: 100, duration_minutes: 30, gate_criteria: ['Smoke tests pre-deploy'] },
      ]
  }
}

export default function ChangeRolloutPanel() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()

  const [selectedId, setSelectedId] = useState<string | number | null>(null)
  const [showCreate, setShowCreate] = useState<boolean>(false)
  const [changeRequestFilter, setChangeRequestFilter] = useState<string>('')
  const [form, setForm] = useState<RolloutForm>({ change_request_id: '', strategy: 'canary', phases: 3, name: '' })
  const [simulate, setSimulate] = useState<SimulateResult | null>(null)

  const { data: plansData, isLoading } = useQuery<{ items?: RolloutPlan[] }>({
    queryKey: ['change-rollout-plans', changeRequestFilter],
    queryFn: () => changeRolloutApi.listPlans(changeRequestFilter).then(r => r.data),
    enabled: Boolean(changeRequestFilter.trim()),
  })

  const plans: RolloutPlan[] = plansData?.items ?? []
  const selectedPlan = plans.find(p => p.id === selectedId)

  const createMutation = useMutation({
    mutationFn: (data: RolloutForm) => {
      const phases = buildPhases(data.strategy, data.phases)
      return changeRolloutApi.createPlan(data.change_request_id, {
        title: data.name?.trim() || `Plan ${STRATEGY_LABEL[data.strategy] || data.strategy}`,
        rollout_phases: phases,
        rollback_steps: [
          'Detener el rollout actual',
          'Restaurar el estado anterior',
          'Notificar a stakeholders',
        ],
      }).then(r => r.data)
    },
    onSuccess: (_res, data) => {
      toast.success('Plan de rollout creado')
      qc.invalidateQueries({ queryKey: ['change-rollout-plans'] })
      setChangeRequestFilter(data.change_request_id)
      setShowCreate(false)
      setForm({ change_request_id: '', strategy: 'canary', phases: 3, name: '' })
    },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || 'Error al crear el plan'),
  })

  const approveMutation = useMutation({
    mutationFn: (id: string | number) => changeRolloutApi.approvePlan(id).then(r => r.data),
    onSuccess: () => {
      toast.success('Plan aprobado')
      qc.invalidateQueries({ queryKey: ['change-rollout-plans'] })
    },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || 'Error al aprobar el plan'),
  })

  const advanceMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string | number; notes: string }) =>
      changeRolloutApi.advancePhase(id, { phase_notes: notes || null }).then(r => r.data),
    onSuccess: (data: { status?: string }) => {
      const status = data?.status || 'in_progress'
      toast.success(status === 'completed' ? 'Rollout completado 🎉' : 'Fase avanzada')
      qc.invalidateQueries({ queryKey: ['change-rollout-plans'] })
    },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || 'Error al avanzar de fase'),
  })

  const rollbackMutation = useMutation({
    mutationFn: ({ changeId, reason }: { changeId: string; reason: string }) =>
      changeRolloutApi.rollback(changeId, { reason }).then(r => r.data),
    onSuccess: () => {
      toast.success('Rollback ejecutado')
      qc.invalidateQueries({ queryKey: ['change-rollout-plans'] })
    },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || 'Error al ejecutar rollback'),
  })

  const handleSimulate = async (plan: RolloutPlan) => {
    try {
      const res = await changeRolloutApi.simulatePlan(plan.change_request_id, plan.id)
      setSimulate(res.data?.simulation ?? res.data?.impact ?? res.data)
    } catch (e: unknown) {
      toast.error((e as ApiError)?.response?.data?.detail || 'Error al simular')
    }
  }

  const handleAdvance = async (id: string | number) => {
    const notes = await pedirTexto({ title: 'Avanzar fase', message: 'Puedes añadir notas para esta fase.', label: 'Notas (opcional)', multiline: true, confirmLabel: 'Avanzar' })
    if (notes === null) return
    advanceMutation.mutate({ id, notes: notes.trim() })
  }

  const handleRollback = async (changeId: string) => {
    const reason = await pedirTexto({ title: 'Rollback del cambio', message: 'El motivo del rollback queda registrado.', label: 'Motivo del rollback', required: true, multiline: true, danger: true, confirmLabel: 'Hacer rollback' })
    if (!reason || !reason.trim()) return
    rollbackMutation.mutate({ changeId, reason: reason.trim() })
  }

  return (
    <Card style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
        <div className="u-row-center-8">
          <GitBranch size={18} style={{ color: 'var(--purple)' }} />
          <h2 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>
            {t('sd.rollout.title', 'Planes de rollout de cambios')}
          </h2>
        </div>
        <Button onClick={() => setShowCreate(v => !v)} icon={<Plus size={14} />}>
          {showCreate ? 'Cerrar' : t('sd.rollout.create', 'Nuevo plan')}
        </Button>
      </div>

      <div className="u-mb-14">
        <div style={fieldLabel}>{t('changerollout.filtrar_por_change_request')}</div>
        <input aria-label="Change Request ID (uuid)"
          type="text"
          placeholder="Change Request ID (uuid)"
          value={changeRequestFilter}
          onChange={e => setChangeRequestFilter(e.target.value)}
          style={inputBase}
        />
      </div>

      {showCreate && (
        <div style={{
          background: 'var(--surface-3)',
          border: '1px solid color-mix(in srgb, var(--purple) 30%, var(--surface-4))',
          borderRadius: 12,
          padding: '14px 16px',
          marginBottom: 16,
        }}>
          <div style={fieldLabel}>{t('sd.rollout.new_plan', 'Nuevo plan de rollout')}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
            <input aria-label="Change Request ID"
              type="text"
              placeholder="Change Request ID"
              value={form.change_request_id}
              onChange={e => setForm(f => ({ ...f, change_request_id: e.target.value }))}
              style={{ ...inputBase, gridColumn: '1 / -1' }}
            />
            <input aria-label={t('changerollout.nombre_del_plan_opcional')}
              type="text"
              placeholder={t('changerollout.nombre_del_plan_opcional')}
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              style={inputBase}
            />
            <select
              value={form.strategy}
              onChange={e => setForm(f => ({ ...f, strategy: e.target.value }))}
              style={inputBase}
            >
              {Object.entries(STRATEGY_LABEL).map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, gridColumn: '1 / -1' }}>
              <span className="u-text2-xs">Fases:</span>
              <input
                aria-label="Fases"
                type="number" min={1} max={10}
                value={form.phases}
                onChange={e => setForm(f => ({ ...f, phases: Number(e.target.value) }))}
                style={{ ...inputBase, width: 80 }}
              />
              <span className="u-text3-xs">
                Vista previa: {buildPhases(form.strategy, form.phases).map(p => `${p.target_pct}%`).join(' → ')}
              </span>
            </div>
          </div>
          <div className="u-row-8">
            <Button
              onClick={() => createMutation.mutate(form)}
              disabled={!form.change_request_id.trim() || createMutation.isPending}
              loading={createMutation.isPending}
            >
              {t('sd.rollout.create_plan', 'Crear plan')}
            </Button>
            <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
        {/* Plans list */}
        <div>
          <div style={fieldLabel}>Planes</div>
          {!changeRequestFilter.trim() ? (
            <EmptyState icon="🔎" title={t('changerollout.filtra_por_change_request_id')} description="Indica el ID del Change Request para listar sus planes de rollout." />
          ) : isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : !plans.length ? (
            <EmptyState icon="🚀" title={t('sd.rollout.no_plans', 'No hay planes para este CR')} />
          ) : (
            <div className="u-stack-6">
              {plans.map(plan => {
                const meta = STATUS_META[plan.status || ''] ?? STATUS_META.draft
                const isSel = selectedId === plan.id
                const totalPhases = plan.rollout_phases?.length ?? 0
                return (
                  <button
                    key={plan.id}
                    type="button"
                    onClick={() => { setSelectedId(isSel ? null : plan.id); setSimulate(null) }}
                    style={{
                      width: '100%', textAlign: 'left',
                      padding: '12px 14px',
                      background: isSel
                        ? 'color-mix(in srgb, var(--purple) 8%, var(--surface-3))'
                        : 'var(--surface-3)',
                      border: `1px solid ${isSel ? 'var(--purple)' : 'var(--surface-4)'}`,
                      borderRadius: 'var(--radius-md)',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      transition: 'border-color .15s, background .15s',
                    }}
                    onMouseEnter={e => { if (!isSel) e.currentTarget.style.borderColor = 'var(--accent)' }}
                    onMouseLeave={e => { if (!isSel) e.currentTarget.style.borderColor = 'var(--surface-4)' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <span className="u-text1-sm-600">
                        {plan.title || plan.name || plan.id}
                      </span>
                      <span style={chip(meta.color)}>{meta.label}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                      <span>Fase {(plan.current_phase_index ?? 0) + (plan.status === 'completed' ? 0 : 1)} / {totalPhases || '—'}</span>
                      {plan.created_at && (
                        <span>Creado {new Date(plan.created_at).toLocaleDateString(localeActivo())}</span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Plan detail */}
        {selectedPlan && (
          <div style={{
            background: 'var(--surface-3)',
            border: '1px solid var(--surface-4)',
            borderRadius: 12,
            padding: '14px 16px',
          }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 4 }}>
              {selectedPlan.title || selectedPlan.name || selectedPlan.id}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 12, fontFamily: 'var(--font-mono)' }}>
              {selectedPlan.id}
            </div>

            {/* Phases progress */}
            <div className="u-mb-14">
              <div style={fieldLabel}>{t('sd.rollout.phases', 'Progreso de fases')}</div>
              {(selectedPlan.rollout_phases || []).length === 0 ? (
                <div className="u-text3-xs">{t('changerollout.sin_fases_definidas')}</div>
              ) : (
                <div className="u-stack-6">
                  {(selectedPlan.rollout_phases || []).map((phase, i) => {
                    const cur = selectedPlan.current_phase_index ?? 0
                    const phaseStatus = phase.status || (i < cur ? 'completed' : i === cur ? 'ready' : 'pending')
                    const color = phaseStatus === 'completed' ? 'var(--success)'
                      : phaseStatus === 'in_progress' || phaseStatus === 'ready' ? 'var(--accent)'
                      : 'var(--text-3)'
                    return (
                      <div key={phase.id || i} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 12px',
                        background: 'var(--surface-1)',
                        border: '1px solid var(--surface-4)',
                        borderRadius: 8,
                      }}>
                        <div style={{
                          width: 22, height: 22, borderRadius: '50%',
                          background: `color-mix(in srgb, ${color} 15%, transparent)`,
                          border: `1px solid ${color}`,
                          color, fontSize: 'var(--text-xs)', fontWeight: 700,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          flexShrink: 0,
                        }}>{phaseStatus === 'completed' ? '✓' : i + 1}</div>
                        <div className="u-flex1-min0">
                          <div className="u-text1-sm-600">
                            {phase.name}
                            <span style={{ marginLeft: 8, fontSize: 'var(--text-xs)', color: 'var(--text-3)', fontWeight: 400 }}>
                              {phase.target_pct}% · {phase.duration_minutes}min
                            </span>
                          </div>
                          {phase.description && (
                            <div className="u-text3-xs-mt2">
                              {phase.description}
                            </div>
                          )}
                        </div>
                        <span style={chip(color)}>{phaseStatus}</span>
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
                >Aprobar</Button>
              )}
              {(selectedPlan.status === 'approved' || selectedPlan.status === 'in_progress') && (
                <Button
                  size="sm"
                  onClick={() => handleAdvance(selectedPlan.id)}
                  loading={advanceMutation.isPending}
                  icon={<ChevronRight size={13} />}
                >Avanzar fase</Button>
              )}
              {['approved', 'in_progress'].includes(selectedPlan.status || '') && (
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => handleRollback(selectedPlan.change_request_id)}
                  loading={rollbackMutation.isPending}
                  icon={<RotateCcw size={13} />}
                >Rollback</Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => handleSimulate(selectedPlan)}
                icon={<Play size={13} />}
              >Simular</Button>
            </div>

            {/* Simulation result */}
            {simulate && (
              <div style={{
                marginTop: 14,
                background: 'var(--surface-1)',
                border: '1px solid var(--surface-4)',
                borderRadius: 8,
                padding: '12px 14px',
                fontSize: 'var(--text-xs)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div style={{ ...fieldLabel, marginBottom: 0 }}>{t('sd.rollout.simulation', 'Simulación de impacto')}</div>
                  {simulate.risk_label && (
                    <span style={chip(RISK_COLOR[simulate.risk_label] || 'var(--text-3)')}>
                      Riesgo {simulate.risk_label}
                      {simulate.risk_score != null && ` · ${Math.round(simulate.risk_score * 100)}%`}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginBottom: 8 }}>
                  {simulate.estimated_duration_minutes != null && (
                    <span><span className="u-text3">{t('changerollout.duracion_estimada')}</span> <strong>{simulate.estimated_duration_minutes}min</strong></span>
                  )}
                  {simulate.recommended_window && (
                    <span><span className="u-text3">Ventana:</span> <strong>{simulate.recommended_window}</strong></span>
                  )}
                  {simulate.rollback_readiness && (
                    <span><span className="u-text3">Rollback:</span> <strong>{simulate.rollback_readiness}</strong></span>
                  )}
                </div>
                {Array.isArray(simulate.recommendations) && simulate.recommendations.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {simulate.recommendations.map((r, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)' }}>
                        <AlertTriangle size={12} style={{ color: 'var(--warning)', flexShrink: 0 }} />
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
