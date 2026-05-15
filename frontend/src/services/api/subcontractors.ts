/**
 * Subcontractors (basic + enterprise extended workers/assignments/timelogs/invoices).
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const subcontractorsApi = {
  list:        (params?: Params): Promise<Response<unknown>> => api.get('/subcontractors', { params }),
  get:         (id: Id): Promise<Response<unknown>> => api.get(`/subcontractors/${id}`),
  create:      (data: JsonBody): Promise<Response<unknown>> => api.post('/subcontractors', data),
  update:      (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/subcontractors/${id}`, data),
  delete:      (id: Id): Promise<Response<unknown>> => api.delete(`/subcontractors/${id}`),
  assignments: (id: Id): Promise<Response<unknown>> => api.get(`/subcontractors/${id}/assignments`),
  timelogs:    (id: Id, params?: Params): Promise<Response<unknown>> =>
    api.get(`/subcontractors/${id}/timelogs`, { params }),
  invoices:    (id: Id): Promise<Response<unknown>> => api.get(`/subcontractors/${id}/invoices`),
}

export const enterpriseSubsApi = {
  dashboard:         (): Promise<Response<unknown>> => api.get('/enterprise/subcontractors-dashboard'),
  list:              (): Promise<Response<unknown>> => api.get('/enterprise/subcontractors'),
  create:            (data: JsonBody): Promise<Response<unknown>> => api.post('/enterprise/subcontractors', data),
  update:            (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/enterprise/subcontractors/${id}`, data),
  delete:            (id: Id): Promise<Response<unknown>> => api.delete(`/enterprise/subcontractors/${id}`),
  workers:           (subId: Id): Promise<Response<unknown>> => api.get(`/enterprise/subcontractors/${subId}/workers`),
  createWorker:      (subId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/enterprise/subcontractors/${subId}/workers`, data),
  updateWorker:      (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/enterprise/subcontractors/workers/${id}`, data),
  deleteWorker:      (id: Id): Promise<Response<unknown>> => api.delete(`/enterprise/subcontractors/workers/${id}`),
  addWorkerSkill:    (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/enterprise/subcontractors/workers/${id}/skills`, data),
  removeWorkerSkill: (id: Id, skillId: Id): Promise<Response<unknown>> =>
    api.delete(`/enterprise/subcontractors/workers/${id}/skills/${skillId}`),
  assignments:       (subId: Id): Promise<Response<unknown>> => api.get(`/enterprise/subcontractors/${subId}/assignments`),
  createAssignment:  (subId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/enterprise/subcontractors/${subId}/assignments`, data),
  timelogs:          (subId: Id): Promise<Response<unknown>> => api.get(`/enterprise/subcontractors/${subId}/timelogs`),
  createTimelog:     (subId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/enterprise/subcontractors/${subId}/timelogs`, data),
  invoices:          (subId: Id): Promise<Response<unknown>> => api.get(`/enterprise/subcontractors/${subId}/invoices`),
  createInvoice:     (subId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/enterprise/subcontractors/${subId}/invoices`, data),
  updateInvoice:     (subId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/enterprise/subcontractors/${subId}/invoices/${id}`, data),
}
