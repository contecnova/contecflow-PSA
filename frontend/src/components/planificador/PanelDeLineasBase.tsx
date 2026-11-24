/**
 * PanelDeLineasBase — varias líneas base por proyecto (rev. 173): congelar el
 * plan, elegir la vigente (la que pinta el Gantt y usa el valor ganado),
 * comparar el plan de hoy o dos líneas base entre sí, y borrar.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, CheckCircle2, GitCompare, Trash2 } from 'lucide-react'
import { lineasBaseApi } from '../../services/api'
import { Button, EmptyState, Spinner, Select, TablaSimple, Checkbox } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useConfirm } from '../../context/ConfirmContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import './planificador.css'
import { Input } from '../ui'

export default function PanelDeLineasBase({ projectId }: { projectId: string }) {
  const t = useAppT()
  const toast = useToast()
  const { confirmar } = useConfirm()
  const qc = useQueryClient()
  const gestiona = useAuth().puede('proyectos.lineas_base')
  const [nombre, setNombre] = useState('')
  const [vigente, setVigente] = useState(false)
  const [comparar, setComparar] = useState<{ id: string; contra: string }>({ id: '', contra: '' })

  const { data: lineas = [], isLoading } = useQuery({
    queryKey: ['lineas-base', projectId],
    queryFn: () => lineasBaseApi.listar(projectId),
    enabled: !!projectId,
  })
  const { data: cmp, isFetching: comparando } = useQuery({
    queryKey: ['lineas-base-cmp', projectId, comparar.id, comparar.contra],
    queryFn: () => lineasBaseApi.comparar(projectId, comparar.id, comparar.contra || undefined),
    enabled: !!comparar.id,
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['lineas-base', projectId] })
    qc.invalidateQueries({ queryKey: ['gantt-tasks'] })
    qc.invalidateQueries({ queryKey: ['plan', projectId] })
  }
  const crear = useMutation({
    mutationFn: () => lineasBaseApi.crear(projectId, { name: nombre.trim(), make_current: vigente || undefined }),
    onSuccess: () => { setNombre(''); setVigente(false); toast.success(t('planificador.linea_base_creada')); refrescar() },
    onError: e => toast.error(extractErr(e, t('planificador.error_generico'))),
  })
  const hacerVigente = useMutation({
    mutationFn: (id: string) => lineasBaseApi.hacerVigente(projectId, id),
    onSuccess: () => { toast.success(t('planificador.linea_base_vigente_ok')); refrescar() },
    onError: e => toast.error(extractErr(e, t('planificador.error_generico'))),
  })
  const borrar = useMutation({
    mutationFn: (id: string) => lineasBaseApi.borrar(projectId, id),
    onSuccess: () => { toast.success(t('planificador.linea_base_borrada')); setComparar({ id: '', contra: '' }); refrescar() },
    onError: e => toast.error(extractErr(e, t('planificador.error_generico'))),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="plan-stack">
      {gestiona && (
        <form className="plan-row" onSubmit={e => { e.preventDefault(); if (nombre.trim()) crear.mutate() }}>
          <Input value={nombre} onChange={e => setNombre(e.target.value)} maxLength={100} placeholder={t('planificador.nombre_linea_base')} aria-label={t('planificador.nombre_linea_base')} />
          <Checkbox className="plan-row plan-muted" label={t('planificador.hacer_vigente')} checked={vigente} onChange={m => setVigente(m)} />
          <Button size="sm" type="submit" icon={<Camera size={13} />} loading={crear.isPending} disabled={!nombre.trim()}>
            {t('planificador.congelar_plan')}
          </Button>
        </form>
      )}

      {lineas.length === 0 ? (
        <EmptyState title={t('planificador.sin_lineas_base')} description={t('planificador.sin_lineas_base_desc')} />
      ) : (
        <div className="plan-card plan-tabla-scroll">
          <TablaSimple claseTabla="plan-tabla">
            <thead>
              <tr>
                <th>{t('planificador.col_nombre')}</th><th>{t('planificador.col_fecha')}</th>
                <th className="plan-num">{t('planificador.col_tareas')}</th><th className="plan-num">{t('planificador.col_horas')}</th>
                <th>{t('planificador.col_estado')}</th><th><span className="u-sr-only">{t('common.col_acciones')}</span></th>
              </tr>
            </thead>
            <tbody>
              {lineas.map(l => (
                <tr key={l.id}>
                  <td>{l.name}</td>
                  <td>{fmtDate(l.baseline_date)}</td>
                  <td className="plan-num">{l.total_tasks}</td>
                  <td className="plan-num">{Math.round(l.total_hours || 0)}</td>
                  <td>{l.is_current ? <span className="plan-chip plan-chip--activa">{t('planificador.vigente')}</span> : null}</td>
                  <td>
                    <span className="plan-row">
                      <Button size="xs" variant="subtle" icon={<GitCompare size={12} />} onClick={() => setComparar({ id: l.id, contra: '' })}>
                        {t('planificador.comparar')}
                      </Button>
                      {gestiona && !l.is_current && (
                        <Button size="xs" variant="subtle" icon={<CheckCircle2 size={12} />} onClick={() => hacerVigente.mutate(l.id)}>
                          {t('planificador.usar_como_vigente')}
                        </Button>
                      )}
                      {gestiona && (
                        <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} title={t('planificador.borrar')}
                          onClick={async () => { if (await confirmar({ message: t('planificador.confirmar_borrar_linea_base', { nombre: l.name }), danger: true })) borrar.mutate(l.id) }}>
                          {t('planificador.borrar')}
                        </Button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}

      {comparar.id && (
        <div className="plan-card plan-stack">
          <div className="plan-row plan-row--between">
            <h3 className="plan-card__titulo">{t('planificador.comparacion')}</h3>
            <Select label={t('planificador.comparar_contra')} value={comparar.contra} onChange={e => setComparar(c => ({ ...c, contra: e.target.value }))} placeholder={t('planificador.plan_de_hoy')}>
                {lineas.filter(l => l.id !== comparar.id).map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
              </Select>
          </div>
          {comparando || !cmp ? <Spinner /> : (
            <>
              <div className="plan-row">
                <span className="plan-chip">{t('planificador.cmp_comparadas', { n: cmp.summary.tasks_compared })}</span>
                <span className="plan-chip">{t('planificador.cmp_retrasadas', { n: cmp.summary.tasks_slipped })}</span>
                <span className="plan-chip">{t('planificador.cmp_adelantadas', { n: cmp.summary.tasks_ahead })}</span>
                <span className="plan-chip">{t('planificador.cmp_desvio_medio', { n: cmp.summary.avg_slip_days })}</span>
                <span className="plan-chip">{t('planificador.cmp_nuevas', { n: cmp.summary.tasks_added })}</span>
                <span className="plan-chip">{t('planificador.cmp_quitadas', { n: cmp.summary.tasks_removed })}</span>
                <span className="plan-chip">{t('planificador.cmp_horas', { base: cmp.summary.baseline_hours, hoy: cmp.summary.current_hours })}</span>
              </div>
              <div className="plan-tabla-scroll">
                <TablaSimple claseTabla="plan-tabla">
                  <thead>
                    <tr>
                      <th>{t('planificador.col_tarea')}</th><th>{t('planificador.col_fin_base')}</th>
                      <th>{t('planificador.col_fin_actual')}</th><th className="plan-num">{t('planificador.col_desvio')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cmp.task_deltas.map(d => (
                      <tr key={`${d.task_id}-${d.delta ?? ''}`}>
                        <td>{d.title ?? d.task_id}{d.delta && <span className="plan-chip">{t(`planificador.delta_${d.delta}`)}</span>}</td>
                        <td>{fmtDate(d.baseline_end)}</td>
                        <td>{fmtDate(d.current_end)}</td>
                        <td className={`plan-num ${(d.slip_days ?? 0) > 0 ? 'plan-critica' : (d.slip_days ?? 0) < 0 ? 'plan-ok' : ''}`}>
                          {d.slip_days ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </TablaSimple>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
