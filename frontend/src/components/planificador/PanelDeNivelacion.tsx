/**
 * PanelDeNivelacion — nivelación real (rev. 173): propone qué tareas retrasar
 * dentro de su holgura para quitar la sobrecarga de las personas, sin mover a
 * sus sucesoras ni alargar el proyecto. Se aplican todas o las marcadas; el
 * servidor recalcula la propuesta antes de escribir.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Scale } from 'lucide-react'
import { planificacionApi, usersApi } from '../../services/api'
import { Button, EmptyState, KpiCard, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import './planificador.css'

export default function PanelDeNivelacion({ projectId }: { projectId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set())

  const { data: prop, isLoading, refetch } = useQuery({
    queryKey: ['nivelacion', projectId],
    queryFn: () => planificacionApi.nivelacion(projectId),
    enabled: !!projectId,
  })
  const { data: personas = [] } = useQuery({
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
  const nombre = Object.fromEntries(personas.map(p => [p.id, p.full_name]))

  const aplicar = useMutation({
    mutationFn: (ids?: string[]) => planificacionApi.aplicarNivelacion(projectId, ids),
    onSuccess: r => {
      toast.success(t('planificador.nivelacion_aplicada', { n: r.total_applied ?? 0 }))
      setMarcadas(new Set())
      qc.invalidateQueries({ queryKey: ['plan', projectId] })
      qc.invalidateQueries({ queryKey: ['gantt-tasks'] })
      refetch()
    },
    onError: e => toast.error(extractErr(e, t('planificador.error_generico'))),
  })

  if (isLoading) return <Spinner />
  if (!prop) return null

  const conmutar = (id: string) => setMarcadas(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  return (
    <div className="plan-stack">
      <div className="plan-kpis">
        <KpiCard icon={<Scale size={16} />} label={t('planificador.sobrecarga_antes')} value={`${prop.overallocated_hours_before} h`}
          sub={t('planificador.dias_persona', { n: prop.overallocations_before.length })} danger={prop.overallocations_before.length > 0} />
        <KpiCard icon={<Scale size={16} />} label={t('planificador.sobrecarga_despues')} value={`${prop.overallocated_hours_after} h`}
          sub={t('planificador.dias_persona', { n: prop.overallocations_after.length })} warning={prop.overallocations_after.length > 0} />
        <KpiCard label={t('planificador.movimientos')} value={prop.moves.length}
          sub={prop.skipped_without_estimate ? t('planificador.sin_estimacion', { n: prop.skipped_without_estimate }) : undefined} />
      </div>
      {prop.moves.length === 0 ? (
        <EmptyState title={prop.overallocations_before.length ? t('planificador.nivelacion_sin_margen') : t('planificador.nivelacion_sin_sobrecarga')}
          description={t('planificador.nivelacion_ayuda')} />
      ) : (
        <div className="plan-card plan-stack">
          <div className="plan-tabla-scroll">
            <table className="plan-tabla">
              <thead>
                <tr>
                  <th /><th>{t('planificador.col_tarea')}</th><th>{t('planificador.col_persona')}</th>
                  <th>{t('planificador.col_antes')}</th><th>{t('planificador.col_despues')}</th>
                  <th className="plan-num">{t('planificador.col_retraso')}</th>
                </tr>
              </thead>
              <tbody>
                {prop.moves.map(m => (
                  <tr key={m.task_id}>
                    <td><input type="checkbox" aria-label={m.title} checked={marcadas.has(m.task_id)} onChange={() => conmutar(m.task_id)} /></td>
                    <td>{m.code} {m.title}</td>
                    <td>{(m.assignee_id && nombre[m.assignee_id]) || '—'}</td>
                    <td>{fmtDate(m.old_start)} – {fmtDate(m.old_due)}</td>
                    <td>{fmtDate(m.new_start)} – {fmtDate(m.new_due)}</td>
                    <td className="plan-num">{t('planificador.n_dias', { n: m.delay_days ?? 0 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="plan-row">
            <Button size="sm" loading={aplicar.isPending} onClick={() => aplicar.mutate(undefined)}>{t('planificador.aplicar_todo')}</Button>
            <Button size="sm" variant="subtle" disabled={!marcadas.size} onClick={() => aplicar.mutate([...marcadas])}>
              {t('planificador.aplicar_marcadas', { n: marcadas.size })}
            </Button>
          </div>
        </div>
      )}
      {prop.overallocations_after.length > 0 && (
        <div className="plan-card">
          <h3 className="plan-card__titulo">{t('planificador.sobrecarga_que_queda')}</h3>
          <ul className="plan-lista">
            {prop.overallocations_after.slice(0, 50).map(o => (
              <li key={`${o.user_id}-${o.date}`}>
                <span>{nombre[o.user_id] ?? o.user_id} · {fmtDate(o.date)}</span>
                <span className="plan-critica">{o.hours} / {o.capacity} h</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
