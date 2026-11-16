/**
 * PanelDelPlan — camino crítico del proyecto (rev. 173).
 *
 * Fin previsto frente al plazo, camino crítico, holguras de cada tarea y sus
 * restricciones de fecha (editables), con el botón «Replanificar» que mueve
 * las tareas pendientes a sus fechas tempranas. Todo viene de
 * GET /planning/projects/{id}/schedule (cuatro tipos de vínculo, desfases,
 * calendario de la empresa y de cada persona).
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CalendarClock, GitBranch, RefreshCw } from 'lucide-react'
import { planificacionApi, tasksApi, type NodoDelPlan } from '../../services/api'
import { Button, EmptyState, KpiCard, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr as extraerError, fmtDate } from '../../utils/helpers'
import './planificador.css'

const RESTRICCIONES = ['', 'snet', 'mso', 'fnlt', 'mfo'] as const

export default function PanelDelPlan({ projectId }: { projectId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const puedeEditar = useAuth().hasRole('admin', 'pm')

  const { data: plan, isLoading } = useQuery({
    queryKey: ['plan', projectId],
    queryFn: () => planificacionApi.plan(projectId),
    enabled: !!projectId,
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['plan', projectId] })
    qc.invalidateQueries({ queryKey: ['gantt-tasks'] })
    qc.invalidateQueries({ queryKey: ['tasks'] })
  }

  const replanificar = useMutation({
    mutationFn: () => planificacionApi.replanificar(projectId),
    onSuccess: r => { toast.success(t('planificador.replanificado', { n: r.total_moved })); refrescar() },
    onError: e => toast.error(extraerError(e, t('planificador.error_generico'))),
  })

  const restriccion = useMutation({
    mutationFn: ({ id, tipo, fecha }: { id: string; tipo: string; fecha: string | null }) =>
      tasksApi.update(id, { constraint_type: (tipo || null) as NodoDelPlan['constraint_type'], constraint_date: tipo ? fecha : null }),
    onSuccess: () => { toast.success(t('planificador.restriccion_guardada')); refrescar() },
    onError: e => toast.error(extraerError(e, t('planificador.error_generico'))),
  })

  if (isLoading) return <Spinner />
  if (!plan || plan.nodes.length === 0) {
    return <EmptyState title={t('planificador.sin_tareas')} description={t('planificador.sin_tareas_desc')} />
  }

  const criticas = plan.nodes.filter(n => n.is_critical).length
  const retraso = plan.finish_vs_deadline_days

  return (
    <div className="plan-stack">
      <div className="plan-row plan-row--between">
        <span className="plan-muted">
          {t('planificador.calendario_resumen', {
            dias: (plan.calendar?.workdays ?? []).map(d => t(`planificador.dia_${d}`)).join(', '),
            horas: plan.calendar?.hours_per_day ?? 0,
            festivos: plan.calendar?.holidays.length ?? 0,
          })}
        </span>
        {puedeEditar && (
          <Button size="sm" icon={<RefreshCw size={13} />} loading={replanificar.isPending}
            onClick={() => replanificar.mutate()} title={t('planificador.replanificar_ayuda')}>
            {t('planificador.replanificar')}
          </Button>
        )}
      </div>

      <div className="plan-kpis">
        <KpiCard icon={<CalendarClock size={16} />} label={t('planificador.fin_previsto')} value={fmtDate(plan.project_finish)} sub={t('planificador.dias_laborables', { n: plan.project_duration_days })} />
        <KpiCard icon={<CalendarClock size={16} />} label={t('planificador.plazo')} value={plan.deadline ? fmtDate(plan.deadline) : t('planificador.sin_plazo')}
          sub={retraso == null ? undefined : retraso > 0 ? t('planificador.dias_tarde', { n: retraso }) : t('planificador.dias_margen', { n: -retraso })}
          danger={retraso != null && retraso > 0} />
        <KpiCard icon={<GitBranch size={16} />} label={t('planificador.tareas_criticas')} value={criticas} sub={t('planificador.de_total', { n: plan.nodes.length })} warning={criticas > 0} />
      </div>

      {plan.cycle.length > 0 && (
        <div className="plan-aviso plan-aviso--peligro" role="alert">
          <AlertTriangle size={14} /> {t('planificador.ciclo_detectado', { n: plan.cycle.length })}
        </div>
      )}
      {plan.critical_path.length > 0 && (
        <div className="plan-card">
          <h3 className="plan-card__titulo">{t('planificador.camino_critico')}</h3>
          <div className="plan-row">{plan.critical_path.map(c => <span key={c} className="plan-chip plan-chip--activa">{c}</span>)}</div>
        </div>
      )}

      <div className="plan-card plan-tabla-scroll">
        <table className="plan-tabla">
          <thead>
            <tr>
              <th>{t('planificador.col_tarea')}</th>
              <th className="plan-num">{t('planificador.col_duracion')}</th>
              <th>{t('planificador.col_inicio_temprano')}</th>
              <th>{t('planificador.col_fin_temprano')}</th>
              <th>{t('planificador.col_fin_tardio')}</th>
              <th className="plan-num">{t('planificador.col_holgura_total')}</th>
              <th className="plan-num">{t('planificador.col_holgura_libre')}</th>
              <th>{t('planificador.col_restriccion')}</th>
            </tr>
          </thead>
          <tbody>
            {plan.nodes.map(n => (
              <FilaDelPlan key={n.id} n={n} editable={puedeEditar}
                onRestriccion={(tipo, fecha) => restriccion.mutate({ id: n.id, tipo, fecha })} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FilaDelPlan({ n, editable, onRestriccion }: {
  n: NodoDelPlan; editable: boolean; onRestriccion: (tipo: string, fecha: string | null) => void
}) {
  const t = useAppT()
  const clase = n.is_critical ? 'plan-critica' : n.is_near_critical ? 'plan-casi' : ''
  return (
    <tr>
      <td>
        <span className={clase}>{n.code}</span> {n.title}
        {n.in_cycle && <span className="plan-chip">{t('planificador.en_ciclo')}</span>}
      </td>
      <td className="plan-num">{n.duration_days}</td>
      <td>{fmtDate(n.early_start)}</td>
      <td>{fmtDate(n.early_finish)}</td>
      <td>{fmtDate(n.late_finish)}</td>
      <td className={`plan-num ${clase}`}>{n.total_float}</td>
      <td className="plan-num">{n.free_float}</td>
      <td>
        {editable ? (
          <span className="plan-row">
            <select className="plan-select" aria-label={t('planificador.col_restriccion')} value={n.constraint_type ?? ''}
              onChange={e => onRestriccion(e.target.value, n.constraint_date ?? n.early_start)}>
              {RESTRICCIONES.map(r => <option key={r} value={r}>{t(`planificador.restriccion_${r || 'ninguna'}`)}</option>)}
            </select>
            {n.constraint_type && (
              <input type="date" className="plan-input plan-input--fecha" aria-label={t('planificador.fecha_restriccion')}
                value={n.constraint_date ?? ''} onChange={e => e.target.value && onRestriccion(n.constraint_type ?? '', e.target.value)} />
            )}
          </span>
        ) : n.constraint_type ? `${t(`planificador.restriccion_${n.constraint_type}`)} ${fmtDate(n.constraint_date)}` : '—'}
      </td>
    </tr>
  )
}
