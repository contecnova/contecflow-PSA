/**
 * Deliverables + SOW milestones.
 */
import { api } from './client'
import type { Id, JsonBody, Response } from './types'

export const deliverablesApi = {
  list:              (projectId: Id): Promise<Response<unknown>> =>
    api.get('/deliverables', { params: { project_id: projectId } }),
  listByProject:     (projectId: Id): Promise<Response<unknown>> => api.get(`/deliverables/${projectId}`),
  overviewAll:       (): Promise<Response<unknown>> => api.get('/deliverables/all/overview'),
  get:               (id: Id): Promise<Response<unknown>> => api.get(`/deliverables/${id}`),
  create:            (data: JsonBody): Promise<Response<unknown>> => api.post('/deliverables', data),
  createForProject:  (projectId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/deliverables/${projectId}`, data),
  update:            (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/deliverables/${id}`, data),
  updateInProject:   (projectId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/deliverables/${projectId}/${id}`, data),
  updateStatus:      (projectId: Id, id: Id, status: string): Promise<Response<unknown>> =>
    api.patch(`/deliverables/${projectId}/${id}`, { status }),
  delete:            (id: Id): Promise<Response<unknown>> => api.delete(`/deliverables/${id}`),
  deleteFromProject: (projectId: Id, id: Id): Promise<Response<unknown>> =>
    api.delete(`/deliverables/${projectId}/${id}`),
  accept:            (projectId: Id, id: Id): Promise<Response<unknown>> =>
    api.post(`/deliverables/${projectId}/${id}/accept`),
  reject:            (projectId: Id, id: Id, reason?: string): Promise<Response<unknown>> =>
    api.post(`/deliverables/${projectId}/${id}/reject`, {}, { params: { reason } }),
  overview:          (): Promise<Response<unknown>> => api.get('/deliverables/overview'),
}

export const milestonesApi = {
  list:            (projectId: Id): Promise<Response<unknown>> => api.get(`/milestones/project/${projectId}`),
  create:          (pid: Id, d: JsonBody): Promise<Response<unknown>> => api.post(`/milestones/project/${pid}`, d),
  update:          (id: Id, d: JsonBody): Promise<Response<unknown>> => api.patch(`/milestones/${id}`, d),
  delete:          (id: Id): Promise<Response<unknown>> => api.delete(`/milestones/${id}`),
  complete:        (id: Id): Promise<Response<unknown>> => api.post(`/milestones/${id}/complete`),
  uncomplete:      (id: Id): Promise<Response<unknown>> => api.post(`/milestones/${id}/uncomplete`),
  requestApproval: (id: Id, d?: JsonBody): Promise<Response<unknown>> =>
    api.post(`/milestones/${id}/request-approval`, d || {}),
  approve:         (id: Id, d: JsonBody): Promise<Response<unknown>> => api.post(`/milestones/${id}/approve`, d),
  generateInvoice: (id: Id): Promise<Response<unknown>> => api.post(`/milestones/${id}/generate-invoice`),
  dashboard:       (): Promise<Response<unknown>> => api.get('/milestones/dashboard/pending'),
}
