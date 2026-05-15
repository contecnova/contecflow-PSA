/**
 * Projects, sprints (project-scoped), workflows, change requests, sprint plans, dependencies, portfolios.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

// TODO type: tighten against `app/schemas/project.py`.
export interface ProjectCreatePayload extends JsonBody {
  name: string
  code?: string
  status?: string
  client_id?: string | null
}

export const projectsApi = {
  list:              (params?: Params): Promise<Response<unknown>> => api.get('/projects', { params }),
  get:               (id: Id): Promise<Response<unknown>> => api.get(`/projects/${id}`),
  create:            (data: ProjectCreatePayload): Promise<Response<unknown>> => api.post('/projects', data),
  update:            (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/projects/${id}`, data),
  team:              (id: Id): Promise<Response<unknown>> => api.get(`/projects/${id}/team`),
  addPhase:          (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/projects/${id}/phases`, data),
  members:           (id: Id): Promise<Response<unknown>> => api.get(`/projects/${id}/members`),
  addMember:         (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/projects/${id}/members`, data),
  removeMember:      (id: Id, memberId: Id): Promise<Response<unknown>> => api.delete(`/projects/${id}/members/${memberId}`),
  milestones:        (params?: Params): Promise<Response<unknown>> => api.get('/projects/milestones', { params }),
  changelog:         (id: Id, params?: Params): Promise<Response<unknown>> => api.get(`/projects/${id}/changelog`, { params }),
  createChangelog:   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/projects/${id}/changelog`, data),
  generateChangelog: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/projects/${id}/changelog/generate`, data),
  deleteChangelog:   (id: Id, entryId: Id): Promise<Response<unknown>> => api.delete(`/projects/${id}/changelog/${entryId}`),
  raci:              (id: Id): Promise<Response<unknown>> => api.get(`/projects/${id}/raci`),
  updateRaci:        (id: Id, data: JsonBody): Promise<Response<unknown>> => api.put(`/projects/${id}/raci`, data),
  deleteRaci:        (id: Id, entryId: Id): Promise<Response<unknown>> => api.delete(`/projects/${id}/raci/${entryId}`),
  evm:               (id: Id): Promise<Response<unknown>> => api.get(`/projects/${id}/evm`),
  evmPortfolio:      (): Promise<Response<unknown>> => api.get('/projects/evm/portfolio'),
}

export const projectChangesApi = {
  list:       (projectId: Id): Promise<Response<unknown>> => api.get(`/changes/${projectId}`),
  allPending: (): Promise<Response<unknown>> => api.get('/changes/all/pending'),
  create:     (projectId: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/changes/${projectId}`, data),
  update:     (projectId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/changes/${projectId}/${id}`, data),
  review:     (projectId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/changes/${projectId}/${id}/review`, data),
  submit:     (projectId: Id, id: Id): Promise<Response<unknown>> => api.post(`/changes/${projectId}/${id}/submit`),
  implement:  (projectId: Id, id: Id): Promise<Response<unknown>> => api.post(`/changes/${projectId}/${id}/implement`),
  delete:     (projectId: Id, id: Id): Promise<Response<unknown>> => api.delete(`/changes/${projectId}/${id}`),
}

export const projectWorkflowsApi = {
  get:              (projectId: Id): Promise<Response<unknown>> => api.get(`/project-workflows/${projectId}`),
  init:             (projectId: Id): Promise<Response<unknown>> => api.post(`/project-workflows/${projectId}/init`),
  createState:      (projectId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/project-workflows/${projectId}/states`, data),
  updateState:      (projectId: Id, stateId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/project-workflows/${projectId}/states/${stateId}`, data),
  deleteState:      (projectId: Id, stateId: Id): Promise<Response<unknown>> =>
    api.delete(`/project-workflows/${projectId}/states/${stateId}`),
  createTransition: (projectId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/project-workflows/${projectId}/transitions`, data),
  deleteTransition: (projectId: Id, transId: Id): Promise<Response<unknown>> =>
    api.delete(`/project-workflows/${projectId}/transitions/${transId}`),
  transitionTask:   (projectId: Id, taskId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/project-workflows/${projectId}/tasks/${taskId}/transition`, data),
  resetWorkflow:    (projectId: Id): Promise<Response<unknown>> => api.delete(`/project-workflows/${projectId}/reset`),
}

export const projectSprintsApi = {
  list:        (projectId: Id): Promise<Response<unknown>> => api.get(`/sprints/${projectId}/sprints`),
  create:      (projectId: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/sprints/${projectId}/sprints`, data),
  update:      (projectId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/sprints/${projectId}/sprints/${id}`, data),
  start:       (projectId: Id, id: Id): Promise<Response<unknown>> => api.post(`/sprints/${projectId}/sprints/${id}/start`),
  close:       (projectId: Id, id: Id): Promise<Response<unknown>> => api.post(`/sprints/${projectId}/sprints/${id}/close`),
  burndown:    (projectId: Id, id: Id): Promise<Response<unknown>> => api.get(`/sprints/${projectId}/sprints/${id}/burndown`),
  backlog:     (projectId: Id): Promise<Response<unknown>> => api.get(`/sprints/${projectId}/backlog`),
  velocity:    (projectId: Id): Promise<Response<unknown>> => api.get(`/sprints/${projectId}/velocity`),
  addTasks:    (projectId: Id, sprintId: Id, taskIds: Id[]): Promise<Response<unknown>> =>
    api.post(`/sprints/${projectId}/sprints/${sprintId}/tasks`, { task_ids: taskIds }),
  removeTask:  (projectId: Id, sprintId: Id, taskId: Id): Promise<Response<unknown>> =>
    api.delete(`/sprints/${projectId}/sprints/${sprintId}/tasks/${taskId}`),
  retrospective:     (projectId: Id, sprintId: Id): Promise<Response<unknown>> =>
    api.get(`/projects/${projectId}/sprints/${sprintId}/retrospective`),
  saveRetrospective: (projectId: Id, sprintId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.put(`/projects/${projectId}/sprints/${sprintId}/retrospective`, data),
  burnup:            (projectId: Id, sprintId: Id): Promise<Response<unknown>> =>
    api.get(`/sprints/${projectId}/sprints/${sprintId}/burnup`),
}

export const dependenciesApi = {
  get: (projectId: Id): Promise<Response<unknown>> => api.get(`/dependencies/${projectId}`),
}

export const sprintPlansApi = {
  generate:     (data: JsonBody): Promise<Response<unknown>> => api.post('/cmdb/sprint-plans/generate', data),
  get:          (projectId: Id): Promise<Response<unknown>> => api.get(`/cmdb/sprint-plans/${projectId}`),
  updateStatus: (id: Id, status: string): Promise<Response<unknown>> =>
    api.patch(`/cmdb/sprint-plans/${id}/status?status=${encodeURIComponent(status)}`),
  delete:       (id: Id): Promise<Response<unknown>> => api.delete(`/cmdb/sprint-plans/${id}`),
}

export const portfolioApi = {
  list:          (): Promise<Response<unknown>> => api.get('/portfolios'),
  get:           (id: Id): Promise<Response<unknown>> => api.get(`/portfolios/${id}`),
  dashboard:     (id: Id): Promise<Response<unknown>> => api.get(`/portfolios/${id}/dashboard`),
  create:        (data: JsonBody): Promise<Response<unknown>> => api.post('/portfolios', data),
  update:        (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/portfolios/${id}`, data),
  delete:        (id: Id): Promise<Response<unknown>> => api.delete(`/portfolios/${id}`),
  addProject:    (id: Id, pid: Id): Promise<Response<unknown>> => api.post(`/portfolios/${id}/projects`, { project_id: pid }),
  removeProject: (id: Id, pid: Id): Promise<Response<unknown>> => api.delete(`/portfolios/${id}/projects/${pid}`),
}
