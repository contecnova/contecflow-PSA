/**
 * Acciones de una reunión (19-11-2026): responsable (persona de la empresa) y
 * fecha editables, tarea o ticket del service desk con un clic, y «crear
 * todas las tareas» en el proyecto elegido. Solo el gestor edita y crea.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, CheckCircle2, ListChecks, ListPlus, Ticket, User } from 'lucide-react'
import { Button, Card, FormField, Input, ProjectSelect, Section, StatusBadge, UserSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import type { ReunionDetalle } from '../../services/api/reuniones'
import { CLAVES } from './comun'
import './Reuniones.css'

export default function AccionesDeReunion({ reunion }: { reunion: ReunionDetalle }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [proyecto, setProyecto] = useState(reunion.project_id ?? '')
  const gestor = reunion.permissions.manage
  const acciones = reunion.actions
  const refrescar = () => {
    qc.invalidateQueries({ queryKey: CLAVES.detalle(reunion.id) })
    qc.invalidateQueries({ queryKey: CLAVES.lista })
  }
  const alFallar = (e: unknown) => toast.error(extractErr(e))

  const editar = useMutation({
    mutationFn: (c: { aid: string; assignee_id?: string | null; due_date?: string | null }) =>
      reunionesApi.editarAccion(reunion.id, c.aid, { assignee_id: c.assignee_id, due_date: c.due_date }),
    onSuccess: refrescar,
    onError: alFallar,
  })
  const tarea = useMutation({
    mutationFn: (aid: string) => reunionesApi.crearTarea(reunion.id, aid, proyecto || null),
    onSuccess: () => { toast.success(t('reuniones.acciones.tarea_creada')); refrescar() },
    onError: alFallar,
  })
  const ticket = useMutation({
    mutationFn: (aid: string) => reunionesApi.crearTicket(reunion.id, aid),
    onSuccess: r => { toast.success(t('reuniones.acciones.ticket_creado', { numero: r.number })); refrescar() },
    onError: alFallar,
  })
  const todas = useMutation({
    mutationFn: () => reunionesApi.crearTareas(reunion.id, { project_id: proyecto || null }),
    onSuccess: r => { toast.success(t('reuniones.acciones.tareas_creadas', { n: r.tasks_created })); refrescar() },
    onError: alFallar,
  })

  const pendientes = acciones.filter(a => !a.is_created && !a.task_id)

  return (
    <Card>
      <Section
        title={<span className="reu-seccion"><ListChecks size={16} aria-hidden />{t('reuniones.acciones.titulo', { n: acciones.length })}</span>}
        actions={gestor && pendientes.length > 0 ? (
          <Button size="sm" icon={<ListPlus size={14} />} loading={todas.isPending} onClick={() => todas.mutate()}>
            {t('reuniones.acciones.crear_todas')}
          </Button>
        ) : undefined}
      >
        {acciones.length === 0 ? <p className="u-text3-xs">{t('reuniones.acciones.vacio')}</p> : (
          <>
            {gestor && pendientes.length > 0 && (
              <div className="reu-acciones__proyecto">
                <FormField label={t('reuniones.acciones.proyecto_tareas')} hint={t('reuniones.acciones.proyecto_tareas_ayuda')}>
                  <ProjectSelect value={proyecto} onChange={id => setProyecto(id)} />
                </FormField>
              </div>
            )}
            <ul className="reu-lista">
              {acciones.map(a => {
                const hecha = a.is_created || !!a.task_id
                return (
                  <li key={a.id} className="reu-accion">
                    <div className="u-flex1-min0">
                      <div className="reu-accion__texto">{a.description}</div>
                      {gestor && !hecha ? (
                        <div className="reu-accion__edicion">
                          <UserSelect value={a.assignee_id ?? ''} placeholder={a.assignee_name || t('reuniones.acciones.sin_responsable')}
                            onChange={id => editar.mutate({ aid: a.id, assignee_id: id || null })} />
                          <Input aria-label={t('reuniones.acciones.fecha')} type="date" value={a.due_date ?? ''}
                            onChange={e => editar.mutate({ aid: a.id, due_date: e.target.value || null })} />
                          {a.due_date_text && !a.due_date && <span className="u-text3-xs">{t('reuniones.acciones.dicho', { texto: a.due_date_text })}</span>}
                        </div>
                      ) : (
                        <div className="reu-accion__meta">
                          {a.assignee_name && <span className="reu-meta"><User size={13} aria-hidden />{a.assignee_name}</span>}
                          {(a.due_date || a.due_date_text) && (
                            <span className="reu-meta"><CalendarDays size={13} aria-hidden />{a.due_date ? fmtDate(a.due_date) : a.due_date_text}</span>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="reu-accion__botones">
                      {hecha && <StatusBadge kind="success" caps={false}><CheckCircle2 size={12} aria-hidden /> {t('reuniones.acciones.tarea')}</StatusBadge>}
                      {a.ticket_id && <StatusBadge kind="info" caps={false}><Ticket size={12} aria-hidden /> {t('reuniones.acciones.ticket')}</StatusBadge>}
                      {gestor && !hecha && (
                        <Button size="xs" variant="secondary" icon={<ListPlus size={12} />} loading={tarea.isPending && tarea.variables === a.id}
                          onClick={() => tarea.mutate(a.id)}>
                          {t('reuniones.acciones.crear_tarea')}
                        </Button>
                      )}
                      {gestor && !a.ticket_id && (
                        <Button size="xs" variant="ghost" icon={<Ticket size={12} />} loading={ticket.isPending && ticket.variables === a.id}
                          onClick={() => ticket.mutate(a.id)}>
                          {t('reuniones.acciones.crear_ticket')}
                        </Button>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </Section>
    </Card>
  )
}
