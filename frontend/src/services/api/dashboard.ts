/**
 * Dashboard KPIs + alerts.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const dashboardApi = {
  kpis:             (): Promise<Response<unknown>> => api.get('/dashboard/kpis'),
  projectsHealth:   (params?: Params): Promise<Response<unknown>> => api.get('/dashboard/projects-health', { params }),
  resourceLoad:     (params?: Params): Promise<Response<unknown>> => api.get('/dashboard/resource-load', { params }),
  profitability:    (params?: Params): Promise<Response<unknown>> => api.get('/dashboard/profitability', { params }),
  teamProductivity: (params?: Params): Promise<Response<unknown>> =>
    api.get('/dashboard/productivity/team', { params }),
}

export const alertsApi = {
  list:    (params?: Params): Promise<Response<unknown>> => api.get('/alerts', { params }),
  run:     (): Promise<Response<unknown>> => api.post('/alerts/run'),
  read:    (id: Id): Promise<Response<unknown>> => api.patch(`/alerts/${id}/read`),
  resolve: (id: Id): Promise<Response<unknown>> => api.patch(`/alerts/${id}/resolve`),
}

// AI Copilot — Gantt / timesheet suggestions
export const aiCopilotApi = {
  ganttSuggestions:     (projectId: Id): Promise<Response<unknown>> => api.get(`/ai/suggestions/gantt/${projectId}`),
  timesheetSuggestions: (userId: Id): Promise<Response<unknown>> => api.get(`/ai/suggestions/timesheets/${userId}`),
}

// Imported from api.js so types compile even if unused by callers.
export type { JsonBody, Id, Params, Response }
