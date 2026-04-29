/**
 * BiConditionalDeliveryPanel.jsx — Conditional Report Delivery rules panel.
 * Connects to /api/v1/bi/delivery/rules endpoints.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useChartTheme } from '../../charts/useChartTheme'
import { Bell, Play, ToggleLeft, ToggleRight } from 'lucide-react'

export default function BiConditionalDeliveryPanel() {
  const t = useAppT()
  const { dark } = useChartTheme()
  const qc = useQueryClient()

  const [form, setForm] = useState({
    name: '',
    report_id: '',
    condition_type: 'diff_threshold',
    threshold_pct: 10,
    recipients: '',
  })
  const [evaluateResult, setEvaluateResult] = useState({})

  const { data, isLoading } = useQuery({
    queryKey: ['bi-delivery-rules'],
    queryFn: () => api.get('/bi/delivery/rules').then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (payload) => api.post('/bi/delivery/rules', payload).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bi-delivery-rules'] })
      setForm({ name: '', report_id: '', condition_type: 'diff_threshold', threshold_pct: 10, recipients: '' })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }) => api.patch(`/bi/delivery/rules/${id}`, { enabled }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-delivery-rules'] }),
  })

  const evaluateMutation = useMutation({
    mutationFn: (id) => api.post(`/bi/delivery/rules/${id}/evaluate`).then(r => r.data),
    onSuccess: (data, id) => setEvaluateResult(prev => ({ ...prev, [id]: data })),
  })

  const cardCls = `rounded-xl border p-6 ${dark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`

  return (
    <div className={cardCls}>
      <div className="flex items-center gap-2 mb-4">
        <Bell className="w-5 h-5 text-indigo-500" />
        <h2 className="text-lg font-bold">{t('bi.delivery.title', 'Entrega Condicional de Reportes')}</h2>
      </div>

      {/* Create rule form */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-5">
        <input
          placeholder={t('bi.delivery.rule_name', 'Nombre de regla')}
          value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
          className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
        />
        <input
          placeholder={t('bi.delivery.report_id', 'ID de reporte')}
          value={form.report_id}
          onChange={e => setForm(f => ({ ...f, report_id: e.target.value }))}
          className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
        />
        <select
          value={form.condition_type}
          onChange={e => setForm(f => ({ ...f, condition_type: e.target.value }))}
          className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
        >
          <option value="diff_threshold">Diff threshold</option>
          <option value="always">Always</option>
          <option value="on_anomaly">On anomaly</option>
          <option value="on_sla_breach">On SLA breach</option>
        </select>
        {form.condition_type === 'diff_threshold' && (
          <input
            type="number"
            min={0}
            max={100}
            value={form.threshold_pct}
            onChange={e => setForm(f => ({ ...f, threshold_pct: Number(e.target.value) }))}
            placeholder="Threshold %"
            className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
          />
        )}
        <input
          placeholder="recipient@email.com"
          value={form.recipients}
          onChange={e => setForm(f => ({ ...f, recipients: e.target.value }))}
          className={`rounded border px-3 py-1.5 text-sm ${dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-300'}`}
        />
        <button
          onClick={() => createMutation.mutate({
            ...form,
            recipients: form.recipients ? form.recipients.split(',').map(r => r.trim()) : [],
          })}
          disabled={createMutation.isPending || !form.name || !form.report_id}
          className="px-4 py-1.5 rounded bg-indigo-600 text-white text-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          {t('bi.delivery.create', 'Crear regla')}
        </button>
      </div>

      {/* Rules list */}
      {isLoading ? (
        <div className="text-gray-400 text-sm">Loading…</div>
      ) : (
        <div className="space-y-2">
          {(data?.items ?? []).map(rule => (
            <div
              key={rule.id}
              className={`flex items-center justify-between px-4 py-3 rounded-lg ${dark ? 'bg-gray-800' : 'bg-gray-50'}`}
            >
              <div>
                <p className="font-medium text-sm">{rule.name}</p>
                <p className="text-xs text-gray-500">{rule.report_id} · {rule.condition_type}
                  {rule.threshold_pct != null && ` (≥${rule.threshold_pct}%)`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {evaluateResult[rule.id] && (
                  <span className={`text-xs px-2 py-0.5 rounded-full ${evaluateResult[rule.id].should_deliver ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                    {evaluateResult[rule.id].should_deliver ? '→ Enviar' : '— Sin cambio'}
                  </span>
                )}
                <button
                  onClick={() => evaluateMutation.mutate(rule.id)}
                  className="text-blue-400 hover:text-blue-600"
                  title="Evaluar ahora"
                >
                  <Play className="w-4 h-4" />
                </button>
                <button
                  onClick={() => toggleMutation.mutate({ id: rule.id, enabled: !rule.enabled })}
                  className={rule.enabled ? 'text-green-400' : 'text-gray-400'}
                  title={rule.enabled ? 'Desactivar' : 'Activar'}
                >
                  {rule.enabled ? <ToggleRight className="w-5 h-5" /> : <ToggleLeft className="w-5 h-5" />}
                </button>
              </div>
            </div>
          ))}
          {!(data?.items?.length) && <p className="text-sm text-gray-400">{t('bi.delivery.no_rules', 'No hay reglas creadas')}</p>}
        </div>
      )}
    </div>
  )
}
