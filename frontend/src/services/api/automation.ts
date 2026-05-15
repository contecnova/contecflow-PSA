/**
 * Automations + auto-workflows + legacy workflows + scheduled reports.
 */
import { api } from './client'
import type { Id, JsonBody, Response } from './types'

export const automationsApi = {
  list:       (): Promise<Response<unknown>> => api.get('/automations'),
  templates:  (): Promise<Response<unknown>> => api.get('/automations/templates/list'),
  create:     (data: JsonBody): Promise<Response<unknown>> => api.post('/automations', data),
  update:     (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/automations/${id}`, data),
  delete:     (id: Id): Promise<Response<unknown>> => api.delete(`/automations/${id}`),
  test:       (id: Id): Promise<Response<unknown>> => api.post(`/automations/${id}/test`),
  executions: (id: Id): Promise<Response<unknown>> => api.get(`/automations/${id}/executions`),
}

export const autoWorkflowsApi = {
  list:   (): Promise<Response<unknown>> => api.get('/automation-workflows'),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/automation-workflows/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/automation-workflows/${id}`),
}

export const workflowsLegacyApi = {
  list:   (): Promise<Response<unknown>> => api.get('/workflows'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/workflows', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/workflows/${id}`, data),
}

export const scheduledReportsApi = {
  list:   (): Promise<Response<unknown>> => api.get('/scheduled-reports'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/scheduled-reports', data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/scheduled-reports/${id}`),
  run:    (id: Id): Promise<Response<unknown>> => api.post(`/scheduled-reports/${id}/run`),
  toggle: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/scheduled-reports/${id}`, data),
}
