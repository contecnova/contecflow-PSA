/**
 * Simulador de flujos y análisis de cuellos de botella.
 * Troceado de ApprovalsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { type CSSProperties, useId, useState } from 'react'
import { extractErr } from '../../utils/helpers'
import { useTono } from '../../hooks/useOrgSettings'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation } from '@tanstack/react-query'
import { approvalsApi } from '../../services/api'
import { settingsApi } from '../../services/settingsApi'
import { Clock as ClockIcon, BarChart3, Layers, RefreshCw, AlertTriangle, Download } from 'lucide-react'
import { Button, EmptyState, KpiCard, SelectorDePeriodo, Select, Input } from '../../components/ui'
import { usePeriodo } from '../../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo, formatearTramo } from '../../utils/periodo'
import { useAppT } from '../../i18n/AppLangContext'
import { UserSelect } from '../../components/ui/EntitySelect'
import {
  type ApprovalWorkflow,
  type BottleneckItem,
  type BottlenecksResponse,
  type BottleneckSummary,
  entityLabels,
  nivel,
  type Recommendation,
  type SimulationPayload,
  type SimulationResult,
  type T,
  type WeeklyRejection,
  type WorkflowAtRisk,
} from './compartido'

// ── Simulador ─────────────────────────────────────────────────────────────────
export function WorkflowSimulatorTab() {
  const idCampo = useId()
  const t = useAppT()
  const [entityType, setEntityType] = useState('document')
  const [category, setCategory] = useState('')
  const [department, setDepartment] = useState('')
  const [amount, setAmount] = useState('')
  const [requestedByUserId, setRequestedByUserId] = useState('')
  const [result, setResult] = useState<SimulationResult | null>(null)
  const toast = useToast()
  const { data: depts = [] } = useQuery({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })

  const { mutate: simulate, isPending } = useMutation({
    mutationFn: (payload: SimulationPayload) => approvalsApi.simulate(payload),
    onSuccess: (res) => setResult(res.data),
    onError: e => toast.error(extractErr(e, t('approvals.error_simular'))),
  })
  const id = (k: string) => `${idCampo}-${k}`
  const accion = (a: string) => a === 'escalate' ? t('approvals.timeout_escalate') : a === 'auto_approve' ? t('approvals.timeout_auto_approve') : a === 'reject' ? t('approvals.timeout_reject') : a

  return (
    <div className="apv-simulador">
      <div className="ds-card apv-tarjeta">
        <div className="apv-tarjeta__texto">{t('approvals.simula_antes_de_publicar_para_validar_ruta')}</div>
        <div className="apv-simulador__rejilla">
          <Select label={t('approvals.entity_type')} placeholder={false} id={id('tipo')} value={entityType} onChange={e => setEntityType(e.target.value)}>
              {['document', 'expense', 'timesheet', 'milestone', 'purchase'].map(k => <option key={k} value={k}>{entityLabels(t)[k].label}</option>)}
            </Select>
          <Input label={t('approvals.categoria')} id={id('cat')} value={category} onChange={e => setCategory(e.target.value)} placeholder={t('approvals.categoria_ejemplo')} />
          <Select label={t('approvals.department')} placeholder={false} id={id('dep')} value={department} onChange={e => setDepartment(e.target.value)}>
              <option value="">{t('approvals.sin_departamento')}</option>
              {depts.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
            </Select>
          <Input label={t('approvals.importe')} id={id('imp')} value={amount} onChange={e => setAmount(e.target.value)} type="number" />
          <div className="apv-span-2">
            <label htmlFor={id('sol')} className="apv-label">{t('approvals.solicitante_opcional')}</label>
            <span id={id('sol')}><UserSelect value={requestedByUserId} onChange={setRequestedByUserId} placeholder={t('approvals.elige_a_quien')} /></span>
          </div>
        </div>
        <div className="apv-mt-8">
          <Button onClick={() => simulate({ entity_type: entityType, context: { category, department, amount: amount ? Number(amount) : undefined, requested_by_user_id: requestedByUserId || undefined } })} loading={isPending}>{t('approvals.simular_flujo')}</Button>
        </div>
      </div>

      {result && (
        <div className="ds-card apv-tarjeta" aria-live="polite">
          {!result.matched ? (
            <div className="apv-aviso">{t('approvals.sin_coincidencia')} {result.reason}</div>
          ) : (
            <>
              <div className="apv-tarjeta__titulo">{t('approvals.flujo_seleccionado', { nombre: result.workflow?.name ?? '' })}</div>
              <div className="apv-tarjeta__nota">{t('approvals.sla_estimado', { h: result.estimated_total_timeout_hours })}</div>
              <div className="u-stack-8">
                {(result.route || []).map(step => (
                  <div key={step.step_order} className="apv-ruta">
                    <div className="u-sm-700">{t('approvals.step_n', { order: step.step_order })}: {step.step_name}</div>
                    <div className="u-text2-xs">{t('approvals.ruta_paso', { aprobador: step.resolved_approver || t('approvals.no_resoluble'), h: step.timeout_hours, accion: accion(step.on_timeout) })}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function exportBottlenecksCSV(t: T, items: BottleneckItem[], recommendations: Recommendation[], periodo: string, workflowFilterName: string | null) {
  const header = [t('approvals.cb_flujo'), t('approvals.cb_paso'), t('approvals.cb_nombre_paso'), t('approvals.cb_decisiones'), t('approvals.cb_media_h'),
    t('approvals.cb_rechazo'), t('approvals.cb_pendientes'), t('approvals.cb_riesgo_sla'), t('approvals.cb_puntuacion')]
  const rows = items.map(it => [
    it.workflow_name, it.step_order, it.step_name, it.decisions_total, it.avg_decision_time_hours,
    it.rejection_rate_pct, it.pending_count, it.sla_risk_pct, it.bottleneck_score,
  ])

  const recHeader = [t('approvals.cb_prioridad'), t('approvals.cb_titulo'), t('approvals.cb_accion'), t('approvals.cb_porque')]
  const recRows = recommendations.map(r => [r.priority, r.title, r.action, r.why])

  const escape = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const toCSV = (hdr: unknown[], data: unknown[][]) => [hdr, ...data].map(r => r.map(escape).join(',')).join('\n')

  const label = workflowFilterName ? t('approvals.cb_flujo_nombre', { nombre: workflowFilterName }) : t('approvals.todos_los_flujos')
  const content = [
    `# ${t('approvals.cb_titulo_csv', { ambito: label, periodo })}`,
    '',
    `## ${t('approvals.cb_seccion_pasos')}`,
    toCSV(header, rows),
    '',
    `## ${t('approvals.cb_seccion_recomendaciones')}`,
    toCSV(recHeader, recRows),
  ].join('\n')

  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `bottlenecks_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export function WorkflowBottlenecksTab() {
  const t = useAppT()
  const tono = useTono()
  const idCampo = useId()
  // Periodo libre (16-11-2026): antes 30/60/90/180 días propios y tendencia semanal fija.
  const periodo = usePeriodo({ defecto: '90d', granularidades: CON_HORA, prefijo: 'cb_' })
  const [workflowFilter, setWorkflowFilter] = useState('')

  const { data: workflowsData = [] } = useQuery<ApprovalWorkflow[]>({
    queryKey: ['approval-workflows'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  const params = { ...periodo.params, ...(workflowFilter ? { workflow_id: workflowFilter } : {}) }
  const { data, isLoading, refetch, isFetching, error } = useQuery<BottlenecksResponse>({
    queryKey: ['approval-bottlenecks', periodo.params, workflowFilter],
    queryFn: () => approvalsApi.bottlenecks(params).then(r => r.data),
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(error)
  const textoDelPeriodo = `${periodo.fechas.desde} – ${periodo.fechas.hasta}`

  const items: BottleneckItem[] = data?.items || []
  const summary: BottleneckSummary = data?.summary || {
    steps_analyzed: items.length,
    critical_steps: items.filter(it => it.is_critical).length,
    pending_total: items.reduce((acc: number, it) => acc + (it.pending_count || 0), 0),
    avg_decision_time_hours: items.length ? Number((items.reduce((acc: number, it) => acc + (it.avg_decision_time_hours || 0), 0) / items.length).toFixed(2)) : 0,
  }
  const topWorkflows: WorkflowAtRisk[] = data?.top_workflows || []
  // Serie completa del periodo: se listan los últimos tramos con decisiones.
  const weeklyTrend: WeeklyRejection[] = (data?.trend || []).filter(row => row.decisions > 0)
  const recommendations: Recommendation[] = data?.recommendations || []

  const selectedWorkflowName = workflowFilter
    ? (workflowsData.find(w => w.id === workflowFilter)?.name || workflowFilter)
    : null

  return (
    <div className="u-stack-12">
      <div className="ds-card apv-barra">
        <span className="u-text2-sm">{t('approvals.ventana')}</span>
        <SelectorDePeriodo {...periodo.selector} />
        <Select label={t('approvals.flujo')} placeholder={false} id={`${idCampo}-flujo`} value={workflowFilter} onChange={e => setWorkflowFilter(e.target.value)}>
          <option value="">{t('approvals.todos_los_flujos')}</option>
          {workflowsData.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </Select>
        <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetch()} loading={isFetching}>{t('approvals.actualizar')}</Button>
        {items.length > 0 && (
          <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={() => exportBottlenecksCSV(t, items, recommendations, textoDelPeriodo, selectedWorkflowName)}>
            {t('approvals.exportar_csv')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="apv-cargando apv-cargando--compacto" role="status">{t('approvals.cargando_cuellos_de_botella')}</div>
      ) : errorDePeriodo ? (
        <div className="ds-card">
          <EmptyState icon={<AlertTriangle size={28} />} title={t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
        </div>
      ) : items.length === 0 ? (
        <div className="ds-card">
          <EmptyState icon={<BarChart3 size={28} />} title={t('approvals.sin_datos_suficientes')} description={t('approvals.sin_decisiones_historicas')} />
        </div>
      ) : (
        <>
          <div className="ds-grid-stats">
            <KpiCard icon={<Layers size={16} />} label={t('approvals.cb_pasos_analizados')} value={summary.steps_analyzed} />
            <KpiCard icon={<AlertTriangle size={16} />} label={t('approvals.cb_pasos_criticos')} value={summary.critical_steps} danger={summary.critical_steps > 0} />
            <KpiCard icon={<ClockIcon size={16} />} label={t('approvals.cb_pendientes_total')} value={summary.pending_total} warning={summary.pending_total > 0} />
            <KpiCard icon={<BarChart3 size={16} />} label={t('approvals.cb_decision_media')} value={summary.avg_decision_time_hours} />
          </div>

          {(topWorkflows.length > 0 || weeklyTrend.length > 0) && (
            <div className="apv-dos-columnas">
              <div className="ds-card apv-kpi">
                <div className="apv-eyebrow">{t('approvals.cb_flujos_en_riesgo')}</div>
                <div className="u-stack-8">
                  {topWorkflows.map((wf, idx) => (
                    <div key={wf.workflow_id || idx} className="apv-riesgo">
                      <span className="u-sm-700">{wf.workflow_name}</span>
                      <span className="u-text2-xs">{t('approvals.cb_puntuacion_n', { n: wf.avg_bottleneck_score })}</span>
                      <span className={`apv-xs ${nivel(tono('aprobacion_riesgo_sla', wf.max_sla_risk_pct))}`}>{t('approvals.cb_sla_n', { n: wf.max_sla_risk_pct })}</span>
                      <span className="apv-xs apv-nivel--medio">{t('approvals.cb_pend_n', { n: wf.pending_total })}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="ds-card apv-kpi">
                <div className="apv-eyebrow">{t('approvals.cb_tendencia_rechazo')}</div>
                {weeklyTrend.length === 0 ? (
                  <div className="u-text2-sm">{t('approvals.sin_tendencia_semanal_disponible')}</div>
                ) : (
                  <div className="u-stack-6">
                    {weeklyTrend.slice(-8).map(row => (
                      <div key={row.t} className="apv-tendencia">
                        <span className="u-text2-mono-xs">{formatearTramo(row.t, periodo.granularidad)}</span>
                        <div className="apv-tendencia__pista" role="img" aria-label={t('approvals.cb_rechazo_semana', { semana: formatearTramo(row.t, periodo.granularidad, true), pct: row.rejection_rate_pct })}>
                          <div className={`apv-tendencia__barra ${nivel(tono('aprobacion_rechazo', row.rejection_rate_pct))}`}
                            style={{ '--apv-pct': `${Math.min(100, row.rejection_rate_pct)}%` } as CSSProperties} />
                        </div>
                        <span className="u-text2-xs">{row.rejection_rate_pct}%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {recommendations.length > 0 && (
            <div className="ds-card apv-kpi">
              <div className="apv-eyebrow">{t('approvals.cb_acciones_recomendadas')}</div>
              <div className="u-stack-8">
                {recommendations.map((rec, idx) => (
                  <div key={`${rec.title}-${idx}`} className="apv-recomendacion">
                    <div className="u-row-center-8">
                      <span className={`apv-prioridad ${rec.priority === 'high' ? 'apv-nivel--alto' : 'apv-nivel--medio'}`}>{t(`approvals.prioridad_${rec.priority}`, rec.priority)}</span>
                      <span className="u-sm-700">{rec.title}</span>
                    </div>
                    <div className="apv-recomendacion__accion">{rec.action}</div>
                    <div className="u-text3-xs-mt2">{rec.why}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="ds-card apv-tabla" role="table" aria-label={t('approvals.cb_seccion_pasos')}>
            <div className="apv-tabla__fila apv-tabla__fila--cabecera" role="row">
              {['cb_paso', 'cb_decis', 'cb_media_h', 'cb_rechazo', 'cb_pendientes', 'cb_riesgo_sla', 'cb_puntuacion'].map(k => (
                <span key={k} role="columnheader">{t(`approvals.${k}`)}</span>
              ))}
            </div>
            {items.slice(0, 30).map((it) => (
              <div key={`${it.workflow_id}-${it.step_order}`} className="apv-tabla__fila" role="row">
                <div role="cell">
                  <div className="u-sm-700">{it.workflow_name}</div>
                  <div className="u-text3-xs">{t('approvals.step_n', { order: it.step_order })}: {it.step_name}</div>
                </div>
                <span className="u-sm" role="cell">{it.decisions_total}</span>
                <span className="u-sm" role="cell">{it.avg_decision_time_hours}</span>
                <span role="cell" className={`apv-sm ${(it.rejection_tone ?? tono('aprobacion_rechazo', it.rejection_rate_pct)) === 'danger' ? 'apv-nivel--alto' : 'apv-nivel--neutro'}`}>{it.rejection_rate_pct}%</span>
                <span role="cell" className={`apv-sm ${it.pending_count > 0 ? 'apv-nivel--medio' : 'apv-nivel--neutro'}`}>{it.pending_count}</span>
                <span role="cell" className={`apv-sm ${nivel(it.sla_risk_tone ?? tono('aprobacion_riesgo_sla', it.sla_risk_pct))}`}>{it.sla_risk_pct}%</span>
                <span className="u-sm-700" role="cell">{it.bottleneck_score}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
