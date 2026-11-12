/**
 * services/api/tasks.ts — Audit #C10 typed slice.
 *
 * Auditoría 2026-11 (#25): los tipos siguen a app/schemas/tasks.py y al endpoint
 * app/api/v1/endpoints/tasks.py. Antes describían otro contrato (comentario con
 * `body`, cambio masivo con `ids`, prioridades `p1_critical`...) y las pantallas
 * los esquivaban con `as unknown as`.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'
import { todasLasPaginas } from './todasLasPaginas'
import type { UserPublic } from './users'

/** `TaskStatus` (app/schemas/common_enums.py). */
export type TaskStatus =
  | 'backlog'
  | 'todo'
  | 'in_progress'
  | 'blocked'
  | 'in_review'
  | 'done'
  | 'cancelled'

/** `TaskPriority` (app/schemas/common_enums.py). */
export type TaskPriority = 'critical' | 'high' | 'medium' | 'low'

/** `TaskCommentOut` (app/schemas/tasks.py). */
export interface TaskComment {
  id: string
  task_id: string
  author: UserPublic | null
  content: string
  created_at: string
}

/** `TaskOut` (app/schemas/tasks.py): lo que devuelven listado, detalle, alta y edición. */
export interface TaskListItem {
  id: string
  code: string
  title: string
  description: string | null
  project_id: string
  phase_id: string | null
  parent_task_id: string | null
  assignee_id: string | null
  status: TaskStatus
  priority: TaskPriority
  estimated_hours: number | null
  story_points: number | null
  start_date: string | null
  due_date: string | null
  issue_type: string | null
  assignee: UserPublic | null
  reporter: UserPublic | null
  real_hours: number
  efficiency_ratio: number | null
  jira_issue_key: string | null
  blocked_reason: string | null
  comments: TaskComment[]
  created_at: string
  updated_at: string | null
}

/** Filtros de `GET /tasks` (list_tasks en app/api/v1/endpoints/tasks.py). */
export interface TaskListParams {
  project_id?: string
  phase_id?: string
  assignee_id?: string
  /** Un estado o varios separados por comas («in_progress,todo»). */
  status?: string
  priority?: TaskPriority
  search?: string
  overdue_only?: boolean
  assigned_to_me?: boolean
  due_date_from?: string
  due_date_to?: string
  sprint_id?: string
  /** Alias viejo de `page_size`. */
  limit?: number
  page?: number
  page_size?: number
}

/** `TaskCreate` (app/schemas/tasks.py). */
export interface TaskCreatePayload {
  title: string
  project_id: string
  description?: string | null
  phase_id?: string | null
  parent_task_id?: string | null
  assignee_id?: string | null
  status?: TaskStatus
  priority?: TaskPriority
  estimated_hours?: number | null
  story_points?: number | null
  start_date?: string | null
  due_date?: string | null
  issue_type?: string | null
}

/** `TaskUpdate` (app/schemas/tasks.py). No admite `project_id`. */
export interface TaskUpdatePayload {
  title?: string | null
  description?: string | null
  phase_id?: string | null
  assignee_id?: string | null
  status?: TaskStatus | null
  priority?: TaskPriority | null
  estimated_hours?: number | null
  start_date?: string | null
  due_date?: string | null
  blocked_reason?: string | null
  tags?: string | null
  issue_type?: string | null
  move_reason?: string | null
}

/** `TaskCommentCreate` (app/schemas/tasks.py). */
export interface TaskCommentPayload {
  content: string
}

/** `BulkTaskUpdatePayload` (app/schemas/tasks.py). */
export interface TaskBulkUpdatePayload {
  task_ids: string[]
  status?: TaskStatus | null
  assignee_id?: string | null
  priority?: TaskPriority | null
}

/** Lo que devuelve `bulk_update_tasks` (app/services/tasks/bulk.py). */
export interface TaskBulkUpdateResult {
  updated: number
  skipped: Array<{ id: string; reason: string }>
}

/** `get_kanban_payload` (app/services/task_service.py): una lista por estado, sin `cancelled`. */
export type KanbanResponse = Record<Exclude<TaskStatus, 'cancelled'>, TaskListItem[]>

/** Lo que devuelve `GET /tasks/{id}/movement-log` (`TaskMovementLogOut`). Revisión 2026-11:
 *  el tipo decía `actor_name`/`at`, campos que el servidor no manda. */
export interface MovementLogEntry {
  id: string
  task_id: string
  project_id: string
  from_status?: TaskStatus | null
  to_status: TaskStatus
  reason?: string | null
  moved_at: string
  moved_by?: UserPublic | null
}

export const tasksApi = {
  list: (params?: TaskListParams): Promise<AxiosResponse<TaskListItem[]>> =>
    // Auditoría 2026-11: sin `page`, todas las páginas (antes, solo las 50 primeras).
    todasLasPaginas('/tasks', params as Record<string, unknown> | undefined),

  kanban: (projectId: string): Promise<AxiosResponse<KanbanResponse>> =>
    api.get(`/tasks/kanban/${projectId}`),

  get: (id: string): Promise<AxiosResponse<TaskListItem>> =>
    api.get(`/tasks/${id}`),

  create: (data: TaskCreatePayload): Promise<AxiosResponse<TaskListItem>> =>
    api.post('/tasks', data),

  update: (id: string, data: TaskUpdatePayload): Promise<AxiosResponse<TaskListItem>> =>
    api.patch(`/tasks/${id}`, data),

  delete: (id: string): Promise<AxiosResponse<unknown>> =>
    api.delete(`/tasks/${id}`),

  comment: (id: string, data: TaskCommentPayload): Promise<AxiosResponse<TaskComment>> =>
    api.post(`/tasks/${id}/comments`, data),

  bulkUpdate: (data: TaskBulkUpdatePayload): Promise<AxiosResponse<TaskBulkUpdateResult>> =>
    api.post('/tasks/bulk-update', data),

  movementLog: (id: string): Promise<AxiosResponse<MovementLogEntry[]>> =>
    api.get(`/tasks/${id}/movement-log`),
} as const
