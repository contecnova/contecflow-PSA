/**
 * Bookings, resource forecasting, capacity planning, profitability.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const bookingsApi = {
  list:   (params?: Params): Promise<Response<unknown>> => api.get('/bookings', { params }),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/bookings', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/bookings/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/bookings/${id}`),
}

export const resourceForecastApi = {
  weeks: (params?: Params): Promise<Response<unknown>> => api.get('/resource-forecast/weeks', { params }),
}

export const forecastApi = {
  heatmap:      (params?: Params): Promise<Response<unknown>> => api.get('/resource-forecast/weeks', { params }),
  userDetail:   (uid: Id, p?: Params): Promise<Response<unknown>> =>
    api.get(`/resource-forecast/users/${uid}`, { params: p }),
  availability: (params?: Params): Promise<Response<unknown>> => api.get('/resource-forecast/availability', { params }),
  summary:      (params?: Params): Promise<Response<unknown>> => api.get('/resource-forecast/summary', { params }),
}

export const capacityApi = {
  board:      (params?: Params): Promise<Response<unknown>> => api.get('/capacity/board', { params }),
  createPlan: (data: JsonBody): Promise<Response<unknown>> => api.post('/capacity/plans', data),
  updatePlan: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/capacity/plans/${id}`, data),
  deletePlan: (id: Id): Promise<Response<unknown>> => api.delete(`/capacity/plans/${id}`),
}

export const profitabilityApi = {
  get:             (projectId: Id): Promise<Response<unknown>> => api.get(`/profitability/${projectId}`),
  summary:         (params?: Params): Promise<Response<unknown>> => api.get('/profitability/summary', { params }),
  projects:        (params?: Params): Promise<Response<unknown>> => api.get('/profitability/projects', { params }),
  createMilestone: (projectId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/profitability/${projectId}/milestones`, data),
  updateMilestone: (projectId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/profitability/${projectId}/milestones/${id}`, data),
  deleteMilestone: (projectId: Id, id: Id): Promise<Response<unknown>> =>
    api.delete(`/profitability/${projectId}/milestones/${id}`),
}

export const burnoutRiskApi = {
  get:     (params?: Params): Promise<Response<unknown>> => api.get('/resources/burnout-risk', { params }),
  compute: (): Promise<Response<unknown>> => api.post('/resources/burnout-risk/compute'),
}

export const resourcesApi = {
  loadScoring: (params?: Params): Promise<Response<unknown>> => api.get('/resources/load-scoring', { params }),
  teamHealth:  (params?: Params): Promise<Response<unknown>> => api.get('/resources/team-health', { params }),
}
