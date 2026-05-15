/**
 * Documents, document permissions, eSign envelopes.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const documentsApi = {
  list:             (params?: Params): Promise<Response<unknown>> => api.get('/documents', { params }),
  get:              (id: Id): Promise<Response<unknown>> => api.get(`/documents/${id}`),
  upload:           (fd: FormData): Promise<Response<unknown>> => api.post('/documents/upload', fd),
  update:           (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/documents/${id}`, data),
  delete:           (id: Id): Promise<Response<unknown>> => api.delete(`/documents/${id}`),
  approve:          (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/documents/${id}/approve`, data),
  submitApproval:   (id: Id): Promise<Response<unknown>> => api.post(`/documents/${id}/submit-approval`),
  aiSummary:        (id: Id): Promise<Response<unknown>> => api.post(`/documents/${id}/ai-summary`),
  addVersion:       (id: Id, fd: FormData): Promise<Response<unknown>> => api.post(`/documents/${id}/versions`, fd),
  listPermissions:  (id: Id): Promise<Response<unknown>> => api.get(`/documents/${id}/permissions`),
  grantPermission:  (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/documents/${id}/permissions`, data),
  revokePermission: (id: Id, permId: Id): Promise<Response<unknown>> =>
    api.delete(`/documents/${id}/permissions/${permId}`),
  byTask:           (taskId: Id, params?: Params): Promise<Response<unknown>> =>
    api.get(`/documents/by-task/${taskId}`, { params }),
  byTicket:         (ticketId: Id, params?: Params): Promise<Response<unknown>> =>
    api.get(`/documents/by-ticket/${ticketId}`, { params }),
  byProject:        (projectId: Id, params?: Params): Promise<Response<unknown>> =>
    api.get(`/documents/by-project/${projectId}`, { params }),
}

export const esignApi = {
  list:       (): Promise<Response<unknown>> => api.get('/esign'),
  stats:      (): Promise<Response<unknown>> => api.get('/esign/summary/stats'),
  create:     (data: JsonBody): Promise<Response<unknown>> => api.post('/esign', data),
  delete:     (id: Id): Promise<Response<unknown>> => api.delete(`/esign/${id}`),
  sign:       (envelopeId: Id, signerId: Id): Promise<Response<unknown>> =>
    api.patch(`/esign/${envelopeId}/signers/${signerId}/signed`),
  getConfig:  (): Promise<Response<unknown>> => api.get('/esign/config'),
  saveConfig: (data: JsonBody): Promise<Response<unknown>> => api.patch('/esign/config', data),
}
