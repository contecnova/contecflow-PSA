/**
 * BiConditionalDeliveryPanel — envío condicional de informes (/predictions).
 * Conecta con /api/v1/bi/delivery/rules
 *
 * 16-11-2026: pasada de diseño. Antes: estilos en línea con campos de fondo
 * gris sin etiqueta («Threshold %», «recipient@email.com» en inglés), textos
 * fijos en castellano («→ Enviar», «Activar») y vacío en texto gris suelto.
 * Ahora: Card/Section, Input/Button del kit, EmptyState y textos traducidos.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biConditionalDeliveryApi } from '../../services/api'
import type { EvaluacionDeEntregaBi, ReglaDeEntregaBi } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { Bell, Play, Plus, ToggleLeft, ToggleRight } from 'lucide-react'
import { Button, Card, EmptyState, Input, Section, Spinner } from '../ui'
import StatusBadge from '../ui/StatusBadge'
import './BiConditionalDeliveryPanel.css'

interface RuleForm {
  name: string
  report_id: string
  diff_threshold_pct: number
  recipients: string
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

  const reglas = data?.items ?? []

  return (
    <Card>
      <Section
        title={<span className="bi-titulo"><Bell size={16} aria-hidden />{t('prediccion_bi.entrega_titulo')}</span>}
        subtitle={t('biconditionaldelivery.envia_reportes_solo_cuando_los_datos_cambian')}
      >
        {/* Create rule form */}
        <div className="bicodepa-form">
          <Input label={t('prediccion_bi.nombre_regla')} value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <Input label={t('prediccion_bi.informe')} value={form.report_id}
            onChange={e => setForm(f => ({ ...f, report_id: e.target.value }))} />
          <Input label={t('prediccion_bi.umbral')} type="number" value={form.diff_threshold_pct}
            onChange={e => setForm(f => ({ ...f, diff_threshold_pct: Number(e.target.value) }))} />
          <Input label={t('prediccion_bi.destinatarios')} placeholder={t('prediccion_bi.destinatarios_ph')} value={form.recipients}
            onChange={e => setForm(f => ({ ...f, recipients: e.target.value }))} />
          <Button icon={<Plus size={14} />}
            onClick={() => createMutation.mutate({
              name:              form.name,
              report_id:         form.report_id,
              diff_threshold_pct: form.diff_threshold_pct,
              schedule_cron:     '0 8 * * 1',
              recipients:        form.recipients ? form.recipients.split(',').map(r => r.trim()) : [],
            })}
            disabled={!form.name || !form.report_id}
            loading={createMutation.isPending}
          >
            {t('prediccion_bi.crear_regla')}
          </Button>
        </div>

        {/* Rules list */}
        {isLoading ? (
          <div className="bicodepa-cargando"><Spinner /></div>
        ) : reglas.length === 0 ? (
          <EmptyState icon={<Bell size={28} />} title={t('prediccion_bi.sin_reglas')} description={t('prediccion_bi.sin_reglas_desc')} />
        ) : (
          <ul className="bicodepa-lista">
            {reglas.map(rule => {
              const evaluacion = evaluateResult[rule.id]
              return (
                <li key={rule.id} className="bicodepa-regla">
                  <div className="u-flex1-min0">
                    <div className="u-text1-base-600">{rule.name}</div>
                    <div className="u-text3-xs-mt2">
                      {/* La regla no guarda un `condition_type`: la condición es métrica + operador + valor, si la hay. */}
                      {rule.report_id}
                      {rule.condition_metric && ` · ${rule.condition_metric} ${rule.condition_operator ?? ''} ${rule.condition_value ?? ''}`}
                      {' · '}{t('prediccion_bi.umbral_n', { n: rule.diff_threshold_pct })}
                    </div>
                  </div>
                  <div className="u-row-center-8">
                    {evaluacion && (
                      <StatusBadge kind={evaluacion.should_deliver ? 'success' : 'neutral'} caps={false}>
                        {evaluacion.should_deliver ? t('prediccion_bi.se_enviaria') : t('prediccion_bi.sin_cambios')}
                      </StatusBadge>
                    )}
                    {!rule.enabled && <StatusBadge kind="neutral" caps={false}>{t('prediccion_bi.desactivada')}</StatusBadge>}
                    <button type="button" aria-label={t('biconditionaldelivery.evaluar_ahora')}
                      onClick={() => evaluateMutation.mutate(rule.id)}
                      title={t('biconditionaldelivery.evaluar_ahora')}
                      className="bicodepa-icono"
                    >
                      <Play size={16} aria-hidden />
                    </button>
                    <button type="button" className={`bicodepa-icono${rule.enabled ? ' bicodepa-icono--activo' : ''}`}
                      onClick={() => toggleMutation.mutate({ id: rule.id, enabled: !rule.enabled })}
                      aria-pressed={rule.enabled}
                      aria-label={rule.enabled ? t('prediccion_bi.desactivar') : t('prediccion_bi.activar')}
                      title={rule.enabled ? t('prediccion_bi.desactivar') : t('prediccion_bi.activar')}
                    >
                      {rule.enabled ? <ToggleRight size={20} aria-hidden /> : <ToggleLeft size={20} aria-hidden />}
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Section>
    </Card>
  )
}
