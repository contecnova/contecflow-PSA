/**
 * BiConditionalDeliveryPanel — Entrega condicional de reportes.
 * Conecta con /api/v1/bi/delivery/rules
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biConditionalDeliveryApi } from '../../services/api'
import type { EvaluacionDeEntregaBi, ReglaDeEntregaBi } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { Bell, Play, ToggleLeft, ToggleRight } from 'lucide-react'
import './BiConditionalDeliveryPanel.css'

interface RuleForm {
  name: string
  report_id: string
  diff_threshold_pct: number
  recipients: string
}

const S: Record<string, React.CSSProperties> = {
  card:  { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-lg)', padding: '20px 24px' },
  input: { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  btn:   { padding: '8px 16px', borderRadius: 8, background: 'var(--accent)', color: 'var(--on-accent)', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
  row:   { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
}

export default function BiConditionalDeliveryPanel() {
  const t  = useAppT()
  const qc = useQueryClient()

  const [form, setForm] = useState<RuleForm>({ name: '', report_id: '', diff_threshold_pct: 10, recipients: '' })
  const [evaluateResult, setEvaluateResult] = useState<Record<string, EvaluacionDeEntregaBi>>({})

  const { data, isLoading } = useQuery({
    queryKey: ['bi-delivery-rules'],
    queryFn:  () => biConditionalDeliveryApi.listRules().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; report_id: string; diff_threshold_pct: number; schedule_cron: string; recipients: string[] }) => biConditionalDeliveryApi.createRule(payload).then(r => r.data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bi-delivery-rules'] }); setForm({ name: '', report_id: '', diff_threshold_pct: 10, recipients: '' }) },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: ReglaDeEntregaBi['id']; enabled: boolean }) => biConditionalDeliveryApi.updateRule(id, { enabled }).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-delivery-rules'] }),
  })

  const evaluateMutation = useMutation({
    mutationFn: (id: ReglaDeEntregaBi['id']) => biConditionalDeliveryApi.evaluate(id, { current_data: {} }).then(r => r.data),
    onSuccess:  (data, id) => setEvaluateResult(prev => ({ ...prev, [id]: data })),
  })

  return (
    <div style={S.card}>
      {/* Header */}
      <div className="bicodepa-row-1">
        <div className="bicodepa-row-2">
          <Bell size={16} />
        </div>
        <div>
          <h3 className="bicodepa-box-1">
            {t('bi.delivery.title', 'Entrega Condicional de Reportes')}
          </h3>
          <p className="bicodepa-box-2">{t('biconditionaldelivery.envia_reportes_solo_cuando_los_datos_cambian')}</p>
        </div>
      </div>

      {/* Create rule form */}
      <div className="bicodepa-grid-1">
        <input aria-label={t('bi.delivery.rule_name', 'Nombre de regla')}
          placeholder={t('bi.delivery.rule_name', 'Nombre de regla')}
          value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
          style={S.input}
        />
        <input aria-label={t('bi.delivery.report_id', 'ID de reporte')}
          placeholder={t('bi.delivery.report_id', 'ID de reporte')}
          value={form.report_id}
          onChange={e => setForm(f => ({ ...f, report_id: e.target.value }))}
          style={S.input}
        />
        <input aria-label="Threshold %"
          type="number" min={0} max={100}
          value={form.diff_threshold_pct}
          onChange={e => setForm(f => ({ ...f, diff_threshold_pct: Number(e.target.value) }))}
          placeholder="Threshold %"
          style={S.input}
        />
        <input aria-label="recipient@email.com"
          placeholder="recipient@email.com"
          value={form.recipients}
          onChange={e => setForm(f => ({ ...f, recipients: e.target.value }))}
          style={S.input}
        />
        <button className="bicodepa-btn"
          onClick={() => createMutation.mutate({
            name:              form.name,
            report_id:         form.report_id,
            diff_threshold_pct: form.diff_threshold_pct,
            schedule_cron:     '0 8 * * 1',
            recipients:        form.recipients ? form.recipients.split(',').map(r => r.trim()) : [],
          })}
          disabled={createMutation.isPending || !form.name || !form.report_id}
          style={{ opacity: (createMutation.isPending || !form.name || !form.report_id) ? 0.5 : 1 }}
        >
          {t('bi.delivery.create', 'Crear regla')}
        </button>
      </div>

      {/* Rules list */}
      {isLoading ? (
        <div className="bicodepa-box-3">{t('chat.loading')}</div>
      ) : (
        <div className="u-stack-8">
          {(data?.items ?? []).map(rule => (
            <div key={rule.id} style={S.row}>
              <div className="u-flex1-min0">
                <div className="u-text1-base-600">{rule.name}</div>
                <div className="u-text3-xs-mt2">
                  {/* La regla no guarda un `condition_type`: la condición es métrica + operador + valor, si la hay. */}
                  {rule.report_id}
                  {rule.condition_metric && ` · ${rule.condition_metric} ${rule.condition_operator ?? ''} ${rule.condition_value ?? ''}`}
                  {` (≥${rule.diff_threshold_pct}%)`}
                </div>
              </div>
              <div className="u-row-center-10">
                {evaluateResult[rule.id] && (
                  <span className="bicodepa-box-4" style={{ background: evaluateResult[rule.id].should_deliver ? 'var(--success-bg)' : 'var(--surface-4)', color: evaluateResult[rule.id].should_deliver ? 'var(--success)' : 'var(--text-3)' }}>
                    {evaluateResult[rule.id].should_deliver ? '→ Enviar' : '— Sin cambio'}
                  </span>
                )}
                <button aria-label={t('biconditionaldelivery.evaluar_ahora')}
                  onClick={() => evaluateMutation.mutate(rule.id)}
                  title={t('biconditionaldelivery.evaluar_ahora')}
                  className="bicodepa-row-3"
                >
                  <Play size={16} />
                </button>
                <button className="bicodepa-row-4"
                  onClick={() => toggleMutation.mutate({ id: rule.id, enabled: !rule.enabled })}
                  title={rule.enabled ? 'Desactivar' : 'Activar'}
                  style={{ color: rule.enabled ? 'var(--success)' : 'var(--text-3)' }}
                >
                  {rule.enabled ? <ToggleRight size={20} /> : <ToggleLeft size={20} />}
                </button>
              </div>
            </div>
          ))}
          {!data?.items.length && (
            <div className="bicodepa-box-3">
              {t('bi.delivery.no_rules', 'No hay reglas creadas')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
