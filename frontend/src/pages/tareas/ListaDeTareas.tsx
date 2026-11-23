/**
 * Listado de tareas: tarjetas en pantallas compactas y tabla virtualizada en el resto.
 * Troceado de TasksPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { Badge, Checkbox, EmptyState, SortableTH } from '../../components/ui'
import VirtualList from '../../components/ui/VirtualList'
import { Search } from 'lucide-react'
import { fmtNumber } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import type { useListaDeProyectos } from '../../hooks/useListas'
import { desdeCasilla, onKeyboardActivate, type Task } from './compartido'

type PropsOrden = Parameters<typeof SortableTH>[0]

interface ListaDeTareasProps {
  tareas: Task[]
  ordenadas: Task[]
  compacta: boolean
  proyectos: NonNullable<ReturnType<typeof useListaDeProyectos>['data']>
  seleccion: Set<string>
  onAlternar: (id: string) => void
  onAlternarTodas: () => void
  orden: PropsOrden['sort']
  onOrden: PropsOrden['onSort']
  onAbrir: (tarea: Task) => void
}

export function ListaDeTareas({ tareas, ordenadas, compacta, proyectos, seleccion, onAlternar, onAlternarTodas, orden, onOrden, onAbrir }: ListaDeTareasProps) {
  const t = useAppT()
  return (
    tareas.length === 0 ? (
      <EmptyState icon={<Search size={28} />} title={t('common.no_results')} description={t('tasks.sin_resultados_desc')} />
    ) : compacta ? (
      <div className="u-stack-10">
        {ordenadas.map((task) => {
          const proj = proyectos.find(p => p.id === task.project_id)
          return (
            <div key={task.id}
              onClick={e => { if (!desdeCasilla(e)) onAbrir(task) }}
              onKeyDown={e => onKeyboardActivate(e, () => onAbrir(task))}
              role="button"
              tabIndex={0}
              className="tsk-mcard"
            >
              <div className="tsk-mcard-head">
                <Checkbox
                  aria-label={task.title}
                  checked={seleccion.has(task.id)}
                  onChange={() => onAlternar(task.id)}
                  className="tsk-check"
                />
                <div className="tsk-mcard-title">{task.title}</div>
                <Badge label={task.priority} />
              </div>
              <div className="tsk-mcard-meta">
                <span>{task.code}</span>
                <span>{proj ? proj.code : t('tasks.no_project')}</span>
                <span>{task.assignee?.full_name || (task.supplier_name ? t('proveedores.externalizada_a', { nombre: task.supplier_name }) : t('tasks.no_assignee'))}</span>
                <span>{task.estimated_hours ? t('tasks.horas_est', { h: fmtNumber(task.estimated_hours, 1) }) : t('tasks.no_estimate')}</span>
                <span>{t('tasks.horas_real', { h: fmtNumber(task.real_hours ?? 0, 1) })}</span>
              </div>
              <div className="tsk-mt8">
                <Badge label={task.status} />
              </div>
            </div>
          )
        })}
      </div>
    ) : (
      <div data-export-table="tasks-list" className="ds-card tsk-list">
        <div className="tsk-list-head">
          <Checkbox aria-label={t('reportbuilder.seleccionar_todos')} checked={seleccion.size === tareas.length && tareas.length > 0} onChange={onAlternarTodas} className="tsk-check" />
          <SortableTH col="title" sort={orden} onSort={onOrden}>{t('tasks.col_task')}</SortableTH>
          <SortableTH col="project_id" sort={orden} onSort={onOrden}>{t('tasks.col_project')}</SortableTH>
          <SortableTH col="assignee.full_name" sort={orden} onSort={onOrden}>{t('tasks.col_assignee')}</SortableTH>
          <SortableTH col="estimated_hours" sort={orden} onSort={onOrden}>{t('tasks.col_est')}</SortableTH>
          <SortableTH col="real_hours" sort={orden} onSort={onOrden}>{t('tasks.col_real')}</SortableTH>
          <SortableTH col="status" sort={orden} onSort={onOrden}>{t('common.status')}</SortableTH>
          <SortableTH col="priority" sort={orden} onSort={onOrden}>{t('common.priority')}</SortableTH>
        </div>
        <VirtualList
          items={ordenadas}
          rowHeight={52}
          height={Math.min(tareas.length * 52, 600)}
          renderRow={(t: Task) => (
            <div
              onClick={e => { if (!desdeCasilla(e)) onAbrir(t) }}
              onKeyDown={e => onKeyboardActivate(e, () => onAbrir(t))}
              role="button"
              tabIndex={0}
              className={`tsk-list-row${seleccion.has(t.id) ? ' tsk-list-row--selected' : ''}`}
            >
              <Checkbox aria-label={t.title} checked={seleccion.has(t.id)} onChange={() => onAlternar(t.id)} className="tsk-check" />
              <div>
                <div className="u-base-600">{t.title}</div>
                <div className="u-text2-mono-xs">{t.code}</div>
              </div>
              <span className="u-text2-sm">
                {proyectos.find(p => p.id === t.project_id)?.code || t.project_id?.slice(0,8) || '—'}
              </span>
              <span className="u-sm">{t.assignee?.full_name?.split(' ')[0] || '—'}</span>
              <span className="tsk-mono-sm">{t.estimated_hours ? `${fmtNumber(t.estimated_hours, 1)}h` : '—'}</span>
              <span className={`tsk-mono-sm${(t.real_hours ?? 0) > (t.estimated_hours ?? 0) ? ' tsk-mono-sm--over' : ''}`}>{fmtNumber(t.real_hours ?? 0, 1)}h</span>
              <span><Badge label={t.status} /></span>
              <span><Badge label={t.priority} /></span>
            </div>
          )}
        />
      </div>
    )
  )
}
