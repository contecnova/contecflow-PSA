/**
 * ModalAutoPlanificar — «Auto-planificar» del Gantt con el motor determinista
 * (16-11-2026).
 *
 * Vista previa de GET /planning/projects/{id}/schedule de cada proyecto: qué
 * fechas quedarían (fechas tempranas), cuántas tareas cambian y el fin del
 * proyecto frente a su plazo. «Aplicar» llama a POST .../schedule/apply de los
 * proyectos con cambios. La sugerencia por IA queda como opción secundaria.
 *
 * Mismo criterio que `aplicar_plan` del servidor: cambia toda tarea no
 * terminada cuyas fechas guardadas no coinciden con las tempranas.
 */
import { useMemo } from 'react'
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CalendarCheck, Sparkles } from 'lucide-react'
import { planificacionApi, type NodoDelPlan, type PlanDelProyecto } from '../../services/api'
import { Button, Modal, Spinner, TablaSimple } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr as extraerError, fmtDate } from '../../utils/helpers'
import { STALE_SHORT_MS } from '../../constants/timings'
import './ModalAutoPlanificar.css'

interface ProyectoCorto { id: string; code?: string; name?: string }

interface Props {
  open: boolean
  onClose: () => void
  projectIds: string[]
  projects: ProyectoCorto[]
  /** Abre la sugerencia por IA (opción secundaria). */
  onSugerenciasIa?: () => void
}

const dia = (s: string | null | undefined) => (s ? String(s).slice(0, 10) : null)

/** Tareas que `schedule/apply` movería. */
export function nodosQueCambian(plan: PlanDelProyecto | undefined): NodoDelPlan[] {
  if (!plan) return []
  return plan.nodes.filter(n => n.status !== 'done'
    && (dia(n.start_date) !== dia(n.early_start) || dia(n.due_date) !== dia(n.early_finish)))
}

export default function ModalAutoPlanificar({ open, onClose, projectIds, projects, onSugerenciasIa }: Props) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()

  const consultas = useQueries({
    queries: projectIds.map(pid => ({
      queryKey: ['plan', pid],
      queryFn: () => planificacionApi.plan(pid),
      enabled: open,
      staleTime: STALE_SHORT_MS,
      retry: false,
    })),
  })
  const cargando = consultas.some(c => c.isLoading)
  const marca = consultas.map(c => c.dataUpdatedAt).join(',')

  const bloques = useMemo(() => projectIds.map((pid, i) => {
    const plan = consultas[i]?.data
    return { pid, plan, cambios: nodosQueCambian(plan), proyecto: projects.find(p => String(p.id) === pid) }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `marca` resume los datos de las consultas
  }), [projectIds, projects, marca])

  const totalCambios = bloques.reduce((s, b) => s + b.cambios.length, 0)
  const totalTareas = bloques.reduce((s, b) => s + (b.plan?.nodes.length ?? 0), 0)

  const aplicar = useMutation({
    mutationFn: async () => {
      let movidas = 0
      for (const b of bloques) {
        if (!b.cambios.length) continue
        movidas += (await planificacionApi.replanificar(b.pid)).total_moved
      }
      return movidas
    },
    onSuccess: n => {
      toast.success(t('planificador.replanificado', { n }))
      qc.invalidateQueries({ queryKey: ['plan'] })
      qc.invalidateQueries({ queryKey: ['gantt-tasks'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      onClose()
    },
    onError: e => toast.error(extraerError(e, t('planificador.error_generico'))),
  })

  return (
    <Modal open={open} onClose={onClose} size="lg"
      title={t('pagina_gantt.vista_previa_titulo')} subtitle={t('pagina_gantt.vista_previa_sub')}>
      {cargando ? <Spinner /> : (
        <div className="autoplan-stack">
          <p className="autoplan-resumen">
            <CalendarCheck size={14} aria-hidden />
            {t('pagina_gantt.tareas_que_cambian', { n: totalCambios, total: totalTareas })}
          </p>

          {bloques.map(({ pid, plan, cambios, proyecto }) => {
            const retraso = plan?.finish_vs_deadline_days ?? null
            return (
              <section key={pid} className="autoplan-proyecto">
                {projectIds.length > 1 && (
                  <h3 className="autoplan-proyecto__titulo">
                    {proyecto ? `${proyecto.code ?? ''} — ${proyecto.name ?? ''}` : pid}
                  </h3>
                )}
                {!plan || plan.nodes.length === 0 ? (
                  <p className="autoplan-muted">{t('pagina_gantt.sin_plan')}</p>
                ) : (
                  <>
                    <div className="autoplan-kpis">
                      <span>{t('planificador.fin_previsto')}: <strong>{fmtDate(plan.project_finish)}</strong></span>
                      <span>
                        {t('planificador.plazo')}: <strong>{plan.deadline ? fmtDate(plan.deadline) : t('planificador.sin_plazo')}</strong>
                        {retraso != null && (
                          <span className={retraso > 0 ? 'autoplan-tarde' : 'autoplan-ok'}>
                            {' · '}{retraso > 0 ? t('planificador.dias_tarde', { n: retraso }) : t('planificador.dias_margen', { n: -retraso })}
                          </span>
                        )}
                      </span>
                    </div>
                    {plan.cycle.length > 0 && (
                      <div className="autoplan-aviso" role="alert">
                        <AlertTriangle size={14} aria-hidden /> {t('planificador.ciclo_detectado', { n: plan.cycle.length })}
                      </div>
                    )}
                    {cambios.length === 0 ? (
                      <p className="autoplan-muted">{t('pagina_gantt.sin_cambios')}</p>
                    ) : (
                      <div className="autoplan-scroll">
                        <TablaSimple claseTabla="contecflow-table">
                          <thead>
                            <tr>
                              <th>{t('planificador.col_tarea')}</th>
                              <th>{t('pagina_gantt.col_actual')}</th>
                              <th>{t('pagina_gantt.col_nuevas')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {cambios.map(n => (
                              <tr key={n.id}>
                                <td>
                                  <span className="autoplan-codigo">{n.code}</span> {n.title}
                                  {n.is_critical && <span className="autoplan-critica"> · {t('ganttchart.ruta_critica')}</span>}
                                </td>
                                <td className="autoplan-muted">
                                  {n.start_date || n.due_date
                                    ? `${fmtDate(n.start_date)} → ${fmtDate(n.due_date)}`
                                    : t('pagina_gantt.sin_fecha')}
                                </td>
                                <td>{fmtDate(n.early_start)} → {fmtDate(n.early_finish)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </TablaSimple>
                      </div>
                    )}
                  </>
                )}
              </section>
            )
          })}

          <div className="autoplan-pie">
            {onSugerenciasIa ? (
              <Button variant="ghost" size="sm" icon={<Sparkles size={13} />} onClick={onSugerenciasIa}
                title={t('pagina_gantt.sugerencias_ia_ayuda')}>
                {t('pagina_gantt.sugerencias_ia')}
              </Button>
            ) : <span />}
            <div className="autoplan-pie__acciones">
              <Button variant="secondary" onClick={onClose}>{t('pagina_gantt.cancelar')}</Button>
              <Button icon={<CalendarCheck size={14} />} loading={aplicar.isPending}
                disabled={totalCambios === 0} onClick={() => aplicar.mutate()}>
                {t('pagina_gantt.aplicar', { n: totalCambios })}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}
