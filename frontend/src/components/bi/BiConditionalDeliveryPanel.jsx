/**
 * BiConditionalDeliveryPanel — Entrega condicional de reportes.
 * Conecta con /api/v1/bi/delivery/rules
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { Bell, Play, ToggleLeft, ToggleRight } from 'lucide-react'

const S = {
  card:  { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '20px 24px' },
  input: { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  btn:   { padding: '8px 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
  row:   { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
}

export default function BiConditionalDeliveryPanel() {
  const t  = useAppT()
  const qc = useQueryClient()

  const [form, setForm] = useState({ name: '', report_id: '', diff_threshold_pct: 10, recipients: '' })
  const [evaluateResult, setEvaluateResult] = useState({})

  const { data, isLoading } = useQuery({
    queryKey: ['bi-delivery-rules'],
    queryFn:  () => api.get('/bi/delivery/rules').then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (payload) => api.post('/bi/delivery/rules', payload).then(r => r.data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bi-delivery-rules'] }); setForm({ name: '', report_id: '', diff_threshold_pct: 10, recipients: '' }) },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }) => api.patch(`/bi/delivery/rules/${id}`, { enabled }).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-delivery-rules'] }),
  })

  const evaluateMutation = useMutation({
    mutationFn: (id) => api.post(`/bi/delivery/rules/${id}/evaluate`, { current_data: {} }).then(r => r.data),
    onSuccess:  (data, id) => setEvaluateResult(prev => ({ ...prev, [id]: data })),
  })

  return (
    <div style={S.card}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
          <Bell size={16} />
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>
            {t('bi.delivery.title', 'Entrega Condicional de Reportes')}
          </h3>
          <p style={{ margin: 0, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>Envía reportes solo cuando los datos cambian significativamente</p>
        </div>
      </div>

      {/* Create rule form */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8, marginBottom: 20 }}>
        <input
          placeholder={t('bi.delivery.rule_name', 'Nombre de regla')}
          value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
          style={S.input}
        />
        <input
          placeholder={t('bi.delivery.report_id', 'ID de reporte')}
          value={form.report_id}
          onChange={e => setForm(f => ({ ...f, report_id: e.target.value }))}
          style={S.input}
        />
        <input
          type="number" min={0} max={100}
          value={form.diff_threshold_pct}
          onChange={e => setForm(f => ({ ...f, diff_threshold_pct: Number(e.target.value) }))}
          placeholder="Threshold %"
          style={S.input}
        />
        <input
          placeholder="recipient@email.com"
          value={form.recipients}
          onChange={e => setForm(f => ({ ...f, recipients: e.target.value }))}
          style={S.input}
        />
        <button
          onClick={() => createMutation.mutate({
            name:              form.name,
            report_id:         form.report_id,
            diff_threshold_pct: form.diff_threshold_pct,
            schedule_cron:     '0 8 * * 1',
            recipients:        form.recipients ? form.recipients.split(',').map(r => r.trim()) : [],
          })}
          disabled={createMutation.isPending || !form.name || !form.report_id}
          style={{ ...S.btn, opacity: (createMutation.isPending || !form.name || !form.report_id) ? 0.5 : 1 }}
        >
          {t('bi.delivery.create', 'Crear regla')}
        </button>
      </div>

      {/* Rules list */}
      {isLoading ? (
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: '20px 0' }}>Cargando…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {(data?.items ?? []).map(rule => (
            <div key={rule.id} style={S.row}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{rule.name}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>
                  {rule.report_id} · {rule.condition_type}
                  {rule.diff_threshold_pct != null && ` (≥${rule.diff_threshold_pct}%)`}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {evaluateResult[rule.id] && (
                  <span style={{
                    fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                    background: evaluateResult[rule.id].should_deliver ? 'var(--success-bg)' : 'var(--surface-4)',
                    color: evaluateResult[rule.id].should_deliver ? 'var(--success)' : 'var(--text-3)',
                  }}>
                    {evaluateResult[rule.id].should_deliver ? '→ Enviar' : '— Sin cambio'}
                  </span>
                )}
                <button
                  onClick={() => evaluateMutation.mutate(rule.id)}
                  title="Evaluar ahora"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', padding: 4, display: 'flex' }}
                >
                  <Play size={16} />
                </button>
                <button
                  onClick={() => toggleMutation.mutate({ id: rule.id, enabled: !rule.enabled })}
                  title={rule.enabled ? 'Desactivar' : 'Activar'}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: rule.enabled ? 'var(--success)' : 'var(--text-3)', padding: 4, display: 'flex' }}
                >
                  {rule.enabled ? <ToggleRight size={20} /> : <ToggleLeft size={20} />}
                </button>
              </div>
            </div>
          ))}
          {!(data?.items?.length) && (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: '20px 0' }}>
              {t('bi.delivery.no_rules', 'No hay reglas creadas')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
