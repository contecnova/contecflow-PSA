/**
 * Enterprise — SSO, notifications, organizations, GDPR, governance, GRC,
 * developer apps, public forms.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const enterpriseApi = {
  auditLog:                (params?: Params): Promise<Response<unknown>> => api.get('/enterprise/audit-log', { params }),
  ssoList:                 (): Promise<Response<unknown>> => api.get('/enterprise/sso'),
  ssoCreate:               (data: JsonBody): Promise<Response<unknown>> => api.post('/enterprise/sso', data),
  ssoDelete:               (id: Id): Promise<Response<unknown>> => api.delete(`/enterprise/sso/${id}`),
  ssoTest:                 (id: Id): Promise<Response<unknown>> => api.post(`/enterprise/sso/${id}/test`),
  notifications:           (params?: Params): Promise<Response<unknown>> =>
    api.get('/enterprise/notifications', { params }),
  markNotificationRead:    (id: Id): Promise<Response<unknown>> =>
    api.post(`/enterprise/notifications/${id}/read`),
  markAllNotificationsRead:(): Promise<Response<unknown>> => api.post('/enterprise/notifications/read-all'),
  clearOldNotifications:   (params?: Params): Promise<Response<unknown>> =>
    api.delete('/enterprise/notifications/clear-old', { params }),
}

export const organizationsApi = {
  list:       (): Promise<Response<unknown>> => api.get('/organizations'),
  get:        (id: Id): Promise<Response<unknown>> => api.get(`/organizations/${id}`),
  create:     (data: JsonBody): Promise<Response<unknown>> => api.post('/organizations', data),
  update:     (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/organizations/${id}`, data),
  assignUser: (orgId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/organizations/${orgId}/assign-user`, data),
  removeUser: (orgId: Id, userId: Id): Promise<Response<unknown>> =>
    api.delete(`/organizations/${orgId}/remove-user/${userId}`),
}

export const gdprApi = {
  list:    (): Promise<Response<unknown>> => api.get('/gdpr/requests'),
  create:  (data: JsonBody): Promise<Response<unknown>> => api.post('/gdpr/requests', data),
  process: (id: Id): Promise<Response<unknown>> => api.post(`/gdpr/requests/${id}/process`),
}

export const governanceApi = {
  config: (): Promise<Response<unknown>> => api.get('/governance/config'),
  stats:  (): Promise<Response<unknown>> => api.get('/governance/stats'),
  logs:   (): Promise<Response<unknown>> => api.get('/governance/logs?limit=100'),
  update: (module: string, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/governance/config/${module}`, data),
}

export const grcApi = {
  permissions:      (): Promise<Response<unknown>> => api.get('/grc/permissions'),
  seedPermissions:  (): Promise<Response<unknown>> => api.post('/grc/permissions/seed'),
  updatePermission: (role: string, module: string, action: string, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/grc/permissions/${role}/${module}/${action}`, data),
  sodRules:         (): Promise<Response<unknown>> => api.get('/grc/sod-rules'),
  createSodRule:    (data: JsonBody): Promise<Response<unknown>> => api.post('/grc/sod-rules', data),
  updateSodRule:    (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/grc/sod-rules/${id}`, data),
  deleteSodRule:    (id: Id): Promise<Response<unknown>> => api.delete(`/grc/sod-rules/${id}`),
  sodCheck:         (): Promise<Response<unknown>> => api.get('/grc/sod-check'),
  violations:       (params?: Params): Promise<Response<unknown>> => api.get('/grc/violations', { params }),
  resolveViolation: (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/grc/violations/${id}/resolve`, data),
  auditLog:         (params?: Params): Promise<Response<unknown>> => api.get('/grc/audit-log', { params }),
}

export const developerAppsApi = {
  list:         (): Promise<Response<unknown>> => api.get('/developer/apps'),
  create:       (data: JsonBody): Promise<Response<unknown>> => api.post('/developer/apps', data),
  update:       (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/developer/apps/${id}`, data),
  rotateSecret: (id: Id): Promise<Response<unknown>> => api.post(`/developer/apps/${id}/rotate-secret`),
  delete:       (id: Id): Promise<Response<unknown>> => api.delete(`/developer/apps/${id}`),
}

export const formsApi = {
  list:        (): Promise<Response<unknown>> => api.get('/forms'),
  create:      (data: JsonBody): Promise<Response<unknown>> => api.post('/forms', data),
  update:      (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/forms/${id}`, data),
  submissions: (id: Id): Promise<Response<unknown>> => api.get(`/forms/${id}/submissions`),
  delete:      (id: Id): Promise<Response<unknown>> => api.delete(`/forms/${id}`),
}
