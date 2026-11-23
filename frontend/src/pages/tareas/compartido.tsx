/**
 * Tipos, constantes y utilidades compartidas de la página de tareas.
 * Troceado de TasksPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import type { CSSProperties, ReactNode } from 'react'
import {
  tasksApi,
  type TaskCreatePayload,
  type TaskUpdatePayload,
  type TaskBulkUpdatePayload,
  type TaskListParams,
} from '../../services/api'
import type {
  CampoPersonalizado,
  ConfigDelTablero,
  EstimacionDeEsfuerzo,
  SugerenciaDeAsignacion,
  TipoDeIncidencia,
  ValorDeCampoPersonalizado,
} from '../../services/api/tipos-rendimiento'
import { CalendarRange, GanttChartSquare, Table2, Users } from 'lucide-react'
import { etiquetaDeEstado } from '../../constants/catalogos'
import { useAppT } from '../../i18n/AppLangContext'

export type Traductor = ReturnType<typeof useAppT>

/** `UserPublic` (app/schemas/users.py): la persona que el servidor anida en tareas y comentarios. */
type PersonaRef = { id: string; full_name: string; email?: string; avatar_url?: string | null }

/** `TaskCommentOut` (app/schemas/tasks.py). */
type TaskComment = { id: string; task_id: string; author?: PersonaRef | null; content: string; created_at: string }

/** `TaskOut` (app/schemas/tasks.py). `tags` y `completed_at` los lee la pantalla aunque el esquema no los declare. */
export type Task = {
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
export type TaskForm = {
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
export type NewTaskForm = {
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
export type CustomField = CampoPersonalizado

export type CustomFieldValue = ValorDeCampoPersonalizado

export type CustomValues = Record<string, string | number>

export type StatusOption = { value: string; icon: string; label: string }

export type IssueType = TipoDeIncidencia

/** Respuesta de `/semantic/suggest/task` (o el error que se guarda en su lugar). */
export type SemSuggestion = Partial<SugerenciaDeAsignacion> & { error?: string }

export type SemEffort = EstimacionDeEsfuerzo

export type Sprint = { id: string; name?: string }

export type KanbanConfig = ConfigDelTablero

export type DragStartHandler = (e: React.MouseEvent, task: Task, onStarted: () => void) => void

// Tipos de la pantalla para lo que manda: los estados y prioridades salen de la URL y de
// los <select> como `string` (el servidor los valida contra sus enums), así que la
// adaptación al slice (`services/api/tasks.ts`, que sigue a app/schemas/tasks.py) es un
// `as` acotado en un único sitio (`tareas`). Auditoría 2026-11 (#25): el formulario guarda
// '' en horas, fechas y asignado vacíos, y el servidor responde 422 a un '' en un número,
// una fecha o un id. `tareas` los limpia: al crear los omite y al editar los manda como
// null (así se puede borrar el valor).
export type TaskBody = Partial<Omit<TaskForm, 'issue_type'>> & { issue_type?: string | null; project_id?: string; move_reason?: string }

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

export type BulkBody = { task_ids: string[]; status?: string; assignee_id?: string; priority?: string }

export type BulkResult = { updated?: number; skipped?: unknown[] }

export const tareas = {
  list:       (q: TaskListQuery) => tasksApi.list(q as TaskListParams),
  create:     (body: TaskBody) => tasksApi.create(limpiarVacios(body, 'omitir') as unknown as TaskCreatePayload),
  update:     (id: string, body: TaskBody) => tasksApi.update(id, limpiarVacios(body, 'anular') as TaskUpdatePayload),
  comment:    (id: string, content: string) => tasksApi.comment(id, { content }),
  bulkUpdate: (body: BulkBody) => tasksApi.bulkUpdate(body as TaskBulkUpdatePayload),
}

// Revisión 2026-11: las cabeceras del tablero salían en castellano con la interfaz en
// otro idioma (tabla fija de helpers.ts, borrada el 19-11-2026); estas son las claves de i18n.
export const CLAVE_DE_ESTADO: Record<string, string> = {
  backlog: 'tasks.status_backlog', todo: 'tasks.status_todo', in_progress: 'tasks.status_in_progress',
  in_review: 'tasks.status_review', blocked: 'tasks.status_blocked', done: 'tasks.status_done', cancelled: 'tasks.status_cancelled',
}

// AIInlineEditor y Tabs solo aceptan `style` (pintan su propio estilo en linea).
const ESTILO_EDITOR: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box', resize: 'vertical' }

export const ESTILO_EDITOR_DETALLE: CSSProperties = { ...ESTILO_EDITOR, padding: '9px 13px', lineHeight: 1.6 }

export const ESTILO_EDITOR_ALTA: CSSProperties = { ...ESTILO_EDITOR, padding: '10px 14px' }

/** Icono de cada vista de trabajo del planificador en la barra de pestañas. */
export const ICONO_DE_VISTA: Record<string, ReactNode> = {
  table: <Table2 size={14} />, timeline: <GanttChartSquare size={14} />,
  calendar: <CalendarRange size={14} />, workload: <Users size={14} />,
}

/** Pulsación dentro de la casilla de selección de una fila: no abre la tarea. */
export const desdeCasilla = (event: { target: EventTarget }) => !!(event.target as HTMLElement).closest?.('.ui-casilla')

export function onKeyboardActivate(event: React.KeyboardEvent, action: () => void) {
  if (desdeCasilla(event)) return
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

// 19-11-2026: las columnas salen del catálogo de estados de tarea de la empresa
// (`useCatalogo('task-statuses')`); `COLUMNAS_DE_TABLERO` es el respaldo.
/** «Abiertas»: lo que el servidor entiende por el filtro rápido de estado (todo menos hecho). */
export const ESTADOS_ABIERTOS = 'backlog,todo,in_progress,blocked,in_review'

// Tope de tareas que se piden (el máximo del endpoint); si hay más, se avisa.
export const TAREAS_MAXIMAS = 500

export const PRIORIDADES = ['critical', 'high', 'medium', 'low']

const CLAVE_DE_PRIORIDAD: Record<string, string> = {
  critical: 'tasks.priority_critical', high: 'tasks.priority_high', medium: 'tasks.priority_medium', low: 'tasks.priority_low',
}

/** Nombre del estado en el idioma activo (el del flujo del proyecto si no es uno de los conocidos). */
export const nombreDeEstado = (t: Traductor, status: string) => CLAVE_DE_ESTADO[status] ? t(CLAVE_DE_ESTADO[status]) : etiquetaDeEstado(t as never, status)

export const nombreDePrioridadT = (t: Traductor, p?: string | null) => (p && CLAVE_DE_PRIORIDAD[p]) ? t(CLAVE_DE_PRIORIDAD[p]) : (p || '')

/** Complejidad que devuelve /semantic/estimate (simple | medium | complex). */
const COMPLEJIDADES = ['simple', 'medium', 'complex']

export const nombreDeComplejidad = (t: Traductor, c?: string | null) => c && COMPLEJIDADES.includes(c) ? t(`tasks.complejidad_${c}`) : (c || '')
