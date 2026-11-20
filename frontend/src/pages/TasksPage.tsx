/**
 * TasksPage — tareas: tablero, lista y vistas del planificador.
 *
 * 16-11-2026: el selector de vista sale de la cabecera a una barra <Tabs>
 * (antes control segmentado dentro de las acciones); "Auto-planificar" con
 * Button secondary (antes variante azul clara `subtle`) e iconos por prop;
 * vacíos con icono lucide y descripción correcta (antes decía solo "Tarea" y
 * "Estado"); emojis de tarjetas, prioridades y botones del panel (📅🕐✅🗑✏️💾🧠⏳
 * 🟢🟡🔴🚨) cambiados por iconos lucide o quitados; pestañas del panel sin
 * estilo en línea.
 */
import { useState, useEffect, useRef, useCallback, useId } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { openConfirmGlobal, pedirTexto } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi, projectsApi, customFieldsApi, semanticApi, projectWorkflowsApi, issueTypesApi, sprintsApi, cmdbApi, usersApi } from '../services/api'
import type { CampoPersonalizado, ConfigDelTablero, EstimacionDeEsfuerzo, FlujoDelProyecto, SugerenciaDeAsignacion, TipoDeIncidencia, ValorDeCampoPersonalizado } from '../services/api/tipos-rendimiento'
import type { ApiError, ProjectListItem, TaskCreatePayload, TaskUpdatePayload, TaskBulkUpdatePayload, TaskListParams, PersonaVisible, MovementLogEntry } from '../services/api'
import { Badge, Button, Modal, EmptyState, Avatar, useSort, SortableTH, Tabs, Drawer, Select, Checkbox, Chip, BarraDeFiltros, IconButton, Pulsable, useErroresDeCampo } from '../components/ui'
import { SkeletonTable } from '../components/ui/Skeletons'
import VistasDeTrabajo, { VISTAS_DE_TRABAJO, type FiltrosDeVistas, type VistaDeTrabajo } from '../components/planificador/VistasDeTrabajo'
import VirtualList from '../components/ui/VirtualList'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  Ban, Brain, Building2, CalendarClock, CalendarDays, CalendarRange, CheckCircle2, CheckSquare, Clock, GanttChartSquare, LayoutGrid, List, Loader2, Pencil, Plus, Save, Search, Sparkles, Table2, Trash2, Users, X,
} from 'lucide-react'
import SmartScheduleModal from '../components/SmartScheduleModal'
import { fmtDate, fmtNumber, extractErr} from '../utils/helpers'
import { COLUMNAS_DE_TABLERO, etiquetaDeEstado } from '../constants/catalogos'
import { useCatalogo } from '../hooks/useCatalogo'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import DocumentsPanel from '../components/DocumentsPanel'
import AIInlineEditor from '../components/AIInlineEditor'
import { useAppT } from '../i18n/AppLangContext'
import ExternalizarTarea from '../components/proveedores/ExternalizarTarea'
import { asignacionExclusiva } from './proveedores/logica'
import DateInput from '../components/ui/DateInput'
import { STALE_DEFAULT_MS, STALE_REFERENCE_DATA_MS } from '../constants/timings'
import './TasksPage.css'


type Traductor = ReturnType<typeof useAppT>

/** `UserPublic` (app/schemas/users.py): la persona que el servidor anida en tareas y comentarios. */
type PersonaRef = { id: string; full_name: string; email?: string; avatar_url?: string | null }
/** `TaskCommentOut` (app/schemas/tasks.py). */
type TaskComment = { id: string; task_id: string; author?: PersonaRef | null; content: string; created_at: string }
/** `TaskOut` (app/schemas/tasks.py). `tags` y `completed_at` los lee la pantalla aunque el esquema no los declare. */
type Task = {
  id: string
  code?: string
  title: string
  description?: string | null
  project_id: string
  assignee_id?: string | null
  status: string
  priority?: string | null
  estimated_hours?: number | null
  start_date?: string | null
  due_date?: string | null
  issue_type?: string | null
  assignee?: PersonaRef | null
  real_hours?: number | null
  blocked_reason?: string | null
  tags?: string | null
  comments?: TaskComment[]
  created_at?: string
  completed_at?: string | null
  /** 19-11-2026: externalizada a un proveedor de outsourcing (excluyente con `assignee_id`). */
  supplier_id?: string | null
  supplier_work_package_id?: string | null
  supplier_name?: string | null
}
/** Formulario de edición del panel de detalle. */
type TaskForm = {
  title: string
  description: string
  status: string
  priority: string
  assignee_id: string
  supplier_id: string
  supplier_work_package_id: string
  estimated_hours: string | number
  start_date: string
  due_date: string
  blocked_reason: string
  tags: string
  issue_type: string
}
/** Formulario de alta. */
type NewTaskForm = {
  title: string
  project_id: string
  status: string
  priority: string
  estimated_hours: string
  start_date: string
  due_date: string
  description: string
  assignee_id: string
  supplier_id: string
  supplier_work_package_id: string
}
// Respuestas del backend: services/api/tipos-rendimiento.ts.
type CustomField = CampoPersonalizado
type CustomFieldValue = ValorDeCampoPersonalizado
type CustomValues = Record<string, string | number>
type StatusOption = { value: string; icon: string; label: string }
type IssueType = TipoDeIncidencia
/** Respuesta de `/semantic/suggest/task` (o el error que se guarda en su lugar). */
type SemSuggestion = Partial<SugerenciaDeAsignacion> & { error?: string }
type SemEffort = EstimacionDeEsfuerzo
type Sprint = { id: string; name?: string }
type KanbanConfig = ConfigDelTablero
type DragStartHandler = (e: React.MouseEvent, task: Task, onStarted: () => void) => void

// Tipos de la pantalla para lo que manda: los estados y prioridades salen de la URL y de
// los <select> como `string` (el servidor los valida contra sus enums), así que la
// adaptación al slice (`services/api/tasks.ts`, que sigue a app/schemas/tasks.py) es un
// `as` acotado en un único sitio (`tareas`). Auditoría 2026-11 (#25): el formulario guarda
// '' en horas, fechas y asignado vacíos, y el servidor responde 422 a un '' en un número,
// una fecha o un id. `tareas` los limpia: al crear los omite y al editar los manda como
// null (así se puede borrar el valor).
type TaskBody = Partial<Omit<TaskForm, 'issue_type'>> & { issue_type?: string | null; project_id?: string; move_reason?: string }
/** Campos opcionales en los que '' significa «sin valor». */
const CAMPOS_VACIABLES = ['estimated_hours', 'start_date', 'due_date', 'assignee_id', 'supplier_id', 'supplier_work_package_id'] as const
function limpiarVacios(body: TaskBody, modo: 'omitir' | 'anular'): Record<string, unknown> {
  const limpio: Record<string, unknown> = { ...body }
  for (const campo of CAMPOS_VACIABLES) {
    if (limpio[campo] !== '') continue
    if (modo === 'omitir') delete limpio[campo]
    else limpio[campo] = null
  }
  return limpio
}
type TaskListQuery = {
  project_id?: string
  status?: string
  search?: string
  priority?: string
  assignee_id?: string
  overdue_only?: boolean
  assigned_to_me?: boolean
  sprint_id?: string
  page_size?: number
}
type BulkBody = { task_ids: string[]; status?: string; assignee_id?: string; priority?: string }
type BulkResult = { updated?: number; skipped?: unknown[] }
const tareas = {
  list:       (q: TaskListQuery) => tasksApi.list(q as TaskListParams),
  create:     (body: TaskBody) => tasksApi.create(limpiarVacios(body, 'omitir') as unknown as TaskCreatePayload),
  update:     (id: string, body: TaskBody) => tasksApi.update(id, limpiarVacios(body, 'anular') as TaskUpdatePayload),
  comment:    (id: string, content: string) => tasksApi.comment(id, { content }),
  bulkUpdate: (body: BulkBody) => tasksApi.bulkUpdate(body as TaskBulkUpdatePayload),
}
// Revisión 2026-11: las cabeceras del tablero salían en castellano con la interfaz en
// otro idioma (tabla fija de helpers.ts, borrada el 19-11-2026); estas son las claves de i18n.
const CLAVE_DE_ESTADO: Record<string, string> = {
  backlog: 'tasks.status_backlog', todo: 'tasks.status_todo', in_progress: 'tasks.status_in_progress',
  in_review: 'tasks.status_review', blocked: 'tasks.status_blocked', done: 'tasks.status_done', cancelled: 'tasks.status_cancelled',
}

// AIInlineEditor y Tabs solo aceptan `style` (pintan su propio estilo en linea).
const ESTILO_EDITOR: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box', resize: 'vertical' }
const ESTILO_EDITOR_DETALLE: CSSProperties = { ...ESTILO_EDITOR, padding: '9px 13px', lineHeight: 1.6 }
const ESTILO_EDITOR_ALTA: CSSProperties = { ...ESTILO_EDITOR, padding: '10px 14px' }

/** Icono de cada vista de trabajo del planificador en la barra de pestañas. */
const ICONO_DE_VISTA: Record<string, ReactNode> = {
  table: <Table2 size={14} />, timeline: <GanttChartSquare size={14} />,
  calendar: <CalendarRange size={14} />, workload: <Users size={14} />,
}

/** Pulsación dentro de la casilla de selección de una fila: no abre la tarea. */
const desdeCasilla = (event: { target: EventTarget }) => !!(event.target as HTMLElement).closest?.('.ui-casilla')

function onKeyboardActivate(event: React.KeyboardEvent, action: () => void) {
  if (desdeCasilla(event)) return
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}


// 19-11-2026: las columnas salen del catálogo de estados de tarea de la empresa
// (`useCatalogo('task-statuses')`); `COLUMNAS_DE_TABLERO` es el respaldo.
/** «Abiertas»: lo que el servidor entiende por el filtro rápido de estado (todo menos hecho). */
const ESTADOS_ABIERTOS = 'backlog,todo,in_progress,blocked,in_review'
// Tope de tareas que se piden (el máximo del endpoint); si hay más, se avisa.
const TAREAS_MAXIMAS = 500
const PRIORIDADES = ['critical', 'high', 'medium', 'low']
const CLAVE_DE_PRIORIDAD: Record<string, string> = {
  critical: 'tasks.priority_critical', high: 'tasks.priority_high', medium: 'tasks.priority_medium', low: 'tasks.priority_low',
}
/** Nombre del estado en el idioma activo (el del flujo del proyecto si no es uno de los conocidos). */
const nombreDeEstado = (t: Traductor, status: string) => CLAVE_DE_ESTADO[status] ? t(CLAVE_DE_ESTADO[status]) : etiquetaDeEstado(t as never, status)
const nombreDePrioridadT = (t: Traductor, p?: string | null) => (p && CLAVE_DE_PRIORIDAD[p]) ? t(CLAVE_DE_PRIORIDAD[p]) : (p || '')
/** Complejidad que devuelve /semantic/estimate (simple | medium | complex). */
const COMPLEJIDADES = ['simple', 'medium', 'complex']
const nombreDeComplejidad = (t: Traductor, c?: string | null) => c && COMPLEJIDADES.includes(c) ? t(`tasks.complejidad_${c}`) : (c || '')

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
function HistorialDeMovimientos({ taskId }: { taskId: string }) {
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
    <input autoFocus value={titulo} placeholder={t('tasks.kanban_alta_titulo')} aria-label={t('tasks.kanban_alta_titulo')}
      onChange={e => setTitulo(e.target.value)} onBlur={() => !titulo && setAbierta(false)}
      onKeyDown={e => { if (e.key === 'Enter') enviar(); if (e.key === 'Escape') { setAbierta(false); setTitulo('') } }}
      className="ds-input tsk-quick-add-input" />
  )
}

function KanbanColumn({ status, tasks, onTaskClick, onTaskDragStart, onColumnEnter, onColumnLeave, dragOver, wipLimit, onSetWip, onCrear }: { status: string; tasks: Task[]; onTaskClick: (t: Task) => void; onTaskDragStart?: DragStartHandler; onColumnEnter?: () => void; onColumnLeave?: () => void; dragOver?: boolean; wipLimit?: number | null; onSetWip?: (n: number | null) => void; onCrear?: (titulo: string) => Promise<unknown> }) {
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

function useWorkflowStatusOptions(projectId: string | undefined, t: Traductor): StatusOption[] {
  const { data } = useQuery<FlujoDelProyecto | null>({
    queryKey: ['project-workflow', projectId],
    queryFn: () => projectWorkflowsApi.get(projectId).then(r => r.data).catch(() => null),
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

function TaskDetailModal({ task, open, onClose }: { task: Task | null; open: boolean; onClose: () => void }) {
  const idCampo = useId()
  const puedeBorrar = useAuth().puede('tareas.gestionar')
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { invalidate: _invalidate } = useInvalidate()
  const [tab, setTab]         = useState('detail')  // detail | comments | docs
  const [isEditing, setIsEditing] = useState(false)
  const [comment, setComment] = useState('')
  const [form, setForm]       = useState<TaskForm | null>(null)
  const [semSuggestion, setSemSuggestion] = useState<SemSuggestion | null>(null)
  const [semEffort, setSemEffort]         = useState<SemEffort | null>(null)
  const [suggesting, setSuggesting]       = useState(false)
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null

  // Reset editing mode and form whenever the task changes or modal opens
  useEffect(() => {
    if (task) {
      setIsEditing(false)
      setForm({
        title:           task.title           || '',
        description:     task.description     || '',
        status:          task.status          || 'todo',
        priority:        task.priority        || 'medium',
        assignee_id:     task.assignee_id     || task.assignee?.id || '',
        supplier_id:     task.supplier_id     || '',
        supplier_work_package_id: task.supplier_work_package_id || '',
        estimated_hours: task.estimated_hours ?? '',
        start_date:      task.start_date      ? task.start_date.split('T')[0] : '',
        due_date:        task.due_date        ? task.due_date.split('T')[0] : '',
        blocked_reason:  task.blocked_reason  || '',
        tags:            task.tags            || '',
        issue_type:      task.issue_type      || '',
      })
    }
  }, [task])

  const { data: users = [] } = useQuery<PersonaVisible[]>({
    // Selector de personas: `/users/directory` sirve a cualquier rol (`/users` da 403 al subcontratado).
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
  })

  const statusOptions = useWorkflowStatusOptions(task?.project_id, t)

  // Auditoría 2026-11: el catálogo de /issue-types no llegaba a las tareas.
  const { data: issueTypes = [] } = useQuery<IssueType[]>({
    queryKey: ['issue-types', task?.project_id],
    queryFn: () => issueTypesApi.list(task.project_id).then(r => r.data).catch(() => []),
    enabled: !!task?.project_id,
    retry: false,
  })
  const { data: customFields = [] } = useQuery<CustomField[]>({
    queryKey: ['custom-fields', task?.project_id],
    queryFn: () => customFieldsApi.list(task.project_id).then(r => r.data).catch(() => []),
    enabled: !!task?.project_id,
    retry: false,
  })
  const { data: rawCustomValues } = useQuery<CustomFieldValue[]>({
    queryKey: ['custom-field-values', task?.id],
    queryFn: () => customFieldsApi.getValues(task.project_id, task.id).then(r => r.data).catch(() => []),
    enabled: !!task?.id && !!task?.project_id,
    retry: false,
  })
  const [customValues, setCustomValues] = useState<CustomValues>({})
  useEffect(() => {
    const map: CustomValues = {}
    ;(rawCustomValues ?? []).forEach(v => { map[v.field_id] = v.value ?? '' })
    setCustomValues(map)
  }, [rawCustomValues])

  const { mutate: saveTask, isPending: saving } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: async ({ taskData, cfValues, cfFields, taskId, projectId }: { taskData: TaskBody; cfValues: CustomValues; cfFields: CustomField[]; taskId: string; projectId: string }) => {
      await tareas.update(taskId, taskData)
      if (cfFields.length > 0) {
        const payload = cfFields.map(f => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await customFieldsApi.setValues(projectId, taskId, payload)
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['dash-my-tasks'] }); qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] }); qc.invalidateQueries({ queryKey: ['cal-tasks'] }); qc.invalidateQueries({ queryKey: ['kanban-board'] }); setIsEditing(false); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('common.error'))) },
  })

  const { mutate: deleteTask, isPending: deleting } = useMutation({
    mutationFn: () => tasksApi.delete(task.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['dash-my-tasks'] }); qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] }); qc.invalidateQueries({ queryKey: ['cal-tasks'] }); qc.invalidateQueries({ queryKey: ['kanban-board'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('common.error'))),
  })

  const { mutate: addComment, isPending: commenting } = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) => tareas.comment(id, content),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); setComment('') },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const analyzeWithAI = async () => {
    if (!form?.title) return
    setSuggesting(true); setSemSuggestion(null); setSemEffort(null)
    try {
      const [s, e] = await Promise.all([
        semanticApi.suggestTask({ title: form.title, description: form.description }),
        semanticApi.estimateEffort({ title: form.title, description: form.description }),
      ])
      setSemSuggestion(s.data); setSemEffort(e.data)
    } catch { /* noop */ } finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id) {
      setForm(f => f && asignacionExclusiva(f, 'assignee_id', semSuggestion.suggested_user_id || ''))
      // Persist SemAssignment so the feedback loop has a base row for this task
      semanticApi.recordAssignment({
        item_type: 'task',
        item_id: task.id,
        item_title: form.title || task.title || '',
        suggested_user_id: semSuggestion.suggested_user_id,
        accepted_user_id: semSuggestion.suggested_user_id,
        was_accepted: true,
        confidence: semSuggestion.confidence,
        needs_review: semSuggestion.needs_review,
        engine_mode: semSuggestion.engine_mode,
        reasoning: semSuggestion.reasoning,
      }).catch(() => { /* non-blocking */ })
    }
    if (semEffort?.base_hours && !form.estimated_hours)
      setForm(f => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
    setSemSuggestion(null); setSemEffort(null)
  }

  const cancelEdit = () => {
    // Revert form to current task values
    setForm({
      title:           task.title           || '',
      description:     task.description     || '',
      status:          task.status          || 'todo',
      priority:        task.priority        || 'medium',
      assignee_id:     task.assignee_id     || task.assignee?.id || '',
      supplier_id:     task.supplier_id     || '',
      supplier_work_package_id: task.supplier_work_package_id || '',
      estimated_hours: task.estimated_hours ?? '',
      start_date:      task.start_date      ? task.start_date.split('T')[0] : '',
      due_date:        task.due_date        ? task.due_date.split('T')[0] : '',
      blocked_reason:  task.blocked_reason  || '',
      tags:            task.tags            || '',
      issue_type:      task.issue_type      || '',
    })
    setSemSuggestion(null); setSemEffort(null)
    setIsEditing(false)
  }

  const set = (k: keyof TaskForm) => (e: { target: { value: string } }) => { campos.limpiar(k); setForm(f => ({ ...f, [k]: e.target.value })) }
  // 19-11-2026: persona o proveedor, excluyentes (422 `proveedor_asignacion_exclusiva` si van los dos).
  const asignar = (k: 'assignee_id' | 'supplier_id' | 'supplier_work_package_id', v: string) => {
    campos.limpiar(k)
    setForm(f => f && asignacionExclusiva(f, k, v))
  }
  if (!open || !task || !form) return null

  return (
    <Drawer onClose={onClose} ariaLabel={task.title || task.code || t('tasks.tarea')} width={520} zIndex={200}>
        {/* Drawer header */}
        <div className="tsk-drawer-head">
          <span className="tsk-drawer-code">{task.code}</span>
          <IconButton className="tsk-icon-btn" onClick={onClose} ariaLabel={t('common.close')}>
            <X size={16} />
          </IconButton>
        </div>
        {/* Scrollable body */}
        <div className="tsk-drawer-body">

      {/* Tabs */}
      <div className="tsk-drawer-tabs">
        <Tabs
          items={[
            { id: 'detail',   label: t('tasks.tab_details') },
            { id: 'comments', label: t('tasks.tab_comments'), count: task.comments?.length },
            { id: 'docs',     label: t('tasks.tab_docs') },
            { id: 'history',  label: t('tasks.tab_historial') },
          ]}
          active={tab}
          onChange={setTab}
          ariaLabel={t('tasks.tab_details')}
        />
      </div>

      {/* ── DETALLES / EDITAR ── */}
      {tab === 'detail' && !isEditing && (
        <div className="tsk-tab-panel">
          {/* Title */}
          <div className="tsk-detail-title">{task.title}</div>

          {/* Status + Priority row */}
          <div className="tsk-chips">
            <span className={`tsk-chip tsk-tone-s--${task.status}`}>
              {nombreDeEstado(t, task.status)}
            </span>
            <span className={`tsk-chip tsk-tone-p--${task.priority}`}>
              {nombreDePrioridadT(t, task.priority)}
            </span>
          </div>

          {/* Info grid */}
          <div className="tsk-info-grid">
            <div className="tsk-info">
              <div className="tsk-eyebrow">{t('tasks.assignee')}</div>
              {task.assignee ? (
                <div className="u-row-center-8">
                  <Avatar name={task.assignee.full_name} size={22} />
                  <span className="u-base-600">{task.assignee.full_name}</span>
                </div>
              ) : task.supplier_name ? (
                <span className="u-row-center-8 u-base-600" title={t('proveedores.externalizada_a', { nombre: task.supplier_name })}>
                  <Building2 size={14} aria-hidden />{t('proveedores.externalizada_a', { nombre: task.supplier_name })}
                </span>
              ) : <span className="tsk-base tsk-base--muted">{t('tasks.no_assignee')}</span>}
            </div>
            <div className="tsk-info">
              <div className="tsk-eyebrow">{t('tasks.hours_label')}</div>
              <span className="u-base-600">
                {t('tasks.horas_real', { h: fmtNumber(task.real_hours ?? 0, 1) })}
                {task.estimated_hours ? ` / ${t('tasks.horas_est', { h: fmtNumber(task.estimated_hours, 1) })}` : ''}
              </span>
            </div>
            {task.start_date && (
              <div className="tsk-info">
                <div className="tsk-eyebrow">{t('tasks.start_date_label')}</div>
                <span className="tsk-base">{fmtDate(task.start_date)}</span>
              </div>
            )}
            {task.due_date && (
              <div className="tsk-info">
                <div className="tsk-eyebrow">{t('tasks.due_date')}</div>
                <span className={`tsk-base${new Date(task.due_date) < new Date() && task.status !== 'done' ? ' tsk-base--overdue' : ''}`}>
                  {fmtDate(task.due_date)}
                </span>
              </div>
            )}
          </div>

          {/* Description */}
          {task.description && (
            <div className="tsk-info tsk-info--block">
              <div className="tsk-eyebrow tsk-eyebrow--mb6">{t('common.description')}</div>
              <div className="tsk-description">{task.description}</div>
            </div>
          )}

          {/* Blocked reason */}
          {task.status === 'blocked' && task.blocked_reason && (
            <div className="tsk-blocked">
              <div className="tsk-blocked-title"><Ban size={13} aria-hidden />{t('tasks.blocked_label')}</div>
              <div className="u-text2-base">{task.blocked_reason}</div>
            </div>
          )}

          {/* Tags */}
          {task.tags && (
            <div className="u-mb-14">
              <div className="tsk-eyebrow tsk-eyebrow--mb6">{t('tasks.tags_label')}</div>
              <div className="tsk-tags">
                {String(task.tags).split(',').filter(Boolean).map(tag => (
                  <span key={tag} className="tsk-tag">#{tag.trim()}</span>
                ))}
              </div>
            </div>
          )}

          {/* Custom fields (read-only) */}
          {customFields.length > 0 && (rawCustomValues?.length ?? 0) > 0 && (
            <div className="tsk-cf-block">
              <div className="tsk-eyebrow tsk-eyebrow--mb8">{t('tasks.custom_fields_label')}</div>
              <div className="tsk-cf-grid">
                {customFields.map(f => {
                  const val = customValues[f.id]
                  if (!val && val !== 0) return null
                  return (
                    <div key={f.id} className="tsk-cf">
                      <div className="tsk-cf-name">{f.name}</div>
                      <div className="tsk-cf-value">{String(val)}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Footer actions */}
          <div className="tsk-footer">
            {/* Borrar exige admin o pm en el servidor (revisión 2026-11) */}
            {puedeBorrar ? (
            <Button variant="ghost" className="tsk-borrar" icon={<Trash2 size={14} />} onClick={() => { openConfirmGlobal({ message: t('tasks.confirmar_eliminar'), onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}>
              {deleting ? t('tasks.deleting') : t('common.delete')}
            </Button>
            ) : <span />}
            <Button icon={<Pencil size={14} />} onClick={() => setIsEditing(true)}>{t('common.edit')}</Button>
          </div>
        </div>
      )}

      {/* ── MODO EDICIÓN ── */}
      {tab === 'detail' && isEditing && (
        <div className="tsk-tab-panel tsk-edit-grid">

          {/* Título */}
          <div className="u-col-full">
            <label id={`${idCampo}-1-et`} htmlFor={`${idCampo}-1`} className="tsk-label">{t('tasks.title_required')}</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-1-et`} value={form.title} onChange={set('title')} className="tsk-input" />
            {msg('title')}
          </div>

          {/* Estado + Prioridad */}
          <div>
            <label id={`${idCampo}-2-et`} htmlFor={`${idCampo}-2`} className="tsk-label">{t('common.status')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.status} onChange={set('status')} className="tsk-input">
              {statusOptions.map(o => (
                <option key={o.value} value={o.value}>{o.icon} {o.label}</option>
              ))}
            </Select>
            {msg('status')}
          </div>
          <div>
            <label id={`${idCampo}-3-et`} htmlFor={`${idCampo}-3`} className="tsk-label">{t('common.priority')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.priority} onChange={set('priority')} className="tsk-input">
              <option value="low">{t('tasks.priority_low')}</option>
              <option value="medium">{t('tasks.priority_medium')}</option>
              <option value="high">{t('tasks.priority_high')}</option>
              <option value="critical">{t('tasks.priority_critical')}</option>
            </Select>
            {msg('priority')}
          </div>

          {/* Asignado + botón IA */}
          <div className="u-col-full">
            <div className="tsk-label-row">
              <label id={`${idCampo}-asignado-et`} htmlFor={`${idCampo}-asignado`} className="tsk-label tsk-label--flush">{t('tasks.assignee')}</label>
              <Button size="xs" variant="ghost" icon={<Brain size={13} />} onClick={analyzeWithAI} disabled={!form.title} loading={suggesting}>
                {t('tasks.ai_suggest')}
              </Button>
            </div>
            <Select suelto placeholder={false} id={`${idCampo}-asignado`} value={form.assignee_id} onChange={e => asignar('assignee_id', e.target.value)} className="tsk-input">
              <option value="">{t('tasks.no_assignee')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </Select>
            {msg('assignee_id')}
            {(semSuggestion || semEffort) && !semSuggestion?.error && (
              <div className="tsk-ai" role="status">
                <div>
                  <div className="tsk-ai-title">{t('tasks.ai_analysis')}</div>
                  <div className="tsk-ai-items">
                    {semSuggestion?.suggested_user_name && (
                      <div>
                        <div className="u-text2-2xs">{t('tasks.ai_person_label')}</div>
                        <div className="u-base-700">{semSuggestion.suggested_user_name} <span className="tsk-ai-note">{Math.round((semSuggestion.confidence||0)*100)}%</span></div>
                      </div>
                    )}
                    {semEffort && (
                      <div>
                        <div className="u-text2-2xs">{t('tasks.ai_effort_label')}</div>
                        <div className="tsk-ai-value tsk-ai-value--warning">{fmtNumber(semEffort.base_hours, 1)}h <span className={`tsk-ai-cx tsk-cx--${semEffort.complexity}`}>{nombreDeComplejidad(t, semEffort.complexity)}</span></div>
                      </div>
                    )}
                  </div>
                </div>
                <div className="u-row-6">
                  <Button size="xs" onClick={acceptSuggestion}>{t('tasks.ai_apply')}</Button>
                  <IconButton className="tsk-icon-btn" onClick={() => { setSemSuggestion(null); setSemEffort(null) }} ariaLabel={t('tasks.descartar_sugerencia')}><X size={14} aria-hidden /></IconButton>
                </div>
              </div>
            )}
          </div>

          {/* Externalizar a un proveedor de outsourcing (excluyente con el asignado) */}
          <ExternalizarTarea projectId={task.project_id} supplierId={form.supplier_id} paqueteId={form.supplier_work_package_id}
            nombreActual={task.supplier_name} onChange={asignar} idBase={idCampo} claseEtiqueta="tsk-label" claseControl="tsk-input" error={msg} />

          <div>
            <label className="tsk-label" htmlFor={`${idCampo}-tipo`}>{t('tasks.issue_type')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-tipo`} value={form.issue_type} onChange={set('issue_type')} className="tsk-input">
              <option value="">—</option>
              {issueTypes.map(it => (
                <option key={it.id} value={it.value}>{it.icon} {it.name}</option>
              ))}
            </Select>
            {msg('issue_type')}
          </div>

          {/* Horas + Fechas */}
          <div>
            <label id={`${idCampo}-horas-et`} htmlFor={`${idCampo}-horas`} className="tsk-label">{t('tasks.estimated_hours')}</label>
            <input id={`${idCampo}-horas`} aria-labelledby={`${idCampo}-horas-et`} type="number" value={form.estimated_hours} onChange={set('estimated_hours')} className="tsk-input" placeholder={t('tasks.estimated_hours')} min="0" step="0.5" />
            {msg('estimated_hours')}
          </div>
          <div className="tsk-dates">
            <div>
              <label id={`${idCampo}-4-et`} htmlFor={`${idCampo}-4`} className="tsk-label">{t('tasks.date_start')}</label>
              <DateInput id={`${idCampo}-4`} aria-labelledby={`${idCampo}-4-et`} value={form.start_date} onChange={set('start_date')} className="tsk-input" />
              {msg('start_date')}
            </div>
            <div>
              <label id={`${idCampo}-5-et`} htmlFor={`${idCampo}-5`} className="tsk-label">{t('tasks.due_date')}</label>
              <DateInput id={`${idCampo}-5`} aria-labelledby={`${idCampo}-5-et`} value={form.due_date} onChange={set('due_date')} className="tsk-input" />
              {msg('due_date')}
            </div>
          </div>

          {/* Descripción */}
          <div className="u-col-full">
            <label id={`${idCampo}-descripcion-et`} htmlFor={`${idCampo}-descripcion`} className="tsk-label">{t('common.description')} <span className="tsk-label-hint">{t('tasks.description_hint')}</span></label>
            <AIInlineEditor inputId={`${idCampo}-descripcion`} value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={4} style={ESTILO_EDITOR_DETALLE} />
            {msg('description')}
          </div>

          {/* Motivo bloqueo */}
          {form.status === 'blocked' && (
            <div className="u-col-full">
              <label id={`${idCampo}-6-et`} htmlFor={`${idCampo}-6`} className="tsk-label">{t('tasks.blocked_reason')}</label>
              <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-6-et`} value={form.blocked_reason} onChange={set('blocked_reason')} className="tsk-input"
                placeholder={t('tasks.blocked_reason_placeholder')} />
              {msg('blocked_reason')}
            </div>
          )}

          {/* Tags */}
          <div className="u-col-full">
            <label id={`${idCampo}-7-et`} htmlFor={`${idCampo}-7`} className="tsk-label">{t('tasks.tags_label')}</label>
            <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-7-et`} value={form.tags} onChange={set('tags')} className="tsk-input" placeholder={t('tasks.tags_placeholder')} />
            {msg('tags')}
          </div>

          {/* Campos personalizados */}
          {customFields.length > 0 && (
            <div className="tsk-span-full-top">
              <div className="tsk-label tsk-label--mb10">{t('tasks.custom_fields_label')}</div>
              <div className="u-grid2-12">
                {customFields.map(f => (
                  <div key={f.id} className={(f.field_type === 'text' || f.field_type === 'url') ? 'u-col-full' : undefined}>
                    <label id={`${idCampo}-cf-${f.id}-et`} htmlFor={`${idCampo}-cf-${f.id}`} className="tsk-label">{f.name}{f.is_required ? ' *' : ''}</label>
                    {f.field_type === 'select' ? (
                      <Select suelto placeholder={false} id={`${idCampo}-cf-${f.id}`} value={customValues[f.id] ?? ''} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))} className="tsk-input">
                        <option value="">{t('tasks.select_option')}</option>
                        {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                      </Select>
                    ) : f.field_type === 'boolean' ? (
                      <div className="tsk-check-row">
                        <Checkbox id={`${idCampo}-cf-${f.id}`} checked={customValues[f.id] === 'true'} onChange={m => setCustomValues(v => ({ ...v, [f.id]: m ? 'true' : 'false' }))} className="tsk-check tsk-check--lg" />
                        <span className="u-text2-base">{customValues[f.id] === 'true' ? t('common.yes') : t('common.no')}</span>
                      </div>
                    ) : (
                      f.field_type === 'date' ? (
                        <DateInput
                          id={`${idCampo}-cf-${f.id}`} aria-labelledby={`${idCampo}-cf-${f.id}-et`}
                          value={String(customValues[f.id] ?? '')}
                          onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}
                          className="tsk-input"
                        />
                      ) : (
                        <input
                          id={`${idCampo}-cf-${f.id}`} aria-labelledby={`${idCampo}-cf-${f.id}-et`}
                          type={f.field_type === 'number' ? 'number' : f.field_type === 'url' ? 'url' : 'text'}
                          value={customValues[f.id] ?? ''}
                          onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}
                          className="tsk-input"
                        />
                      )
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Info solo lectura */}
          <div className="tsk-readonly">
            <span><Clock size={13} aria-hidden />{t('tasks.real_hours')}: <strong className="u-text1">{fmtNumber(task.real_hours ?? 0, 1)}h</strong></span>
            <span><CalendarClock size={13} aria-hidden />{t('tasks.created_label')}: <strong className="u-text1">{fmtDate(task.created_at)}</strong></span>
            {task.completed_at && <span><CheckCircle2 size={13} aria-hidden />{t('tasks.completed_label')}: <strong className="u-success">{fmtDate(task.completed_at)}</strong></span>}
          </div>

          {/* Acciones edición */}
          <div className="tsk-edit-actions">
            {/* Borrar exige admin o pm en el servidor (revisión 2026-11) */}
            {puedeBorrar ? (
            <Button variant="ghost" className="tsk-borrar" icon={<Trash2 size={14} />} onClick={() => { openConfirmGlobal({ message: t('tasks.confirmar_eliminar'), onConfirm: () => deleteTask(), danger: true }) }} disabled={deleting}>
              {deleting ? t('tasks.deleting') : t('common.delete')}
            </Button>
            ) : <span />}
            <div className="u-row-8">
              <Button variant="secondary" onClick={cancelEdit}>{t('common.cancel')}</Button>
              <Button icon={<Save size={14} />} onClick={() => saveTask({ taskData: { ...form, issue_type: form.issue_type || null }, cfValues: customValues, cfFields: customFields, taskId: task.id, projectId: task.project_id })} disabled={!form.title} loading={saving}>
                {saving ? t('common.saving') : t('tasks.save_changes')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── HISTORIAL de movimientos (revisión 2026-11: lo enseñaba la pantalla Kanban) ── */}
      {tab === 'history' && <HistorialDeMovimientos taskId={task.id} />}

      {/* ── COMENTARIOS ── */}
      {tab === 'comments' && (
        <div className="tsk-tab-panel">
          {(!task.comments || task.comments.length === 0) ? (
            <p className="tsk-empty-comments">{t('tasks.no_comments')}</p>
          ) : (
            <div className="tsk-comments">
              {task.comments.map(c => (
                <div key={c.id} className="u-row-10">
                  <Avatar name={c.author?.full_name || '?'} size={28} />
                  <div className="tsk-comment">
                    <div className="u-text2-xs-mb4">
                      <strong className="u-text1">{c.author?.full_name}</strong> · {fmtDate(c.created_at)}
                    </div>
                    <div className="tsk-comment-body">{c.content}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="u-row-8">
            <textarea aria-label={t('tasks.add_comment')} value={comment} onChange={e => setComment(e.target.value)}
              placeholder={t('tasks.add_comment')}
              rows={2}
              className="tsk-comment-input"
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && comment) addComment({ id: task.id, content: comment }) }}
            />
            <Button onClick={() => addComment({ id: task.id, content: comment })} disabled={!comment || commenting}>{t('tasks.send_comment')}</Button>
          </div>
          <div className="u-hint">{t('tasks.send_hint')}</div>
        </div>
      )}

      {/* ── DOCUMENTOS ── */}
      {tab === 'docs' && (
        <div className="tsk-tab-panel">
          <DocumentsPanel taskId={task.id} />
        </div>
      )}
        </div>
    </Drawer>
  )
}

export default function TasksPage() {
  const traducir = useAppT()
  const estadosDeTarea = useCatalogo('task-statuses')
  const STATUSES = estadosDeTarea.valores.length
    ? estadosDeTarea.valores.map(v => v.value).filter(v => v !== 'backlog' && v !== 'cancelled')
    : COLUMNAS_DE_TABLERO
  const t = useAppT()
  const { puede } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  // ── Kanban drag-and-drop state ────────────────────────────────────────────
  const dragTask      = useRef<Task | null>(null)
  const ghostRef      = useRef<HTMLDivElement | null>(null)
  const dropTargetRef = useRef<string | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)

  const cleanupGhost = useCallback(() => {
    if (ghostRef.current) { ghostRef.current.remove(); ghostRef.current = null }
  }, [])

  const { mutate: moveTaskStatus } = useMutation({
    mutationFn: ({ id, status, move_reason }: { id: string; status: string; move_reason?: string }) =>
      tareas.update(id, { status, ...(move_reason ? { move_reason } : {}) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
    },
    onError: (e: Error) => toast.error((e as ApiError)?.response?.data?.detail || t('tasks.error_mover')),
  })

  const requestMoveTask = useCallback(async (id: string, fromStatus: string, toStatus: string) => {
    if (fromStatus === toStatus) return
    let move_reason
    if (fromStatus === 'done' || fromStatus === 'cancelled') {
      move_reason = await pedirTexto({
        title: t('tasks.mover_cerrada_titulo'),
        message: t('tasks.mover_cerrada_mensaje', { estado: nombreDeEstado(t, fromStatus) }),
        label: t('tasks.motivo'),
        multiline: true,
        confirmLabel: t('tasks.mover'),
      })
      if (move_reason === null) return
      move_reason = move_reason.trim() || undefined
    }
    moveTaskStatus({ id, status: toStatus, move_reason })
  }, [moveTaskStatus, t])

  const handleTaskDragStart = useCallback((e: React.MouseEvent, task: Task, onDragStarted: () => void) => {
    const startX = e.clientX
    const startY = e.clientY
    let dragging = false

    const onMove = (ev: MouseEvent) => {
      if (!dragging) {
        const dx = ev.clientX - startX
        const dy = ev.clientY - startY
        if (Math.sqrt(dx * dx + dy * dy) < 5) return
        dragging = true
        dragTask.current = task
        onDragStarted()
        const ghost = document.createElement('div')
        ghost.textContent = task.title
        ghost.className = 'tsk-drag-ghost'
        ghost.style.left = ev.clientX + 12 + 'px'
        ghost.style.top  = ev.clientY + 12 + 'px'
        document.body.appendChild(ghost)
        ghostRef.current = ghost
      } else if (ghostRef.current) {
        ghostRef.current.style.left = ev.clientX + 12 + 'px'
        ghostRef.current.style.top  = ev.clientY + 12 + 'px'
      }
    }

    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      cleanupGhost()
      if (dragging) {
        const target = dropTargetRef.current
        if (dragTask.current && target && dragTask.current.status !== target) {
          requestMoveTask(dragTask.current.id, dragTask.current.status, target)
        }
      }
      dragTask.current = null
      dropTargetRef.current = null
      setDropTarget(null)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    // `requestMoveTask` se invoca dentro de onUp y no estaba declarada
    // (auditoría 2026-08, P1-6): los listeners capturaban una versión antigua
    // del callback, así que un arrastre podía mover la tarea con estado viejo.
  }, [cleanupGhost, requestMoveTask])

  const handleColumnEnter = useCallback((status: string) => {
    dropTargetRef.current = status
    setDropTarget(status)
  }, [])
  const handleColumnLeave = useCallback(() => {}, [])
  const [searchParams, setSearchParams] = useSearchParams()
  const view           = searchParams.get('view') || 'kanban'
  const projectFilter  = searchParams.get('project_id') || ''
  const statusFilter   = searchParams.get('status') || ''
  const search         = searchParams.get('search') || ''
  const priorityFilter = searchParams.get('priority') || ''
  const assigneeFilter = searchParams.get('assignee') || ''
  const overdueOnly    = searchParams.get('overdue') === '1'
  const mineOnly       = searchParams.get('mine') === '1'
  const sprintFilter   = searchParams.get('sprint') || ''
  const carriles       = searchParams.get('lanes') || ''
  const setTaskParam = (k: string, v: string) => setSearchParams(p => { const n = new URLSearchParams(p); v ? n.set(k, v) : n.delete(k); return n }, { replace: true })
  const setView           = (v: string) => setTaskParam('view', v === 'kanban' ? '' : v)
  const setProjectFilter  = (v: string) => setTaskParam('project_id', v)
  const setStatusFilter   = (v: string) => setTaskParam('status', v)
  const setSearch         = (v: string) => setTaskParam('search', v)
  const setPriorityFilter = (v: string) => setTaskParam('priority', v)
  const setAssigneeFilter = (v: string) => setTaskParam('assignee', v)
  const setSprintFilter   = (v: string) => setTaskParam('sprint', v)
  const clearQuickFilters = () => setSearchParams(p => {
    const n = new URLSearchParams(p)
    n.delete('mine')
    n.delete('overdue')
    if (n.get('status') === 'open') n.delete('status')
    return n
  }, { replace: true })
  const quickFilterPills = [
    mineOnly ? { key: 'mine', label: t('tasks.filtro_mis_tareas'), onClear: () => setTaskParam('mine', '') } : null,
    overdueOnly ? { key: 'overdue', label: t('tasks.filtro_vencidas'), onClear: () => setTaskParam('overdue', '') } : null,
    statusFilter === 'open' ? { key: 'open', label: t('tasks.filtro_estado_abiertas'), onClear: () => setTaskParam('status', '') } : null,
  ].filter(Boolean)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [smartScheduleOpen, setSmartScheduleOpen] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())  // bulk selection
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth)

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const isCompact = viewportWidth <= 1024
  const isMobile = viewportWidth <= 768

  // Bulk action state
  const [bulkStatus, setBulkStatus] = useState('')
  const [bulkAssignee, setBulkAssignee] = useState('')
  const [bulkPriority, setBulkPriority] = useState('')

  const { data: projects = [] } = useQuery<ProjectListItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  // Revisión 2026-11: tablero y lista enseñan LAS MISMAS tareas (la misma consulta
  // y los mismos filtros). Antes el tablero con proyecto usaba otro endpoint que
  // ignoraba persona, vencidas y «mías», y la lista se cortaba en 50 sin avisar.
  const { data: tasksData, isLoading } = useQuery<{ items: Task[]; total: number }>({
    queryKey: ['tasks', view, projectFilter, statusFilter, search, priorityFilter, assigneeFilter, overdueOnly, mineOnly, sprintFilter],
    queryFn: () => {
      const effectiveStatus = statusFilter === 'open'
        ? ESTADOS_ABIERTOS
        : (statusFilter || undefined)
      return tareas.list({
        project_id: projectFilter || undefined,
        status: view === 'kanban' ? undefined : effectiveStatus,
        search: search || undefined,
        priority: priorityFilter || undefined,
        assignee_id: assigneeFilter || undefined,
        overdue_only: overdueOnly || undefined,
        assigned_to_me: mineOnly || undefined,
        sprint_id: (projectFilter && sprintFilter) || undefined,
        page_size: TAREAS_MAXIMAS,
      }).then(r => {
        const d = r.data as Task[] | { items?: Task[]; total?: number }
        const items = Array.isArray(d) ? d : (d?.items ?? [])
        const total = Number(r.headers?.['x-total-count'] ?? (Array.isArray(d) ? undefined : d?.total) ?? items.length)
        return { items, total }
      })
    },
    placeholderData: prev => prev,
  })

  const projectOptions = projects.map(p => ({ value: p.id, label: `${p.code} — ${p.name}` }))

  const flatTasks: Task[] = tasksData?.items ?? []
  const cortadas = (tasksData?.total ?? 0) > flatTasks.length

  const { sort: taskSort, setSort: setTaskSort, sortedData: sortedTasks } = useSort(flatTasks, 'title')

  // Revisión 2026-11: sin proyecto el Kanban caía en una lista. Ahora agrupa por
  // estado las mismas tareas que mostraría la lista (con sus filtros).
  const agrupar = (lista: Task[]) => lista.reduce<Record<string, Task[]>>((a, task) => {
    if (task.status !== 'cancelled') (a[task.status] = a[task.status] || []).push(task)
    return a
  }, STATUSES.reduce<Record<string, Task[]>>((a, s) => ({ ...a, [s]: [] }), {}))
  const kanbanColumns = agrupar(flatTasks)

  // ── Tablero: sprint, carriles y límites WIP (revisión 2026-11) ───────────────
  // Venían de la pantalla «Kanban» (/kanban-advanced), que enseñaba las mismas
  // tareas por estado; ahora es una sola. Carriles y WIP se guardan por proyecto
  // (`/cmdb/kanban/{proyecto}`): antes los límites vivían en memoria y se perdían.
  const puedeConfigurar = puede('tareas.gestionar')
  const { data: sprintsDelProyecto = [] } = useQuery<Sprint[]>({
    queryKey: ['sprints', projectFilter], enabled: !!projectFilter,
    queryFn: () => sprintsApi.list(projectFilter).then(r => r.data ?? []),
  })
  const { data: tablero } = useQuery<KanbanConfig>({
    queryKey: ['kanban-config', projectFilter], enabled: !!projectFilter,
    queryFn: () => cmdbApi.kanbanConfig(projectFilter).then(r => r.data),
  })
  const carril = carriles || (projectFilter && tablero?.swimlane_by) || 'none'
  const limiteWip = (status: string): number | null =>
    (tablero?.columns || []).find(c => c.status === status)?.wip_limit ?? null
  const guardarCarril = async (v: string) => {
    setTaskParam('lanes', v === 'none' ? '' : v)
    if (projectFilter && puedeConfigurar) {
      try { await cmdbApi.saveKanbanConfig(projectFilter, { swimlane_by: v }); qc.invalidateQueries({ queryKey: ['kanban-config', projectFilter] }) }
      catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
    }
  }
  const guardarWip = async (status: string, n: number | null) => {
    try {
      if (!tablero?.configured) await cmdbApi.saveKanbanConfig(projectFilter, { swimlane_by: carril })
      const col = (tablero?.columns || []).find(c => c.status === status)
      if (col) await cmdbApi.updateKanbanColumn(col.id, { status, wip_limit: n })
      else await cmdbApi.addKanbanColumn(projectFilter, { status, wip_limit: n })
      qc.invalidateQueries({ queryKey: ['kanban-config', projectFilter] })
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const crearEnColumna = (status: string) => async (titulo: string) => {
    try {
      await tareas.create({ title: titulo, status, project_id: projectFilter })
      qc.invalidateQueries({ queryKey: ['tasks'] })
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
    const filasDelTablero: { id: string; titulo: string | null; tareas: Task[] }[] = (() => {
    if (carril === 'assignee') {
      const g: Record<string, { id: string; titulo: string; tareas: Task[] }> = {}
      for (const task of flatTasks) {
        const k = task.assignee_id || '__sin'
        g[k] = g[k] || { id: k, titulo: task.assignee?.full_name || t('tasks.no_assignee'), tareas: [] }
        g[k].tareas.push(task)
      }
      return Object.values(g).sort((a, b) => a.titulo.localeCompare(b.titulo))
    }
    if (carril === 'priority') {
      return ['critical', 'high', 'medium', 'low']
        .map(p => ({ id: p, titulo: nombreDePrioridadT(t, p), tareas: flatTasks.filter(x => x.priority === p) }))
        .filter(f => f.tareas.length)
    }
    return [{ id: 'todas', titulo: null, tareas: flatTasks }]
  })()
  const buscador = useRef<HTMLInputElement | null>(null)
  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      const dentro = (e.target as HTMLElement)?.closest?.('input, textarea, select, [contenteditable=true]')
      if (e.key === '/' && !dentro) { e.preventDefault(); buscador.current?.focus() }
    }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [])
  // El servidor devuelve «backlog»; antes no tenía columna y esas tareas no se veían.
  const kanbanStatuses = (kanbanColumns.backlog?.length ? ['backlog'] : []).concat(STATUSES)

  // ── Bulk operations ──────────────────────────────────────────────────────
  const { data: allUsers = [] } = useQuery<PersonaVisible[]>({
    // Selector de personas: `/users/directory` sirve a cualquier rol (`/users` da 403 al subcontratado).
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })

  const { mutate: bulkMutate, isPending: bulkPending } = useMutation({
    mutationFn: (payload: BulkBody) => tareas.bulkUpdate(payload),
    onSuccess: res => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-my-tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] })
      qc.invalidateQueries({ queryKey: ['cal-tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
      const data: BulkResult = res.data
      const n = data?.updated ?? 0
      const s = data?.skipped?.length ?? 0
      toast.success(t(n === 1 ? 'tasks.bulk_actualizada_1' : 'tasks.bulk_actualizadas', { n })
        + (s > 0 ? ` · ${t(s === 1 ? 'tasks.bulk_omitida_1' : 'tasks.bulk_omitidas', { n: s })}` : ''))
      setSelected(new Set())
      setBulkStatus(''); setBulkAssignee(''); setBulkPriority('')
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('tasks.bulk_error'))),
  })

  const toggleSelect = (id: string) => setSelected(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const toggleAll = () => setSelected(prev =>
    prev.size === flatTasks.length ? new Set<string>() : new Set<string>(flatTasks.map(t => t.id))
  )
  const applyBulk = () => {
    if (selected.size === 0) return
    const payload: BulkBody = { task_ids: [...selected] }
    if (bulkStatus)   payload.status = bulkStatus
    if (bulkAssignee) payload.assignee_id = bulkAssignee
    if (bulkPriority) payload.priority = bulkPriority
    if (!payload.status && !payload.assignee_id && !payload.priority) {
      toast.error(t('tasks.bulk_sin_campos'))
      return
    }
    bulkMutate(payload)
  }

  // ── Barra de filtros única ───────────────────────────────────────────────
  const esVistaDeTrabajo = (VISTAS_DE_TRABAJO as readonly string[]).includes(view)
  // La carga por persona solo depende del proyecto: el resto de filtros no se enseña.
  const soloProyecto = view === 'workload'
  const filtrosDeVistas: FiltrosDeVistas = {
    status: (statusFilter === 'open' ? ESTADOS_ABIERTOS : statusFilter) || undefined,
    search: search || undefined,
    priority: (priorityFilter || undefined) as FiltrosDeVistas['priority'],
    assignee_id: assigneeFilter || undefined,
    overdue_only: overdueOnly || undefined,
    assigned_to_me: mineOnly || undefined,
    sprint_id: (projectFilter && sprintFilter) || undefined,
  }
  const aplicarFiltrosDeVista = ({ status, assignee }: { status?: string; assignee?: string }) => setSearchParams(p => {
    const n = new URLSearchParams(p)
    const estado = status === ESTADOS_ABIERTOS ? 'open' : status
    estado ? n.set('status', estado) : n.delete('status')
    assignee ? n.set('assignee', assignee) : n.delete('assignee')
    return n
  }, { replace: true })
  const controlesDeFiltro = (
    <>
      {!soloProyecto && (
        <div className="tsk-search">
          <Search size={14} aria-hidden className="tsk-search-icon" />
          <input aria-label={t('tasks.search_placeholder')} ref={buscador} value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('tasks.search_placeholder')} aria-keyshortcuts="/"
            className="ds-input tsk-search-input" />
        </div>
      )}
      <Select suelto placeholder={false} aria-label={t('tasks.all_projects')} value={projectFilter} onChange={e => setProjectFilter(e.target.value)}
        className="tsk-filter--project">
        <option value="">{t('tasks.all_projects')}</option>
        {projectOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </Select>
      {!soloProyecto && (
        <>
          <Select suelto placeholder={false} aria-label={t('tasks.filter_priority')} value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}
            className={`tsk-filter${priorityFilter ? ' tsk-filter--accent' : ''}`}>
            <option value="">{t('tasks.filter_priority')}</option>
            {PRIORIDADES.map(p => <option key={p} value={p}>{nombreDePrioridadT(t, p)}</option>)}
          </Select>
          <Select suelto placeholder={false} aria-label={t('tasks.all_assignees')} value={assigneeFilter} onChange={e => setAssigneeFilter(e.target.value)}
            className={`tsk-filter${assigneeFilter ? ' tsk-filter--accent' : ''}`}>
            <option value="">{t('tasks.all_assignees')}</option>
            {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
          {projectFilter && sprintsDelProyecto.length > 0 && (
            <Select suelto placeholder={false} aria-label={t('tasks.kanban_sprint')} value={sprintFilter} onChange={e => setSprintFilter(e.target.value)}
              className={`tsk-filter${sprintFilter ? ' tsk-filter--accent' : ''}`}>
              <option value="">{t('tasks.kanban_todos_los_sprints')}</option>
              {sprintsDelProyecto.map(sp => <option key={sp.id} value={sp.id}>{sp.name}</option>)}
            </Select>
          )}
        </>
      )}
      {view === 'kanban' && (
        <Select suelto placeholder={false} aria-label={t('tasks.kanban_carriles')} value={carril} onChange={e => guardarCarril(e.target.value)}
          className="tsk-filter">
          <option value="none">{t('tasks.kanban_sin_carriles')}</option>
          <option value="assignee">{t('tasks.kanban_carril_persona')}</option>
          <option value="priority">{t('tasks.kanban_carril_prioridad')}</option>
        </Select>
      )}
      {(view === 'list' || (esVistaDeTrabajo && !soloProyecto)) && (
        <Select suelto placeholder={false} aria-label={t('tasks.filter_status')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="tsk-filter">
          <option value="">{t('tasks.filter_status')}</option>
          <option value="open">{t('tasks.estado_abiertas')}</option>
          {STATUSES.map(v => <option key={v} value={v}>{nombreDeEstado(t, v)}</option>)}
        </Select>
      )}
    </>
  )

  return (
    <PageShell>
      <PageHeader
        icon={<CheckSquare size={18} />}
        title={t('tasks.title')}
        subtitle={t('tasks.subtitle')}
        exportTargetSelector='[data-export-table="tasks-list"]'
        exportFilePrefix='tasks'
        actions={
          <div className={`tsk-header-actions${isMobile ? ' tsk-header-actions--full' : ''}`}>
            {/* I27: Auto-planificar. Aplicar las fechas (bulk-dates) exige admin o pm. */}
            {puede('tareas.gestionar') && (
              <Button
                variant="secondary"
                icon={<Sparkles size={14} />}
                onClick={() => setSmartScheduleOpen(true)}
                title={traducir('tasks.sugerir_fechas_para_tareas_sin_planificar_usando')}
              >
                {t('tasks.auto_planificar')}
              </Button>
            )}
            {puede('tareas.crear') && (
              <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>
                {t('tasks.new_task')}
              </Button>
            )}
          </div>
        }
      />

      {/* Vista: tablero, lista y (rev. 173) tabla editable, línea temporal, calendario y carga por persona */}
      <div className="tsk-views">
        <Tabs
          ariaLabel={t('tasks.vista')}
          active={view}
          onChange={setView}
          items={[
            { id: 'kanban', label: t('tasks.vista_kanban'), icon: <LayoutGrid size={14} /> },
            { id: 'list', label: t('tasks.vista_lista'), icon: <List size={14} /> },
            ...VISTAS_DE_TRABAJO.map(v => ({ id: v, label: t(`planificador.vista_${v}`), icon: ICONO_DE_VISTA[v] })),
          ]}
        />
      </div>

      {/* Quick filter pills */}
      {quickFilterPills.length > 0 && (
        <div className="ds-row-wrap tsk-pills">
          {quickFilterPills.map(pill => (
            <Chip key={pill.key} activo onQuitar={pill.onClear}>{pill.label}</Chip>
          ))}
          <Button variant="link" size="sm" onClick={clearQuickFilters}>
            {traducir('tasks.limpiar_filtros_rapidos')}
          </Button>
        </div>
      )}

      {/* Una sola barra de filtros (17-11-2026): en tablero y lista es la de la
          página; en las vistas de trabajo, estos mismos controles encabezan la
          barra de VistasDeTrabajo (columnas y vistas guardadas). Los filtros
          viven en la URL. */}
      {!esVistaDeTrabajo && (
        <BarraDeFiltros className="tsk-toolbar">
          {controlesDeFiltro}
        </BarraDeFiltros>
      )}

      {/* ── Bulk Action Bar ─────────────────────────────────────────────── */}
      {selected.size > 0 && (
        <div className="tsk-bulk" role="region" aria-label={t('tasks.acciones_masivas')}>
          <span className="tsk-bulk-count">
            <CheckSquare size={13} aria-hidden /> {selected.size} {t('tasks.selected')}
          </span>
          <div className="tsk-bulk-sep" aria-hidden="true" />
          <Select suelto placeholder={false} aria-label={t('tasks.bulk_status_ph')} value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}
            className="ds-input tsk-bulk-select">
            <option value="">{t('tasks.bulk_status_ph')}</option>
            <option value="todo">{t('tasks.status_todo')}</option>
            <option value="in_progress">{t('tasks.status_in_progress')}</option>
            <option value="in_review">{t('tasks.status_review')}</option>
            <option value="blocked">{t('tasks.status_blocked')}</option>
            <option value="done">{t('tasks.status_done')}</option>
          </Select>
          <Select suelto placeholder={false} aria-label={t('tasks.bulk_priority_ph')} value={bulkPriority} onChange={e => setBulkPriority(e.target.value)}
            className="ds-input tsk-bulk-select">
            <option value="">{t('tasks.bulk_priority_ph')}</option>
            <option value="low">{t('tasks.priority_low')}</option>
            <option value="medium">{t('tasks.priority_medium')}</option>
            <option value="high">{t('tasks.priority_high')}</option>
            <option value="critical">{t('tasks.priority_critical')}</option>
          </Select>
          <Select suelto placeholder={false} aria-label={t('tasks.bulk_assignee_ph')} value={bulkAssignee} onChange={e => setBulkAssignee(e.target.value)}
            className="ds-input tsk-bulk-select">
            <option value="">{t('tasks.bulk_assignee_ph')}</option>
            {allUsers.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
          <Button size="sm" onClick={applyBulk}
            disabled={bulkPending || (!bulkStatus && !bulkPriority && !bulkAssignee)}>
            {bulkPending
              ? <><Loader2 size={12} className="tsk-spin" aria-hidden /> {t('tasks.aplicando')}</>
              : t('tasks.bulk_apply')}
          </Button>
          <Button size="sm" variant="secondary"
            onClick={() => { setSelected(new Set()); setBulkStatus(''); setBulkPriority(''); setBulkAssignee('') }}>
            {t('common.cancel')}
          </Button>
        </div>
      )}

      {cortadas && (
        <div role="status" className="tsk-truncated">
          {t('tasks.mostrando_de', { n: flatTasks.length, total: tasksData?.total ?? 0 })}
        </div>
      )}
      {esVistaDeTrabajo ? (
        <VistasDeTrabajo projectId={projectFilter || undefined} vista={view as VistaDeTrabajo} onVista={setView}
          filtros={filtrosDeVistas} filtrosDePagina={controlesDeFiltro} onFiltros={aplicarFiltrosDeVista} />
      ) : isLoading ? (
        <SkeletonTable rows={10} />
      ) : view === 'kanban' ? (
        flatTasks.length === 0 && !projectFilter ? (
          <EmptyState
            icon={<CheckSquare size={28} />}
            title={t('tasks.no_tasks')}
            description={puede('tareas.crear') ? t('tasks.vacio_desc_crear') : t('tasks.vacio_desc')}
            action={puede('tareas.crear') ? <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('tasks.new_task')}</Button> : undefined}
          />
        ) : (
          <div className="tsk-board">
            {filasDelTablero.map(fila => {
              const columnas = agrupar(fila.tareas)
              return (
                <section key={fila.id} aria-label={fila.titulo || undefined}>
                  {fila.titulo && (
                    <div className="tsk-lane-title">
                      {fila.titulo} <span className="tsk-lane-count">· {fila.tareas.length}</span>
                    </div>
                  )}
                  <div className={`tsk-lane${isCompact ? ' tsk-lane--compact' : ''}`}>
                    {kanbanStatuses.map(status => (
                      <KanbanColumn
                        key={status}
                        status={status}
                        tasks={columnas[status] || []}
                        onTaskClick={setSelectedTask}
                        onTaskDragStart={handleTaskDragStart}
                        onColumnEnter={() => handleColumnEnter(status)}
                        onColumnLeave={handleColumnLeave}
                        dragOver={dropTarget === status}
                        wipLimit={fila.titulo ? null : limiteWip(status)}
                        onSetWip={projectFilter && puedeConfigurar && !fila.titulo ? (n => guardarWip(status, n)) : undefined}
                        onCrear={projectFilter && !fila.titulo ? crearEnColumna(status) : undefined}
                      />
                    ))}
                  </div>
                </section>
              )
            })}
          </div>
        )
      ) : (
        flatTasks.length === 0 ? (
          <EmptyState icon={<Search size={28} />} title={t('common.no_results')} description={t('tasks.sin_resultados_desc')} />
        ) : isCompact ? (
          <div className="u-stack-10">
            {sortedTasks.map((task) => {
              const proj = projects.find(p => p.id === task.project_id)
              return (
                <div key={task.id}
                  onClick={e => { if (!desdeCasilla(e)) setSelectedTask(task) }}
                  onKeyDown={e => onKeyboardActivate(e, () => setSelectedTask(task))}
                  role="button"
                  tabIndex={0}
                  className="tsk-mcard"
                >
                  <div className="tsk-mcard-head">
                    <Checkbox
                      aria-label={task.title}
                      checked={selected.has(task.id)}
                      onChange={() => toggleSelect(task.id)}
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
              <Checkbox aria-label={t('reportbuilder.seleccionar_todos')} checked={selected.size === flatTasks.length && flatTasks.length > 0} onChange={toggleAll} className="tsk-check" />
              <SortableTH col="title" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_task')}</SortableTH>
              <SortableTH col="project_id" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_project')}</SortableTH>
              <SortableTH col="assignee.full_name" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_assignee')}</SortableTH>
              <SortableTH col="estimated_hours" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_est')}</SortableTH>
              <SortableTH col="real_hours" sort={taskSort} onSort={setTaskSort}>{t('tasks.col_real')}</SortableTH>
              <SortableTH col="status" sort={taskSort} onSort={setTaskSort}>{t('common.status')}</SortableTH>
              <SortableTH col="priority" sort={taskSort} onSort={setTaskSort}>{t('common.priority')}</SortableTH>
            </div>
            <VirtualList
              items={sortedTasks}
              rowHeight={52}
              height={Math.min(flatTasks.length * 52, 600)}
              renderRow={(t: Task) => (
                <div
                  onClick={e => { if (!desdeCasilla(e)) setSelectedTask(t) }}
                  onKeyDown={e => onKeyboardActivate(e, () => setSelectedTask(t))}
                  role="button"
                  tabIndex={0}
                  className={`tsk-list-row${selected.has(t.id) ? ' tsk-list-row--selected' : ''}`}
                >
                  <Checkbox aria-label={t.title} checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} className="tsk-check" />
                  <div>
                    <div className="u-base-600">{t.title}</div>
                    <div className="u-text2-mono-xs">{t.code}</div>
                  </div>
                  <span className="u-text2-sm">
                    {projects.find(p => p.id === t.project_id)?.code || t.project_id?.slice(0,8) || '—'}
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
      )}

      <TaskDetailModal task={selectedTask} open={!!selectedTask} onClose={() => setSelectedTask(null)} />
      <CreateTaskModal open={showCreate} onClose={() => setShowCreate(false)} projects={projects} />
      <SmartScheduleModal
        open={smartScheduleOpen}
        onClose={() => setSmartScheduleOpen(false)}
        projectId={projectFilter || null}
        projectName={projects?.find(p => p.id === projectFilter)?.name}
      />
    </PageShell>
  )
}

function CreateTaskModal({ open, onClose, projects }: { open: boolean; onClose: () => void; projects: ProjectListItem[] }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: users = [] } = useQuery<PersonaVisible[]>({
    // Selector de personas: `/users/directory` sirve a cualquier rol (`/users` da 403 al subcontratado).
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
  })
  const [form, setForm] = useState<NewTaskForm>({
    title: '', project_id: '', status: 'todo', priority: 'medium',
    estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '', supplier_id: '', supplier_work_package_id: '',
  })
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const [semSuggestion, setSemSuggestion] = useState<SemSuggestion | null>(null)
  const [semEffort, setSemEffort] = useState<SemEffort | null>(null)
  const [suggesting, setSuggesting] = useState(false)
  const [pendingSuggestion, setPendingSuggestion] = useState<SemSuggestion | null>(null)
  const [customValues, setCustomValues] = useState<CustomValues>({})

  const { data: customFields = [] } = useQuery<CustomField[]>({
    queryKey: ['custom-fields', form.project_id],
    queryFn: () => customFieldsApi.list(form.project_id).then(r => r.data).catch(() => []),
    enabled: !!form.project_id,
    retry: false,
  })

  const statusOptions = useWorkflowStatusOptions(form.project_id, t)

  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: async ({ taskData, cfValues, cfFields }: { taskData: TaskBody; cfValues: CustomValues; cfFields: CustomField[] }) => {
      const res = await tareas.create(taskData)
      const task = res.data
      if (cfFields.length > 0 && task?.id) {
        const payload = cfFields.map(f => ({ field_id: f.id, value: cfValues[f.id] ?? null }))
        await customFieldsApi.setValues(task.project_id, task.id, payload)
      }
      return task
    },
    onSuccess: newTask => {
      if (pendingSuggestion?.suggested_user_id && newTask?.id) {
        semanticApi.recordAssignment({
          item_type: 'task',
          item_id: newTask.id,
          item_title: newTask.title || '',
          suggested_user_id: pendingSuggestion.suggested_user_id,
          accepted_user_id: pendingSuggestion.suggested_user_id,
          was_accepted: true,
          confidence: pendingSuggestion.confidence,
          needs_review: pendingSuggestion.needs_review,
          engine_mode: pendingSuggestion.engine_mode,
          reasoning: pendingSuggestion.reasoning,
        }).catch(() => { /* non-blocking */ })
      }
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-my-tasks'] })
      qc.invalidateQueries({ queryKey: ['dash-overdue-tasks'] })
      qc.invalidateQueries({ queryKey: ['cal-tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
      onClose()
      setForm({ title: '', project_id: '', status: 'todo', priority: 'medium', estimated_hours: '', start_date: '', due_date: '', description: '', assignee_id: '', supplier_id: '', supplier_work_package_id: '' })
      setCustomValues({})
      setSemSuggestion(null); setSemEffort(null); setPendingSuggestion(null)
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  const set = (k: keyof NewTaskForm) => (e: { target: { value: string } }) => { campos.limpiar(k); setForm(f => ({ ...f, [k]: e.target.value })) }
  // 19-11-2026: persona o proveedor, excluyentes; cambiar de proyecto vacía el proveedor (sus paquetes son del proyecto).
  const asignar = (k: 'assignee_id' | 'supplier_id' | 'supplier_work_package_id', v: string) => {
    campos.limpiar(k)
    setForm(f => asignacionExclusiva(f, k, v))
  }

  const analyzeWithAI = async () => {
    if (!form.title) return
    setSuggesting(true)
    setSemSuggestion(null); setSemEffort(null)
    try {
      const [sugRes, effortRes] = await Promise.all([
        semanticApi.suggestTask({ title: form.title, description: form.description, project_id: form.project_id || undefined }),
        semanticApi.estimateEffort({ title: form.title, description: form.description }),
      ])
      setSemSuggestion(sugRes.data)
      setSemEffort(effortRes.data)
    } catch (e) { setSemSuggestion({ error: (e as ApiError)?.response?.data?.detail || t('common.error') }) }
    finally { setSuggesting(false) }
  }

  const acceptSuggestion = () => {
    if (semSuggestion?.suggested_user_id) {
      setForm(f => asignacionExclusiva(f, 'assignee_id', semSuggestion.suggested_user_id || ''))
      // Store suggestion so we can persist SemAssignment once the task is created (task.id is known)
      setPendingSuggestion({ ...semSuggestion })
    }
    if (semEffort?.base_hours && !form.estimated_hours)
      setForm(f => ({ ...f, estimated_hours: String(semEffort.base_hours) }))
    setSemSuggestion(null); setSemEffort(null)
  }

  return (
    <Modal open={open} onClose={onClose} title={t('tasks.new_task')} width={580}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-1-et`} htmlFor={`${idCampo}-1`} className="tsk-label tsk-label--lg">{t('tasks.title_required')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-1-et`} value={form.title} onChange={set('title')} className="tsk-input tsk-input--lg" placeholder={t('tasks.task_title')} />
          {msg('title')}
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-2-et`} htmlFor={`${idCampo}-2`} className="tsk-label tsk-label--lg">{t('tasks.project_required')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.project_id} onChange={e => { campos.limpiar('project_id'); setForm(f => ({ ...f, project_id: e.target.value, supplier_id: '', supplier_work_package_id: '' })) }} className="tsk-input tsk-input--lg">
            <option value="">{t('tasks.select_project_option')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>
          {msg('project_id')}
        </div>
        <div>
          <label id={`${idCampo}-3-et`} htmlFor={`${idCampo}-3`} className="tsk-label tsk-label--lg">{t('common.status')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.status} onChange={set('status')} className="tsk-input tsk-input--lg">
            {statusOptions.map(o => (
              <option key={o.value} value={o.value}>{o.icon} {o.label}</option>
            ))}
          </Select>
          {msg('status')}
        </div>
        <div>
          <label id={`${idCampo}-4-et`} htmlFor={`${idCampo}-4`} className="tsk-label tsk-label--lg">{t('common.priority')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.priority} onChange={set('priority')} className="tsk-input tsk-input--lg">
            <option value="low">{t('tasks.priority_low')}</option>
            <option value="medium">{t('tasks.priority_medium')}</option>
            <option value="high">{t('tasks.priority_high')}</option>
            <option value="critical">{t('tasks.priority_critical')}</option>
          </Select>
          {msg('priority')}
        </div>
        {/* Asignación + estimación con IA */}
        <div className="u-col-full">
          <div className="tsk-label-row tsk-label-row--lg">
            <label id={`${idCampo}-asignado-et`} htmlFor={`${idCampo}-asignado`} className="tsk-label tsk-label--lg tsk-label--flush">{t('tasks.assignee')}</label>
            <Button size="xs" variant="ghost" icon={<Brain size={13} />} onClick={analyzeWithAI} disabled={!form.title} loading={suggesting}>
              {t('tasks.ai_analyze')}
            </Button>
          </div>
          <Select suelto placeholder={false} id={`${idCampo}-asignado`} value={form.assignee_id} onChange={e => asignar('assignee_id', e.target.value)} className="tsk-input tsk-input--lg">
            <option value="">{t('tasks.no_assignee')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>
          {msg('assignee_id')}
        </div>
        {/* Externalizar a un proveedor de outsourcing (excluyente con el asignado) */}
        <ExternalizarTarea projectId={form.project_id} supplierId={form.supplier_id} paqueteId={form.supplier_work_package_id}
          onChange={asignar} idBase={idCampo} claseEtiqueta="tsk-label tsk-label--lg" claseControl="tsk-input tsk-input--lg" error={msg} />
        {/* Banner de sugerencia IA */}
        {(semSuggestion || semEffort) && !semSuggestion?.error && (
          <div className="tsk-ai tsk-ai--modal" role="status">
            <div className="u-flex1">
              <div className="tsk-ai-title">{t('tasks.ai_analysis')}</div>
              <div className="tsk-ai-items">
                {semSuggestion?.suggested_user_name && (
                  <div>
                    <div className="u-text2-2xs">{t('tasks.ai_person_label')}</div>
                    <div className="tsk-ai-value">
                      {semSuggestion.suggested_user_name}
                      <span className="tsk-ai-note">
                        {Math.round((semSuggestion.confidence||0)*100)}%
                      </span>
                    </div>
                  </div>
                )}
                {semEffort && (
                  <div>
                    <div className="u-text2-2xs">{t('tasks.ai_effort_label')}</div>
                    <div className="tsk-ai-value tsk-ai-value--warning">
                      {fmtNumber(semEffort.base_hours, 1)}h
                      <span className={`tsk-ai-cx tsk-cx--${semEffort.complexity}`}>
                        {nombreDeComplejidad(t, semEffort.complexity)}
                      </span>
                    </div>
                  </div>
                )}
              </div>
              {semSuggestion?.reasoning && <div className="tsk-ai-reason">{semSuggestion.reasoning}</div>}
            </div>
            <div className="u-row-6">
              <Button size="sm" onClick={acceptSuggestion}>{t('tasks.ai_apply')}</Button>
              <IconButton className="tsk-icon-btn" onClick={() => { setSemSuggestion(null); setSemEffort(null) }} ariaLabel={t('tasks.descartar_sugerencia')}><X size={14} aria-hidden /></IconButton>
            </div>
          </div>
        )}
        <div>
          <label id={`${idCampo}-horas-et`} htmlFor={`${idCampo}-horas`} className="tsk-label tsk-label--lg">{t('tasks.estimated_hours')}</label>
          <input id={`${idCampo}-horas`} aria-labelledby={`${idCampo}-horas-et`} type="number" min="0" step="0.5" value={form.estimated_hours} onChange={set('estimated_hours')} className="tsk-input tsk-input--lg" placeholder={t('tasks.estimated_hours')} />
          {msg('estimated_hours')}
        </div>
        <div>
          <label id={`${idCampo}-5-et`} htmlFor={`${idCampo}-5`} className="tsk-label tsk-label--lg">{t('tasks.date_start')}</label>
          <DateInput id={`${idCampo}-5`} aria-labelledby={`${idCampo}-5-et`} value={form.start_date} onChange={set('start_date')} className="tsk-input tsk-input--lg" />
          {msg('start_date')}
        </div>
        <div>
          <label id={`${idCampo}-6-et`} htmlFor={`${idCampo}-6`} className="tsk-label tsk-label--lg">{t('tasks.due_date')}</label>
          <DateInput id={`${idCampo}-6`} aria-labelledby={`${idCampo}-6-et`} value={form.due_date} onChange={set('due_date')} className="tsk-input tsk-input--lg" />
          {msg('due_date')}
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-descripcion-et`} htmlFor={`${idCampo}-descripcion`} className="tsk-label tsk-label--lg">{t('common.description')} <span className="tsk-label-hint">{t('tasks.description_hint')}</span></label>
          <AIInlineEditor inputId={`${idCampo}-descripcion`} value={form.description} onChange={val => set('description')({ target: { value: val } })} rows={3} placeholder={t('common.description')} style={ESTILO_EDITOR_ALTA} />
          {msg('description')}
        </div>
        {/* Campos personalizados del proyecto */}
        {customFields.length > 0 && (
          <div className="tsk-span-full-top">
            <div className="tsk-label tsk-label--lg tsk-label--mb10">{t('tasks.custom_fields_label')}</div>
            <div className="u-grid2-12">
              {customFields.map(f => (
                <div key={f.id} className={(f.field_type === 'text' || f.field_type === 'url') ? 'u-col-full' : undefined}>
                  <label id={`${idCampo}-cf-${f.id}-et`} htmlFor={`${idCampo}-cf-${f.id}`} className="tsk-label tsk-label--lg">{f.name}{f.is_required ? ' *' : ''}</label>
                  {f.field_type === 'select' ? (
                    <Select suelto placeholder={false} id={`${idCampo}-cf-${f.id}`} value={customValues[f.id] ?? ''} onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))} className="tsk-input tsk-input--lg">
                      <option value="">{t('tasks.select_option')}</option>
                      {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                    </Select>
                  ) : f.field_type === 'boolean' ? (
                    <div className="tsk-check-row">
                      <Checkbox id={`${idCampo}-cf-${f.id}`} checked={customValues[f.id] === 'true'} onChange={m => setCustomValues(v => ({ ...v, [f.id]: m ? 'true' : 'false' }))} className="tsk-check tsk-check--lg" />
                      <span className="u-text2-base">{customValues[f.id] === 'true' ? t('common.yes') : t('common.no')}</span>
                    </div>
                  ) : (
                    f.field_type === 'date' ? (
                      <DateInput
                        id={`${idCampo}-cf-${f.id}`} aria-labelledby={`${idCampo}-cf-${f.id}-et`}
                        value={String(customValues[f.id] ?? '')}
                        onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}
                        className="tsk-input tsk-input--lg"
                      />
                    ) : (
                      <input
                        id={`${idCampo}-cf-${f.id}`} aria-labelledby={`${idCampo}-cf-${f.id}-et`}
                        type={f.field_type === 'number' ? 'number' : f.field_type === 'url' ? 'url' : 'text'}
                        value={customValues[f.id] ?? ''}
                        onChange={e => setCustomValues(v => ({ ...v, [f.id]: e.target.value }))}
                        className="tsk-input tsk-input--lg"
                      />
                    )
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="tsk-modal-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate({ taskData: form, cfValues: customValues, cfFields: customFields })} disabled={isPending || !form.title || !form.project_id} loading={isPending}>
            {isPending ? t('tasks.creating') : t('tasks.create_task_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}