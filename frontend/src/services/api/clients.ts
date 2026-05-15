/**
 * Clients, client extensions, client portal, portal conversations.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

// TODO type: tighten against `app/schemas/client.py`.
export interface ClientCreatePayload extends JsonBody {
  name: string
  email?: string
  tax_id?: string
}

export const clientsApi = {
  list:          (params?: Params): Promise<Response<unknown>> => api.get('/clients', { params }),
  get:           (id: Id): Promise<Response<unknown>> => api.get(`/clients/${id}`),
  create:        (data: ClientCreatePayload): Promise<Response<unknown>> => api.post('/clients', data),
  update:        (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/clients/${id}`, data),
  delete:        (id: Id): Promise<Response<unknown>> => api.delete(`/clients/${id}`),
  contacts:      (id: Id): Promise<Response<unknown>> => api.get(`/clients/${id}/contacts`),
  addContact:    (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/clients/${id}/contacts`, data),
  deleteContact: (id: Id, cid: Id): Promise<Response<unknown>> => api.delete(`/clients/${id}/contacts/${cid}`),
  view360:       (id: Id): Promise<Response<unknown>> => api.get(`/clients/${id}/360`),
}

export const clientExtApi = {
  projects:           (cid: Id): Promise<Response<unknown>> => api.get(`/clients/${cid}/projects`),
  availableProjects:  (cid: Id): Promise<Response<unknown>> => api.get(`/clients/${cid}/projects/available`),
  linkProject:        (cid: Id, pid: Id): Promise<Response<unknown>> => api.post(`/clients/${cid}/projects/${pid}/link`),
  unlinkProject:      (cid: Id, pid: Id): Promise<Response<unknown>> => api.delete(`/clients/${cid}/projects/${pid}/link`),
  contacts:           (cid: Id): Promise<Response<unknown>> => api.get(`/clients/${cid}/contacts`),
  createContact:      (cid: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/clients/${cid}/contacts`, data),
  deleteContact:      (cid: Id, id: Id): Promise<Response<unknown>> => api.delete(`/clients/${cid}/contacts/${id}`),
  licenses:           (cid: Id): Promise<Response<unknown>> => api.get(`/clients/${cid}/licenses`),
  linkLicense:        (cid: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/clients/${cid}/licenses`, data),
  unlinkLicense:      (cid: Id, id: Id): Promise<Response<unknown>> => api.delete(`/clients/${cid}/licenses/${id}`),
  contracts:          (cid: Id): Promise<Response<unknown>> => api.get(`/clients/${cid}/contracts`),
  linkContract:       (cid: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/clients/${cid}/contracts`, data),
  unlinkContract:     (cid: Id, id: Id): Promise<Response<unknown>> => api.delete(`/clients/${cid}/contracts/${id}`),
  portalConfig:       (cid: Id): Promise<Response<unknown>> => api.get(`/clients/${cid}/portal-config`),
  updatePortalConfig: (cid: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/clients/${cid}/portal-config`, data),
}

export const portalClientsApi = {
  list:             (params?: Params): Promise<Response<unknown>> => api.get('/portal/clients', { params }),
  create:           (data: JsonBody): Promise<Response<unknown>> => api.post('/portal/clients', data),
  update:           (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/portal/clients/${id}`, data),
  translations:     (): Promise<Response<unknown>> => api.get('/portal/translations'),
  saveTranslations: (data: JsonBody): Promise<Response<unknown>> => api.post('/portal/translations', data),
}

export const portalApi = {
  clients:               (params?: Params): Promise<Response<unknown>> => api.get('/portal/clients', { params }),
  createClient:          (data: JsonBody): Promise<Response<unknown>> => api.post('/portal/clients', data),
  updateClient:          (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/portal/clients/${id}`, data),
  deleteClient:          (id: Id): Promise<Response<unknown>> => api.delete(`/portal/clients/${id}`),
  uat:                   (params?: Params): Promise<Response<unknown>> => api.get('/portal/uat/team', { params }),
  createUat:             (projectId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/portal/uat/${projectId}`, data),
  addTestCase:           (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/portal/uat/${id}/test-cases`, data),
  updateUatStatus:       (id: Id, params?: Params): Promise<Response<unknown>> =>
    api.patch(`/portal/uat/issues/${id}`, null, { params }),
  featureRequests:       (params?: Params): Promise<Response<unknown>> =>
    api.get('/portal/feature-requests/team', { params }),
  respondFeatureRequest: (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/portal/feature-requests/${id}/respond`, data),
  documents:             (params?: Params): Promise<Response<unknown>> =>
    api.get('/portal/documents/team', { params }),
  createDocument:        (projectId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post('/portal/documents', data, { params: { project_id: projectId } }),
  stats:                 (projectId: Id): Promise<Response<unknown>> => api.get(`/portal/stats/${projectId}`),
  translations:          (): Promise<Response<unknown>> => api.get('/portal/translations'),
  saveTranslations:      (data: JsonBody): Promise<Response<unknown>> => api.post('/portal/translations', data),
}

export const portalConversationsApi = {
  getPolicies:   (): Promise<Response<unknown>> => api.get('/portal/conversations/team/policies'),
  updatePolicy:  (topicType: string, data: JsonBody): Promise<Response<unknown>> =>
    api.put(`/portal/conversations/team/policies/${topicType}`, data),
  reviewMessage: (convId: Id, msgId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/portal/conversations/team/${convId}/messages/${msgId}/review`, data),
}
