/**
 * EditorDeDependencias — las dependencias del proyecto en un solo modelo (rev. 173):
 * FS/SS/FF/SF con desfase (las que planifican) y los vínculos informativos
 * (relacionada, duplicada, clonada). Crear, cambiar tipo y desfase, borrar.
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2, Plus, Trash2 } from 'lucide-react'
import { dependenciasApi, tasksApi, type Dependencia } from '../../services/api'
import { Button, EmptyState, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr } from '../../utils/helpers'
import { SCHEDULE_TASKS_LIST_SIZE } from '../../constants/pagination'
import './planificador.css'

const TIPOS = ['FS', 'SS', 'FF', 'SF'] as const
const VINCULOS = ['schedule', 'relates_to', 'duplicates', 'cloned_from'] as const

export default function EditorDeDependencias({ projectId }: { projectId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const puedeEditar = useAuth().hasRole('admin', 'pm')
  const [nueva, setNueva] = useState({ predecessor_id: '', successor_id: '', dependency_type: 'FS', lag_days: 0, link_type: 'schedule' })

  const { data: deps = [], isLoading } = useQuery({
    queryKey: ['task-deps', projectId],
    queryFn: () => dependenciasApi.listar(projectId),
    enabled: !!projectId,
  })
  const { data: tareas = [] } = useQuery({
    queryKey: ['tasks', 'deps-editor', projectId],
    queryFn: () => tasksApi.list({ project_id: projectId, page_size: SCHEDULE_TASKS_LIST_SIZE }).then(r => r.data),
    enabled: !!projectId,
  })
  const nombre = useMemo(() => Object.fromEntries(tareas.map(x => [x.id, `${x.code} ${x.title}`])), [tareas])

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['task-deps', projectId] })
    qc.invalidateQueries({ queryKey: ['plan', projectId] })
    qc.invalidateQueries({ queryKey: ['gantt-tasks'] })
  }
  const onError = (e: unknown) => toast.error(extractErr(e, t('planificador.error_generico')))
  const crear = useMutation({
    mutationFn: () => dependenciasApi.crear({
      predecessor_id: nueva.predecessor_id, successor_id: nueva.successor_id,
      dependency_type: nueva.dependency_type as Dependencia['dependency_type'], lag_days: Number(nueva.lag_days) || 0,
      link_type: nueva.link_type as Dependencia['link_type'],
    }),
    onSuccess: () => { toast.success(t('planificador.dependencia_creada')); setNueva(n => ({ ...n, predecessor_id: '', successor_id: '' })); refrescar() },
    onError,
  })
  const editar = useMutation({
    mutationFn: ({ id, cambios }: { id: string; cambios: Partial<Dependencia> }) => dependenciasApi.editar(id, cambios),
    onSuccess: refrescar,
    onError,
  })
  const borrar = useMutation({ mutationFn: (id: string) => dependenciasApi.borrar(id), onSuccess: refrescar, onError })

  if (isLoading) return <Spinner />

  return (
    <div className="plan-stack">
      {puedeEditar && (
        <form className="plan-row" onSubmit={e => { e.preventDefault(); crear.mutate() }}>
          <select className="plan-select" aria-label={t('planificador.predecesora')} value={nueva.predecessor_id}
            onChange={e => setNueva(n => ({ ...n, predecessor_id: e.target.value }))}>
            <option value="">{t('planificador.predecesora')}</option>
            {tareas.map(x => <option key={x.id} value={x.id}>{nombre[x.id]}</option>)}
          </select>
          <select className="plan-select" aria-label={t('planificador.col_vinculo')} value={nueva.link_type}
            onChange={e => setNueva(n => ({ ...n, link_type: e.target.value }))}>
            {VINCULOS.map(v => <option key={v} value={v}>{t(`planificador.vinculo_${v}`)}</option>)}
          </select>
          {nueva.link_type === 'schedule' && (
            <>
              <select className="plan-select" aria-label={t('planificador.col_tipo')} value={nueva.dependency_type}
                onChange={e => setNueva(n => ({ ...n, dependency_type: e.target.value }))}>
                {TIPOS.map(x => <option key={x} value={x}>{t(`planificador.tipo_${x}`)}</option>)}
              </select>
              <input type="number" className="plan-input plan-input--num" aria-label={t('planificador.col_desfase')}
                value={nueva.lag_days} onChange={e => setNueva(n => ({ ...n, lag_days: Number(e.target.value) }))} />
            </>
          )}
          <select className="plan-select" aria-label={t('planificador.sucesora')} value={nueva.successor_id}
            onChange={e => setNueva(n => ({ ...n, successor_id: e.target.value }))}>
            <option value="">{t('planificador.sucesora')}</option>
            {tareas.filter(x => x.id !== nueva.predecessor_id).map(x => <option key={x.id} value={x.id}>{nombre[x.id]}</option>)}
          </select>
          <Button size="sm" type="submit" icon={<Plus size={13} />} loading={crear.isPending}
            disabled={!nueva.predecessor_id || !nueva.successor_id}>{t('planificador.anadir_dependencia')}</Button>
        </form>
      )}
      {deps.length === 0 ? (
        <EmptyState icon={<Link2 size={20} />} title={t('planificador.sin_dependencias')} description={t('planificador.sin_dependencias_desc')} />
      ) : (
        <div className="plan-card plan-tabla-scroll">
          <table className="plan-tabla">
            <thead>
              <tr>
                <th>{t('planificador.predecesora')}</th><th>{t('planificador.col_vinculo')}</th>
                <th>{t('planificador.col_tipo')}</th><th className="plan-num">{t('planificador.col_desfase')}</th>
                <th>{t('planificador.sucesora')}</th><th />
              </tr>
            </thead>
            <tbody>
              {deps.map(d => (
                <tr key={d.id}>
                  <td>{nombre[d.predecessor_id] ?? d.predecessor_id}</td>
                  <td>{t(`planificador.vinculo_${d.link_type ?? 'schedule'}`)}</td>
                  <td>
                    {puedeEditar && d.link_type === 'schedule' ? (
                      <select className="plan-select" aria-label={t('planificador.col_tipo')} value={d.dependency_type}
                        onChange={e => editar.mutate({ id: d.id, cambios: { dependency_type: e.target.value as Dependencia['dependency_type'] } })}>
                        {TIPOS.map(x => <option key={x} value={x}>{t(`planificador.tipo_${x}`)}</option>)}
                      </select>
                    ) : d.link_type === 'schedule' ? t(`planificador.tipo_${d.dependency_type}`) : '—'}
                  </td>
                  <td className="plan-num">
                    {puedeEditar && d.link_type === 'schedule' ? (
                      <input type="number" className="plan-input plan-input--num" aria-label={t('planificador.col_desfase')}
                        defaultValue={d.lag_days} onBlur={e => Number(e.target.value) !== d.lag_days
                          && editar.mutate({ id: d.id, cambios: { lag_days: Number(e.target.value) || 0 } })} />
                    ) : d.lag_days}
                  </td>
                  <td>{nombre[d.successor_id] ?? d.successor_id}</td>
                  <td>
                    {puedeEditar && (
                      <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => borrar.mutate(d.id)}>
                        {t('planificador.borrar')}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
