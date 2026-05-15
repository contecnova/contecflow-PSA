/**
 * Approvals workflows + groups + UAT.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const approvalsApi = {
  listWorkflows:      (params?: Params): Promise<Response<unknown>> => api.get('/approvals/workflows', { params }),
  listTemplates:      (): Promise<Response<unknown>> => api.get('/approvals/workflow-templates'),
  getWorkflow:        (id: Id): Promise<Response<unknown>> => api.get(`/approvals/workflows/${id}`),
  createWorkflow:     (d: JsonBody): Promise<Response<unknown>> => api.post('/approvals/workflows', d),
  createFromTemplate: (d: JsonBody): Promise<Response<unknown>> =>
    api.post('/approvals/workflows/from-template', d),
  updateWorkflow:     (id: Id, d: JsonBody): Promise<Response<unknown>> => api.patch(`/approvals/workflows/${id}`, d),
  validateWorkflow:   (id: Id): Promise<Response<unknown>> => api.get(`/approvals/workflows/${id}/validate`),
  publishWorkflow:    (id: Id): Promise<Response<unknown>> => api.post(`/approvals/workflows/${id}/publish`),
  cloneVersion:       (id: Id, d?: JsonBody): Promise<Response<unknown>> =>
    api.post(`/approvals/workflows/${id}/clone-version`, d || {}),
  deleteWorkflow:     (id: Id): Promise<Response<unknown>> => api.delete(`/approvals/workflows/${id}`),
  addStep:            (wid: Id, d: JsonBody): Promise<Response<unknown>> =>
    api.post(`/approvals/workflows/${wid}/steps`, d),
  updateStep:         (wid: Id, sid: Id, d: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/approvals/workflows/${wid}/steps/${sid}`, d),
  deleteStep:         (wid: Id, sid: Id): Promise<Response<unknown>> =>
    api.delete(`/approvals/workflows/${wid}/steps/${sid}`),
  simulate:           (d: JsonBody): Promise<Response<unknown>> => api.post('/approvals/simulate', d),
  bottlenecks:        (params?: Params): Promise<Response<unknown>> =>
    api.get('/approvals/analytics/bottlenecks', { params }),
  approverLoad:       (params?: Params): Promise<Response<unknown>> =>
    api.get('/approvals/analytics/approver-load', { params }),
  listRequests:       (params?: Params): Promise<Response<unknown>> => api.get('/approvals/requests', { params }),
  pendingMyAction:    (): Promise<Response<unknown>> => api.get('/approvals/requests/pending-my-action'),
  createRequest:      (d: JsonBody): Promise<Response<unknown>> => api.post('/approvals/requests', d),
  decide:             (id: Id, d: JsonBody): Promise<Response<unknown>> =>
    api.post(`/approvals/requests/${id}/decide`, d),
  cancel:             (id: Id): Promise<Response<unknown>> => api.post(`/approvals/requests/${id}/cancel`),
  stats:              (): Promise<Response<unknown>> => api.get('/approvals/stats'),
  listGroups:         (): Promise<Response<unknown>> => api.get('/approvals/groups'),
  getGroup:           (id: Id): Promise<Response<unknown>> => api.get(`/approvals/groups/${id}`),
  createGroup:        (d: JsonBody): Promise<Response<unknown>> => api.post('/approvals/groups', d),
  updateGroup:        (id: Id, d: JsonBody): Promise<Response<unknown>> => api.patch(`/approvals/groups/${id}`, d),
  deleteGroup:        (id: Id): Promise<Response<unknown>> => api.delete(`/approvals/groups/${id}`),
}

export const uatApi = {
  list:   (projectId: Id, params?: Params): Promise<Response<unknown>> =>
    api.get(`/projects/${projectId}/uat`, { params }),
  create: (projectId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/projects/${projectId}/uat`, data),
  update: (projectId: Id, id: Id, d: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/projects/${projectId}/uat/${id}`, d),
  remove: (projectId: Id, id: Id): Promise<Response<unknown>> =>
    api.delete(`/projects/${projectId}/uat/${id}`),
  export: (projectId: Id): Promise<Response<unknown>> => api.get(`/projects/${projectId}/uat/export`),
}
