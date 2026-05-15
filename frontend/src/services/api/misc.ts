/**
 * Misc — settings (admin), onboarding, search, git, BPMN, wiki, mentions,
 * report-builder, settings-admin, etc.
 *
 * NB: `settingsApi` here is the minimal log-level/general one from the old
 * `api.js`. The richer `settingsApi` lives in `services/settingsApi.ts` and
 * is imported at a different path — both coexist.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const settingsApi = {
  general:     (): Promise<Response<unknown>> => api.get('/settings/general'),
  logLevel:    (): Promise<Response<unknown>> => api.get('/settings/log-level'),
  setLogLevel: (data: JsonBody): Promise<Response<unknown>> => api.post('/settings/log-level', data),
}

export const settingsAdminApi = {
  getLogLevel:    (): Promise<Response<unknown>> => api.get('/settings/log-level'),
  setLogLevel:    (data: JsonBody): Promise<Response<unknown>> => api.post('/settings/log-level', data),
  getOrgDefaults: (): Promise<Response<unknown>> => api.get('/settings/org-defaults'),
}

export const onboardingApi = {
  get:          (): Promise<Response<unknown>> => api.get('/onboarding'),
  completeStep: (data: JsonBody): Promise<Response<unknown>> => api.post('/onboarding/complete-step', data),
  dismiss:      (): Promise<Response<unknown>> => api.post('/onboarding/dismiss'),
}

export const searchApi = {
  search: (params?: Params): Promise<Response<unknown>> => api.get('/global-search', { params }),
}

export const gitApi = {
  pullRequests: (): Promise<Response<unknown>> => api.get('/git/pull-requests'),
  deployments:  (): Promise<Response<unknown>> => api.get('/git/deployments'),
}

export const reportBuilderApi = {
  schema:         (): Promise<Response<unknown>> => api.get('/reports/schema'),
  preview:        (data: JsonBody): Promise<Response<unknown>> => api.post('/reports/preview', data),
  export:         (data: JsonBody, config?: Record<string, unknown>): Promise<Response<unknown>> =>
    api.post('/reports/export', data, config),
  templates:      (): Promise<Response<unknown>> => api.get('/reports/templates'),
  saveTemplate:   (data: JsonBody): Promise<Response<unknown>> => api.post('/reports/templates', data),
  deleteTemplate: (id: Id): Promise<Response<unknown>> => api.delete(`/reports/templates/${id}`),
}

export const wikiApi = {
  spaces:           (): Promise<Response<unknown>> => api.get('epics/wiki/spaces'),
  createSpace:      (data: JsonBody): Promise<Response<unknown>> => api.post('epics/wiki/spaces', data),
  pages:            (spaceId: Id): Promise<Response<unknown>> => api.get(`epics/wiki/spaces/${spaceId}/pages`),
  getPage:          (id: Id): Promise<Response<unknown>> => api.get(`epics/wiki/pages/${id}`),
  createPage:       (spaceId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`epics/wiki/spaces/${spaceId}/pages`, data),
  updatePage:       (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`epics/wiki/pages/${id}`, data),
  deletePage:       (id: Id): Promise<Response<unknown>> => api.delete(`epics/wiki/pages/${id}`),
  versions:         (id: Id): Promise<Response<unknown>> => api.get(`epics/wiki/pages/${id}/versions`),
  restorePage:      (id: Id, vn: number | string): Promise<Response<unknown>> =>
    api.post(`epics/wiki/pages/${id}/restore/${vn}`),
  search:           (q: string, spaceId?: Id): Promise<Response<unknown>> =>
    api.get('epics/wiki/search', { params: { q, space_id: spaceId } }),
  tags:             (space: string): Promise<Response<unknown>> => api.get(`/wiki-tags/${space}`),
  createTag:        (space: string, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/wiki-tags/${space}`, data),
  updateTag:        (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/wiki-tags/${id}`, data),
  deleteTag:        (id: Id): Promise<Response<unknown>> => api.delete(`/wiki-tags/${id}`),
  portalSpaces:     (): Promise<Response<unknown>> => api.get('wiki/spaces'),
  portalPages:      (spaceId: Id): Promise<Response<unknown>> => api.get(`wiki/spaces/${spaceId}/pages`),
  portalUpdatePage: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`wiki/pages/${id}`, data),
}

export const mentionsApi = {
  comments:            (entityType: string, entityId: Id): Promise<Response<unknown>> =>
    api.get('/epics/comments', { params: { entity_type: entityType, entity_id: entityId } }),
  createComment:       (entityType: string, entityId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post('/epics/comments', data, { params: { entity_type: entityType, entity_id: entityId } }),
  resolveComment:      (id: Id): Promise<Response<unknown>> => api.patch(`/epics/comments/${id}/resolve`),
  deleteComment:       (id: Id): Promise<Response<unknown>> => api.delete(`/epics/comments/${id}`),
  mentions:            (onlyUnread?: boolean): Promise<Response<unknown>> =>
    api.get('/activity/mentions/my', { params: { unread_only: onlyUnread } }),
  markMentionRead:     (id: Id): Promise<Response<unknown>> => api.post(`/activity/mentions/${id}/read`),
  markAllMentionsRead: (): Promise<Response<unknown>> => api.post('/epics/mentions/read-all'),
}

export const bpmnProcessesApi = {
  list:        (params?: Params): Promise<Response<unknown>> => api.get('/bpmn-processes', { params }),
  catalogue:   (): Promise<Response<unknown>> => api.get('/bpmn-processes/catalogue'),
  seed:        (force = false): Promise<Response<unknown>> => api.post('/bpmn-processes/seed', { force }),
  get:         (id: Id): Promise<Response<unknown>> => api.get(`/bpmn-processes/${id}`),
  create:      (data: JsonBody): Promise<Response<unknown>> => api.post('/bpmn-processes', data),
  update:      (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/bpmn-processes/${id}`, data),
  delete:      (id: Id): Promise<Response<unknown>> => api.delete(`/bpmn-processes/${id}`),
  duplicate:   (id: Id, name: string): Promise<Response<unknown>> =>
    api.post(`/bpmn-processes/${id}/duplicate`, { new_name: name }),
  saveVersion: (id: Id, xml: string, n?: string): Promise<Response<unknown>> =>
    api.post(`/bpmn-processes/${id}/versions`, { bpmn_xml: xml, notes: n }),
  versions:    (id: Id): Promise<Response<unknown>> => api.get(`/bpmn-processes/${id}/versions`),
  getVersion:  (id: Id, v: number | string): Promise<Response<unknown>> =>
    api.get(`/bpmn-processes/${id}/versions/${v}`),
  publish:     (id: Id, v: number | string): Promise<Response<unknown>> =>
    api.post(`/bpmn-processes/${id}/versions/${v}/publish`),
}
