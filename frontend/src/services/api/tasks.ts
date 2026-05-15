/**
 * Tasks, task dependencies, issue types, project permissions, custom fields.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

// TODO type: tighten against `app/schemas/task.py`.
export interface TaskCreatePayload extends JsonBody {
  title: string
  project_id: Id
  status?: string
  priority?: string
  assignee_id?: string | null
}

export const tasksApi = {
  list:        (params?: Params): Promise<Response<unknown>> => api.get('/tasks', { params }),
  kanban:      (projectId: Id): Promise<Response<unknown>> => api.get(`/tasks/kanban/${projectId}`),
  get:         (id: Id): Promise<Response<unknown>> => api.get(`/tasks/${id}`),
  create:      (data: TaskCreatePayload): Promise<Response<unknown>> => api.post('/tasks', data),
  update:      (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/tasks/${id}`, data),
  delete:      (id: Id): Promise<Response<unknown>> => api.delete(`/tasks/${id}`),
  comment:     (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/tasks/${id}/comments`, data),
  bulkUpdate:  (data: JsonBody): Promise<Response<unknown>> => api.post('/tasks/bulk-update', data),
  movementLog: (id: Id): Promise<Response<unknown>> => api.get(`/tasks/${id}/movement-log`),
}

export const taskDependenciesApi = {
  getByProject: (projectId: Id): Promise<Response<unknown>> => api.get(`/tasks/dependencies/${projectId}`),
  create:       (data: JsonBody): Promise<Response<unknown>> => api.post('/tasks/dependencies', data),
  delete:       (id: Id): Promise<Response<unknown>> => api.delete(`/tasks/dependencies/${id}`),
  bulkDates:    (updates: unknown[]): Promise<Response<unknown>> => api.post('/tasks/bulk-dates', { updates }),
}

export const issueTypesApi = {
  list:   (projectId: Id): Promise<Response<unknown>> => api.get(`/issue-types/${projectId}`),
  create: (projectId: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/issue-types/${projectId}`, data),
  update: (projectId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/issue-types/${projectId}/${id}`, data),
  init:   (projectId: Id): Promise<Response<unknown>> => api.post(`/issue-types/${projectId}/init`),
  delete: (projectId: Id, id: Id): Promise<Response<unknown>> => api.delete(`/issue-types/${projectId}/${id}`),
}

export const permissionsApi = {
  list:   (projectId: Id): Promise<Response<unknown>> => api.get(`/permissions/${projectId}`),
  create: (projectId: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/permissions/${projectId}`, data),
  update: (projectId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/permissions/${projectId}/${id}`, data),
  delete: (projectId: Id, id: Id): Promise<Response<unknown>> => api.delete(`/permissions/${projectId}/${id}`),
}

export const customFieldsApi = {
  list:      (projectId: Id): Promise<Response<unknown>> => api.get(`/custom-fields/${projectId}`),
  create:    (projectId: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/custom-fields/${projectId}`, data),
  update:    (projectId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/custom-fields/${projectId}/${id}`, data),
  delete:    (projectId: Id, id: Id): Promise<Response<unknown>> => api.delete(`/custom-fields/${projectId}/${id}`),
  getValues: (projectId: Id, taskId: Id): Promise<Response<unknown>> =>
    api.get(`/custom-fields/${projectId}/values/${taskId}`),
  setValues: (projectId: Id, taskId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/custom-fields/${projectId}/values/${taskId}`, data),
}
