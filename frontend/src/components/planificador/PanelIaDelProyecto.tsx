/**
 * PanelIaDelProyecto — la IA de proyectos en pantalla (rev. 173). Antes eran
 * endpoints sin interfaz: salud y riesgo de retraso (GET /activity/projects/{id}/health),
 * simulación what-if (POST …/simulate), estimación de horas
 * (POST /ai-planning/estimate/{tarea}) y persona sugerida (POST /semantic/suggest/task).
 * Las sugerencias no se aplican solas: se aceptan una a una.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, HeartPulse, Sparkles, UserCheck } from 'lucide-react'
import { iaDeProyectosApi, tasksApi, type EstimacionIa, type Simulacion } from '../../services/api'
import type { SugerenciaDeAsignacion } from '../../services/api/tipos-rendimiento'
import { Button, EmptyState, KpiCard, Spinner, TablaSimple } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr, fmtDate } from '../../utils/helpers'
import { DEFAULT_PAGE_SIZE } from '../../constants/pagination'
import './planificador.css'

const COLOR_SEMAFORO: Record<string, 'danger' | 'warning' | undefined> = { red: 'danger', yellow: 'warning' }

export default function PanelIaDelProyecto({ projectId }: { projectId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const dinero = useFormatoMoneda()
  const edita = useAuth().hasRole('admin', 'pm')
  const [sim, setSim] = useState({ delay_days: 0, compress_pct: 0, extra_horas: 0 })
  const [resultado, setResultado] = useState<Simulacion | null>(null)
  const [estimaciones, setEstimaciones] = useState<Record<string, EstimacionIa>>({})
  const [personas, setPersonas] = useState<Record<string, SugerenciaDeAsignacion>>({})

  const { data: salud, isLoading } = useQuery({
    queryKey: ['salud-proyecto', projectId],
    queryFn: () => iaDeProyectosApi.salud(projectId),
    enabled: !!projectId,
  })
  const { data: tareas = [] } = useQuery({
    queryKey: ['tasks', 'ia', projectId],
    queryFn: () => tasksApi.list({ project_id: projectId, status: 'backlog,todo,in_progress,blocked', page_size: DEFAULT_PAGE_SIZE }).then(r => r.data),
    enabled: !!projectId,
  })
  const onError = (e: unknown) => toast.error(extractErr(e, t('planificador.error_generico')))

  const simular = useMutation({
    mutationFn: () => iaDeProyectosApi.simular(projectId, {
      delay_days: sim.delay_days || undefined, compress_pct: sim.compress_pct || undefined,
      add_resources: sim.extra_horas ? [{ hours_per_week: sim.extra_horas }] : undefined,
    }),
    onSuccess: setResultado,
    onError,
  })
  const estimar = useMutation({
    mutationFn: (id: string) => iaDeProyectosApi.estimar(id),
    onSuccess: r => setEstimaciones(e => ({ ...e, [r.task_id]: r })),
    onError,
  })
  const sugerir = useMutation({
    mutationFn: (x: { id: string; title: string; description?: string | null }) =>
      iaDeProyectosApi.sugerirPersona({ title: x.title, description: x.description ?? undefined, project_id: projectId }).then(r => ({ id: x.id, r })),
    onSuccess: ({ id, r }) => setPersonas(p => ({ ...p, [id]: r })),
    onError,
  })
  const aplicar = useMutation({
    mutationFn: ({ id, cambios }: { id: string; cambios: { estimated_hours?: number; assignee_id?: string } }) =>
      tasksApi.update(id, cambios),
    onSuccess: (_r, v) => {
      toast.success(t('planificador.ia_aplicada'))
      if (v.cambios.estimated_hours) iaDeProyectosApi.aceptarEstimacion(v.id, true).catch(() => undefined)
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['plan', projectId] })
    },
    onError,
  })

  if (isLoading) return <Spinner />
  const s = salud?.current

  return (
    <div className="plan-stack">
      {s && (
        <div className="plan-kpis">
          <KpiCard icon={<HeartPulse size={16} />} label={t('planificador.salud')} value={Math.round(s.score)}
            sub={t(`planificador.semaforo_${s.traffic_light}`)}
            danger={COLOR_SEMAFORO[s.traffic_light] === 'danger'} warning={COLOR_SEMAFORO[s.traffic_light] === 'warning'} />
          <KpiCard label={t('planificador.salud_plazo')} value={Math.round(s.schedule_score)} sub={t('planificador.tareas_vencidas', { n: s.overdue_tasks })} />
          <KpiCard label={t('planificador.salud_presupuesto')} value={Math.round(s.budget_score)} />
          <KpiCard label={t('planificador.salud_calidad')} value={Math.round(s.quality_score)} />
          <KpiCard label={t('planificador.salud_velocidad')} value={Math.round(s.velocity_score)} />
        </div>
      )}

      <div className="plan-card plan-stack">
        <h3 className="plan-card__titulo"><Sparkles size={14} />{t('planificador.simulacion')}</h3>
        <div className="plan-form">
          <label>{t('planificador.sim_retraso')}
            <input type="number" min={0} className="plan-input" value={sim.delay_days} onChange={e => setSim(x => ({ ...x, delay_days: Number(e.target.value) }))} />
          </label>
          <label>{t('planificador.sim_compresion')}
            <input type="number" min={0} max={90} className="plan-input" value={sim.compress_pct} onChange={e => setSim(x => ({ ...x, compress_pct: Number(e.target.value) }))} />
          </label>
          <label>{t('planificador.sim_refuerzo')}
            <input type="number" min={0} className="plan-input" value={sim.extra_horas} onChange={e => setSim(x => ({ ...x, extra_horas: Number(e.target.value) }))} />
          </label>
        </div>
        <div className="plan-row"><Button size="sm" loading={simular.isPending} onClick={() => simular.mutate()}>{t('planificador.simular')}</Button></div>
        {resultado && (
          <div className="plan-stack">
            <div className="plan-kpis">
              <KpiCard label={t('planificador.sim_fin_base')} value={fmtDate(resultado.simulation.base_end_date)} />
              <KpiCard label={t('planificador.sim_fin_simulado')} value={fmtDate(resultado.simulation.simulated_end_date)}
                sub={t('planificador.sim_dias', { n: resultado.simulation.days_delta })} danger={resultado.simulation.days_delta > 0} />
              <KpiCard label={t('planificador.sim_coste')} value={dinero(resultado.simulation.cost_delta_eur)} />
              <KpiCard label={t('planificador.sim_en_riesgo')} value={resultado.simulation.at_risk_tasks} warning={resultado.simulation.at_risk_tasks > 0} />
            </div>
            {/* `notes` del servidor viene en texto libre en inglés: no se pinta; las cifras de arriba dicen lo mismo. */}
          </div>
        )}
      </div>

      <div className="plan-card plan-stack">
        <h3 className="plan-card__titulo"><Brain size={14} />{t('planificador.ia_tareas')}</h3>
        {tareas.length === 0 ? <EmptyState title={t('planificador.sin_tareas_abiertas')} /> : (
          <div className="plan-tabla-scroll">
            <TablaSimple claseTabla="plan-tabla">
              <thead><tr><th>{t('planificador.col_tarea')}</th><th>{t('planificador.ia_estimacion')}</th><th>{t('planificador.ia_persona')}</th></tr></thead>
              <tbody>
                {tareas.map(x => {
                  const e = estimaciones[x.id]
                  const p = personas[x.id]
                  return (
                    <tr key={x.id}>
                      <td>{x.code} {x.title}<div className="plan-muted">{x.estimated_hours ? t('planificador.horas_actuales', { n: x.estimated_hours }) : t('planificador.sin_horas')}</div></td>
                      <td>
                        {e ? (
                          <span className="plan-stack">
                            <span>{t('planificador.ia_horas', { n: e.estimated_hours, c: e.confidence_pct })}</span>
                            <span className="plan-muted">{e.reasoning}</span>
                            {edita && <Button size="xs" variant="subtle" onClick={() => aplicar.mutate({ id: x.id, cambios: { estimated_hours: e.estimated_hours } })}>{t('planificador.aceptar')}</Button>}
                          </span>
                        ) : <Button size="xs" variant="subtle" icon={<Brain size={12} />} loading={estimar.isPending && estimar.variables === x.id} onClick={() => estimar.mutate(x.id)}>{t('planificador.estimar')}</Button>}
                      </td>
                      <td>
                        {p ? (
                          <span className="plan-stack">
                            <span>{p.suggested_user_name ?? t('planificador.sin_sugerencia')} {p.suggested_user_id && `· ${Math.round((p.confidence ?? 0) * 100)} %`}</span>
                            <span className="plan-muted">{p.reasoning}</span>
                            {edita && p.suggested_user_id && <Button size="xs" variant="subtle" onClick={() => aplicar.mutate({ id: x.id, cambios: { assignee_id: p.suggested_user_id! } })}>{t('planificador.asignar')}</Button>}
                          </span>
                        ) : <Button size="xs" variant="subtle" icon={<UserCheck size={12} />} loading={sugerir.isPending && sugerir.variables?.id === x.id} onClick={() => sugerir.mutate({ id: x.id, title: x.title, description: x.description })}>{t('planificador.sugerir_persona')}</Button>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </div>
    </div>
  )
}
