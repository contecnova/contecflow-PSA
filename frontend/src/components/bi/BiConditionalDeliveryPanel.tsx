/**
 * BiConditionalDeliveryPanel — Entrega condicional de reportes.
 * Conecta con /api/v1/bi/delivery/rules
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biConditionalDeliveryApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { Bell, Play, ToggleLeft, ToggleRight } from 'lucide-react'

// TODO type: biConditionalDeliveryApi rule payload — needs shared type
interface DeliveryRule {
  id: string | number
  name: string
  report_id: string
  condition_type: string
  diff_threshold_pct?: number
  enabled: boolean
}

interface DeliveryRulesResponse {
  items?: DeliveryRule[]
}

interface RuleForm {
  name: string
  report_id: string
  diff_threshold_pct: number
  recipients: string
}

interface EvaluateResult {
  should_deliver?: boolean
  [k: string]: unknown
}

const S: Record<string, React.CSSProperties> = {
  card:  { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '20px 24px' },
  input: { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  btn:   { padding: '8px 16px', borderRadius: 8, background: 'var(--accent)', color: 'var(--on-accent)', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
  row:   { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
}

export default function BiConditionalDeliveryPanel() {
  const t  = useAppT()
  const qc = useQueryClient()

  const [form, setForm] = useState<RuleForm>({ name: '', report_id: '', diff_threshold_pct: 10, recipients: '' })
  const [evaluateResult, setEvaluateResult] = useState<Record<string, EvaluateResult>>({})

  const { data, isLoading } = useQuery<DeliveryRulesResponse>({
    queryKey: ['bi-delivery-rules'],
    queryFn:  () => biConditionalDeliveryApi.listRules().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; report_id: string; diff_threshold_pct: number; schedule_cron: string; recipients: string[] }) => biConditionalDeliveryApi.createRule(payload).then(r => r.data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bi-delivery-rules'] }); setForm({ name: '', report_id: '', diff_threshold_pct: 10, recipients: '' }) },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: DeliveryRule['id']; enabled: boolean }) => biConditionalDeliveryApi.updateRule(id, { enabled }).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-delivery-rules'] }),
  })

  const evaluateMutation = useMutation<EvaluateResult, unknown, DeliveryRule['id']>({
    mutationFn: (id) => biConditionalDeliveryApi.evaluate(id, { current_data: {} }).then(r => r.data),
    onSuccess:  (data, id) => setEvaluateResult(prev => ({ ...prev, [String(id)]: data })),
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
          <p style={{ margin: 0, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{t('biconditionaldelivery.envia_reportes_solo_cuando_los_datos_cambian')}</p>
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
        <div className="u-stack-8">
          {(data?.items ?? []).map(rule => (
            <div key={rule.id} style={S.row}>
              <div className="u-flex1-min0">
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{rule.name}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>
                  {rule.report_id} · {rule.condition_type}
                  {rule.diff_threshold_pct != null && ` (≥${rule.diff_threshold_pct}%)`}
                </div>
              </div>
              <div className="u-row-center-10">
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
