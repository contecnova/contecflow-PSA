/**
 * Global sprints, epics, epic dependencies.
 * (Project-scoped sprints live in projects.ts as projectSprintsApi.)
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const sprintsApi = {
  list:     (projectId: Id, params?: Params): Promise<Response<unknown>> =>
    api.get('/sprints', { params: { project_id: projectId, ...(params || {}) } }),
  get:      (id: Id): Promise<Response<unknown>> => api.get(`/sprints/${id}`),
  create:   (data: JsonBody): Promise<Response<unknown>> => api.post('/sprints', data),
  update:   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sprints/${id}`, data),
  delete:   (id: Id): Promise<Response<unknown>> => api.delete(`/sprints/${id}`),
  start:    (id: Id): Promise<Response<unknown>> => api.post(`/sprints/${id}/start`),
  complete: (id: Id): Promise<Response<unknown>> => api.post(`/sprints/${id}/complete`),
  burndown: (id: Id): Promise<Response<unknown>> => api.get(`/sprints/${id}/burndown`),
  velocity: (projectId: Id): Promise<Response<unknown>> => api.get(`/sprints/velocity/${projectId}`),
}

export const epicsApi = {
  list:             (projectId: Id): Promise<Response<unknown>> => api.get('/epics', { params: { project_id: projectId } }),
  get:              (id: Id): Promise<Response<unknown>> => api.get(`/epics/${id}`),
  create:           (data: JsonBody): Promise<Response<unknown>> => api.post('/epics', data),
  createForProject: (projectId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post('/epics', data, { params: { project_id: projectId } }),
  update:           (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/epics/${id}`, data),
  delete:           (id: Id): Promise<Response<unknown>> => api.delete(`/epics/${id}`),
  roadmap:          (projectId: Id): Promise<Response<unknown>> => api.get('/roadmap', { params: { project_id: projectId } }),
  roadmapByProject: (projectId: Id): Promise<Response<unknown>> =>
    api.get('/epics/roadmap', { params: { project_id: projectId } }),
  cfd:              (params?: Params): Promise<Response<unknown>> => api.get('/epics/cfd', { params }),
  cfdSnapshot:      (projectId: Id): Promise<Response<unknown>> =>
    api.post('/epics/cfd/snapshot', null, { params: { project_id: projectId } }),
  nqlSearch:        (data: JsonBody): Promise<Response<unknown>> => api.post('/epics/nql/search', data),
}

export const epicDependenciesApi = {
  get:    (projectId: Id): Promise<Response<unknown>> => api.get(`/epic-dependencies/${projectId}`),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/epic-dependencies', data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/epic-dependencies/${id}`),
}
