/**
 * ChangeRolloutPanel.jsx — Advanced change rollout management UI.
 * Connects to /api/v1/sd/change/rollout-plans/* endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { GitBranch, ChevronRight, CheckCircle, AlertTriangle, RotateCcw, Play, Plus } from 'lucide-react'

const STATUS_META = {
  draft:      { label: 'Borrador',    cls: 'bg-gray-100 text-gray-600' },
  approved:   { label: 'Aprobado',    cls: 'bg-green-100 text-green-700' },
  in_progress:{ label: 'En curso',    cls: 'bg-blue-100 text-blue-700' },
  rolled_back:{ label: 'Revertido',   cls: 'bg-red-100 text-red-700' },
  completed:  { label: 'Completado',  cls: 'bg-emerald-100 text-emerald-700' },
}

export default function ChangeRolloutPanel() {
  const t = useAppT()
  const { dark } = useChartTheme()
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ change_request_id: '', strategy: 'canary', phases: 3, name: '' })
  const [simulate, setSimulate] = useState(null)

  const { data: plansData, isLoading } = useQuery({
    queryKey: ['change-rollout-plans'],
    queryFn: () => api.get('/sd/change/rollout-plans').then(r => r.data),
  })

  const selectedPlan = (plansData?.plans ?? []).find(p => p.id === selectedId)

  const createMutation = useMutation({
    mutationFn: (data) => api.post('/sd/change/rollout-plans', data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['change-rollout-plans'] }); setShowCreate(false) },
  })

  const approveMutation = useMutation({
    mutationFn: (id) => api.post(`/sd/change/rollout-plans/${id}/approve`, { approved_by: 'admin' }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['change-rollout-plans'] }),
  })

  const advanceMutation = useMutation({
    mutationFn: ({ id, notes }) => api.post(`/sd/change/rollout-plans/${id}/advance`, { notes }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['change-rollout-plans'] }),
  })

  const rollbackMutation = useMutation({
    mutationFn: ({ id, reason }) => api.post(`/sd/change/rollout-plans/${id}/rollback`, { reason }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['change-rollout-plans'] }),
  })

  const handleSimulate = async (id) => {
    const res = await api.get(`/sd/change/rollout-plans/${id}/simulate`)
    setSimulate(res.data)
  }

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`
  const plans = plansData?.plans ?? []

  return (
    <div className={cardCls}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-purple-500" />
          <h2 className="text-lg font-bold">{t('sd.rollout.title', 'Planes de Rollout de Cambios')}</h2>
        </div>
        <button
          onClick={() => setShowCreate(v => !v)}
          className="flex items-center gap-1 px-3 py-1.5 rounded bg-purple-600 text-white text-sm hover:bg-purple-700"
        >
          <Plus className="w-4 h-4" />
          {t('sd.rollout.create', 'Nuevo plan')}
        </button>
      </div>

      {showCreate && (
        <div className={`rounded-lg border p-4 mb-4 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-purple-50 border-purple-200'}`}>
          <p className="text-sm font-semibold mb-3">{t('sd.rollout.new_plan', 'Nuevo plan de rollout')}</p>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <input
              type="text"
              placeholder="Change Request ID"
              value={form.change_request_id}
              onChange={e => setForm(f => ({ ...f, change_request_id: e.target.value }))}
              className={`col-span-2 rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <input
              type="text"
              placeholder="Nombre del plan"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-300'}`}
            />
            <select
              value={form.strategy}
              onChange={e => setForm(f => ({ ...f, strategy: e.target.value }))}
              className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-300'}`}
            >
              {['canary', 'blue_green', 'rolling', 'big_bang'].map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <div className="flex items-center gap-2">
              <label className="text-xs">Fases:</label>
              <input
                type="number"
                min={1} max={10}
                value={form.phases}
                onChange={e => setForm(f => ({ ...f, phases: Number(e.target.value) }))}
                className={`rounded border px-2 py-1 text-sm w-16 ${dark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-300'}`}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => createMutation.mutate(form)}
              disabled={!form.change_request_id || createMutation.isPending}
              className="px-4 py-1.5 rounded bg-purple-600 text-white text-sm hover:bg-purple-700 disabled:opacity-50"
            >
              {t('sd.rollout.create_plan', 'Crear plan')}
            </button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-1.5 rounded text-sm text-gray-500 hover:text-gray-700">
              Cancelar
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Plans list */}
        <div className="space-y-2">
          {isLoading && <p className="text-sm text-gray-400">{t('common.loading', 'Cargando...')}</p>}
          {plans.map(plan => {
            const meta = STATUS_META[plan.status] ?? STATUS_META.draft
            return (
              <button
                key={plan.id}
                onClick={() => setSelectedId(plan.id === selectedId ? null : plan.id)}
                className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
                  selectedId === plan.id
                    ? (dark ? 'border-purple-500 bg-gray-800' : 'border-purple-400 bg-purple-50')
                    : (dark ? 'border-gray-700 bg-gray-800 hover:border-gray-500' : 'border-gray-200 bg-gray-50 hover:border-gray-300')
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm">{plan.name ?? plan.id}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${meta.cls}`}>{meta.label}</span>
                </div>
                <div className="flex gap-3 mt-1 text-xs text-gray-400">
                  <span>{plan.strategy}</span>
                  <span>Fase {plan.current_phase ?? 0}/{plan.total_phases ?? plan.phases}</span>
                </div>
              </button>
            )
          })}
          {!isLoading && !plans.length && (
            <p className="text-sm text-gray-400">{t('sd.rollout.no_plans', 'No hay planes de rollout')}</p>
          )}
        </div>

        {/* Plan detail + actions */}
        {selectedPlan && (
          <div className={`rounded-lg border p-4 ${dark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
            <p className="font-semibold mb-3">{selectedPlan.name ?? selectedPlan.id}</p>

            {/* Phase progress */}
            <div className="mb-3">
              <p className="text-xs text-gray-400 mb-1">{t('sd.rollout.phases', 'Progreso de fases')}</p>
              <div className="flex gap-1">
                {Array.from({ length: selectedPlan.total_phases ?? selectedPlan.phases ?? 3 }).map((_, i) => (
                  <div
                    key={i}
                    className={`flex-1 h-2 rounded ${
                      i < (selectedPlan.current_phase ?? 0) ? 'bg-green-500' :
                      i === (selectedPlan.current_phase ?? 0) ? 'bg-blue-500' : (dark ? 'bg-gray-700' : 'bg-gray-300')
                    }`}
                  />
                ))}
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex flex-wrap gap-2">
              {selectedPlan.status === 'draft' && (
                <button
                  onClick={() => approveMutation.mutate(selectedPlan.id)}
                  disabled={approveMutation.isPending}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
                >
                  <CheckCircle className="w-3.5 h-3.5" /> Aprobar
                </button>
              )}
              {selectedPlan.status === 'approved' || selectedPlan.status === 'in_progress' ? (
                <button
                  onClick={() => advanceMutation.mutate({ id: selectedPlan.id, notes: '' })}
                  disabled={advanceMutation.isPending}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  <ChevronRight className="w-3.5 h-3.5" /> Avanzar fase
                </button>
              ) : null}
              {['approved', 'in_progress'].includes(selectedPlan.status) && (
                <button
                  onClick={() => rollbackMutation.mutate({ id: selectedPlan.id, reason: 'Manual rollback' })}
                  disabled={rollbackMutation.isPending}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Rollback
                </button>
              )}
              <button
                onClick={() => handleSimulate(selectedPlan.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-amber-500 text-white hover:bg-amber-600"
              >
                <Play className="w-3.5 h-3.5" /> Simular
              </button>
            </div>

            {/* Simulation result */}
            {simulate && (
              <div className={`mt-3 text-xs rounded p-3 ${dark ? 'bg-gray-900' : 'bg-white'} border ${dark ? 'border-gray-700' : 'border-gray-200'}`}>
                <p className="font-medium mb-1">{t('sd.rollout.simulation', 'Simulación')}</p>
                {simulate.risks && (
                  <div className="space-y-1">
                    {simulate.risks.map((r, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <AlertTriangle className="w-3 h-3 text-amber-500 flex-shrink-0" />
                        <span>{r}</span>
                      </div>
                    ))}
                  </div>
                )}
                {simulate.estimated_duration && (
                  <p className="mt-1 text-gray-400">{t('sd.rollout.est_duration', 'Duración estimada')}: {simulate.estimated_duration}</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
