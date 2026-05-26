/**
 * services/api/tasks.ts — Audit #C10 typed slice.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'

export type TaskStatus =
  | 'todo'
  | 'in_progress'
  | 'in_review'
  | 'done'
  | 'cancelled'
  | 'blocked'

export interface TaskListItem {
  id: string
  code?: string
  title: string
  description?: string | null
  status: TaskStatus
  priority?: 'p1_critical' | 'p2_high' | 'p3_medium' | 'p4_low' | null
  project_id: string
  project_name?: string | null
  assigned_to?: string | null
  assigned_to_name?: string | null
  due_date?: string | null
  estimated_hours?: number | null
  actual_hours?: number | null
}

export interface TaskListParams {
  project_id?: string
  status?: TaskStatus
  assigned_to?: string
  mine?: boolean
  overdue?: boolean
  page?: number
  page_size?: number
  q?: string
}

export interface TaskCreatePayload {
  title: string
  project_id: string
  description?: string
  status?: TaskStatus
  priority?: string
  assigned_to?: string
  due_date?: string
  estimated_hours?: number
}

export type TaskUpdatePayload = Partial<TaskCreatePayload>

export interface TaskCommentPayload {
  body: string
  mentions?: string[]
}

export interface TaskBulkUpdatePayload {
  ids: string[]
  status?: TaskStatus
  assigned_to?: string | null
  priority?: string
}

export interface KanbanResponse {
  columns: Array<{
    status: TaskStatus
    label: string
    tasks: TaskListItem[]
  }>
}

export interface MovementLogEntry {
  id: string
  from_status?: TaskStatus | null
  to_status: TaskStatus
  actor_id: string
  actor_name?: string
  at: string
}

export const tasksApi = {
  list: (params?: TaskListParams): Promise<AxiosResponse<TaskListItem[]>> =>
    api.get('/tasks', { params }),

  kanban: (projectId: string): Promise<AxiosResponse<KanbanResponse>> =>
    api.get(`/tasks/kanban/${projectId}`),

  get: (id: string): Promise<AxiosResponse<TaskListItem>> =>
    api.get(`/tasks/${id}`),

  create: (data: TaskCreatePayload): Promise<AxiosResponse<TaskListItem>> =>
    api.post('/tasks', data),

  update: (id: string, data: TaskUpdatePayload): Promise<AxiosResponse<TaskListItem>> =>
    api.patch(`/tasks/${id}`, data),

  delete: (id: string): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.delete(`/tasks/${id}`),

  comment: (id: string, data: TaskCommentPayload): Promise<AxiosResponse<unknown>> =>
    api.post(`/tasks/${id}/comments`, data),

  bulkUpdate: (data: TaskBulkUpdatePayload): Promise<AxiosResponse<{ updated: number }>> =>
    api.post('/tasks/bulk-update', data),

  movementLog: (id: string): Promise<AxiosResponse<MovementLogEntry[]>> =>
    api.get(`/tasks/${id}/movement-log`),
} as const
