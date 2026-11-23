/**
 * Tarjeta de tablero, columna, alta rápida, historial y opciones de estado del flujo.
 * Troceado de TasksPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useRef } from 'react'
import { pedirTexto } from '../../context/ConfirmContext'
import { useQuery } from '@tanstack/react-query'
import { tasksApi, projectWorkflowsApi, type MovementLogEntry } from '../../services/api'
import type { FlujoDelProyecto } from '../../services/api/tipos-rendimiento'
import { Badge, Avatar, Pulsable, Input } from '../../components/ui'
import { Building2, CalendarDays, Loader2, Plus } from 'lucide-react'
import { fmtDate, fmtNumber } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import { CLAVE_DE_ESTADO, type DragStartHandler, nombreDeEstado, type StatusOption, type Task, type Traductor } from './compartido'

function TaskKanbanCard({ task, onTaskClick, onTaskDragStart }: { task: Task; onTaskClick: (t: Task) => void; onTaskDragStart?: DragStartHandler }) {
  const t = useAppT()
  const wasDragged = useRef(false)
  const vencida = !!task.due_date && new Date(task.due_date) < new Date() && task.status !== 'done'
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${task.title} — ${nombreDeEstado(t, task.status)}`}
      onMouseDown={e => {
        if (e.button !== 0) return
        wasDragged.current = false
        onTaskDragStart && onTaskDragStart(e, task, () => { wasDragged.current = true })
      }}
      onClick={() => { if (!wasDragged.current) onTaskClick(task) }}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onTaskClick(task) } }}
      className={`tsk-card${task.status === 'blocked' ? ' tsk-card--blocked' : ''}`}
    >
      <div className="tsk-card-head">
        <span className="u-text2-mono-xs">{task.code}</span>
        <Badge label={task.priority} />
      </div>
      <div className="tsk-card-title">{task.title}</div>
      <div className="u-row-between">
        {task.assignee ? (
          <div className="u-row-center-6">
            <Avatar name={task.assignee.full_name} size={22} />
            <span className="u-text2-xs">{task.assignee.full_name.split(' ')[0]}</span>
          </div>
        ) : task.supplier_name ? (
          <span className="u-row-center-6 u-text2-xs" title={t('proveedores.externalizada_a', { nombre: task.supplier_name })}>
            <Building2 size={12} aria-hidden />{task.supplier_name}
          </span>
        ) : <span />}
        {!!task.estimated_hours && (
          <span className={`tsk-card-hours${(task.real_hours ?? 0) > (task.estimated_hours ?? 0) ? ' tsk-card-hours--over' : ''}`}>
            {fmtNumber(task.real_hours ?? 0, 1)}h / {fmtNumber(task.estimated_hours, 1)}h
          </span>
        )}
      </div>
      {task.due_date && (
        <div className={`tsk-card-due${vencida ? ' tsk-card-due--overdue' : ''}`}>
          <CalendarDays size={12} aria-hidden />{fmtDate(task.due_date)}
        </div>
      )}
    </div>
  )
}

/** Cambios de estado de la tarea, con quién, cuándo y el motivo al reabrir. */
export function HistorialDeMovimientos({ taskId }: { taskId: string }) {
  const t = useAppT()
  const { data = [], isLoading } = useQuery<MovementLogEntry[]>({
    queryKey: ['task-movement-log', taskId],
    queryFn: () => tasksApi.movementLog(taskId).then(r => (r.data as MovementLogEntry[] & { items?: MovementLogEntry[] })?.items ?? r.data ?? []),
  })
  if (isLoading) return <Loader2 size={14} className="tsk-spin" aria-label={t('common.loading')} />
  if (!data.length) return <p className="u-text2-base">{t('tasks.historial_vacio')}</p>
  return (
    <ol className="tsk-history">
      {data.map(m => (
        <li key={m.id} className="tsk-history-item">
          <strong>{m.from_status ? t(CLAVE_DE_ESTADO[m.from_status] || m.from_status) : '—'} → {t(CLAVE_DE_ESTADO[m.to_status] || m.to_status)}</strong>
          <span className="u-text3"> · {m.moved_by?.full_name || '—'} · {fmtDate(m.moved_at)}</span>
          {m.reason && <div className="tsk-history-reason">{t('tasks.historial_motivo', { motivo: m.reason })}</div>}
        </li>
      ))}
    </ol>
  )
}

/** Alta rápida al pie de una columna (revisión 2026-11, traída de la pantalla Kanban). */
function AltaRapida({ onCrear }: { onCrear: (titulo: string) => Promise<unknown> }) {
  const t = useAppT()
  const [abierta, setAbierta] = useState(false)
  const [titulo, setTitulo] = useState('')
  const enviar = async () => {
    if (!titulo.trim()) return
    await onCrear(titulo.trim()); setTitulo(''); setAbierta(false)
  }
  if (!abierta) return (
    <Pulsable className="tsk-quick-add" onClick={() => setAbierta(true)}>
      <Plus size={13} aria-hidden />{t('tasks.kanban_alta_rapida')}
    </Pulsable>
  )
  return (
    <Input autoFocus value={titulo} placeholder={t('tasks.kanban_alta_titulo')} aria-label={t('tasks.kanban_alta_titulo')}
      onChange={e => setTitulo(e.target.value)} onBlur={() => !titulo && setAbierta(false)}
      onKeyDown={e => { if (e.key === 'Enter') enviar(); if (e.key === 'Escape') { setAbierta(false); setTitulo('') } }}
      inputClassName="tsk-quick-add-input" />
  )
}

export function KanbanColumn({ status, tasks, onTaskClick, onTaskDragStart, onColumnEnter, onColumnLeave, dragOver, wipLimit, onSetWip, onCrear }: { status: string; tasks: Task[]; onTaskClick: (t: Task) => void; onTaskDragStart?: DragStartHandler; onColumnEnter?: () => void; onColumnLeave?: () => void; dragOver?: boolean; wipLimit?: number | null; onSetWip?: (n: number | null) => void; onCrear?: (titulo: string) => Promise<unknown> }) {
  const t = useAppT()
  const pasado = !!wipLimit && tasks.length > wipLimit
  return (
    <div
      onPointerEnter={onColumnEnter}
      onPointerLeave={onColumnLeave}
      className={`tsk-col${dragOver ? ' tsk-col--over' : ''}`}>
      <div className="tsk-col-head">
        <div className={`tsk-col-dot tsk-tone-s--${status}`} aria-hidden="true" />
        <span className="tsk-col-title">
          {nombreDeEstado(t, status)}
        </span>
        <span title={wipLimit ? t('tasks.kanban_wip_titulo', { n: wipLimit }) : undefined}
          className={`tsk-col-count${pasado ? ' tsk-col-count--over' : ''}`}>
          {tasks.length}{wipLimit ? ` / ${wipLimit}` : ''}
        </span>
        {onSetWip && (
          <Pulsable aria-label={t('tasks.kanban_wip_editar')} title={t('tasks.kanban_wip_editar')}
            onClick={async () => {
              const v = await pedirTexto({ title: t('tasks.kanban_wip_editar'), message: t('tasks.kanban_wip_pregunta'), defaultValue: wipLimit ? String(wipLimit) : '', inputType: 'number' })
              if (v === null) return
              const n = parseInt(v, 10)
              onSetWip(Number.isFinite(n) && n > 0 ? n : null)
            }}
            className="tsk-wip-btn">WIP</Pulsable>
        )}
      </div>
      <div className="u-stack-8">
        {tasks.map(task => (
          <TaskKanbanCard
            key={task.id}
            task={task}
            onTaskClick={onTaskClick}
            onTaskDragStart={onTaskDragStart}
          />
        ))}
      </div>
      {onCrear && <AltaRapida onCrear={onCrear} />}
    </div>
  )
}

export function useWorkflowStatusOptions(projectId: string | undefined, t: Traductor): StatusOption[] {
  const { data } = useQuery<FlujoDelProyecto | null>({
    queryKey: ['project-workflow', projectId],
    // 23-11-2026: solo el 404 («sin flujo propio») es un null válido; cualquier otro fallo sube y avisa.
    queryFn: () => projectWorkflowsApi.get(projectId).then(r => r.data).catch((err: { response?: { status?: number } }) => {
      if (err?.response?.status === 404) return null
      throw err
    }),
    enabled: !!projectId,
    staleTime: STALE_DEFAULT_MS,
    retry: false,
  })
  if ((data?.states?.length ?? 0) > 0) {
    return data.states
      .slice()
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
      .map(s => ({ value: s.value, icon: s.icon || '○', label: s.name }))
  }
  return [
    { value: 'backlog',     icon: '○', label: t('tasks.status_backlog')     },
    { value: 'todo',        icon: '○', label: t('tasks.status_todo')        },
    { value: 'in_progress', icon: '◑', label: t('tasks.status_in_progress') },
    { value: 'in_review',   icon: '◐', label: t('tasks.status_review')      },
    { value: 'blocked',     icon: '✕', label: t('tasks.status_blocked')     },
    { value: 'done',        icon: '●', label: t('tasks.status_done')        },
    { value: 'cancelled',   icon: '✕', label: t('tasks.status_cancelled')   },
  ]
}
