/**
 * Service Desk — tickets, problems, changes, dynamic forms, metrics, catalog,
 * SLA policies, groups, templates, canned responses, announcements, routing,
 * KB, workflow designer, major incidents, SLA schedules, auto-resolution,
 * alert clusters, change rollout, CAB, voice agent, incident-assignment ML.
 */
import { api } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const ticketsApi = {
  list:                    (params?: Params): Promise<Response<unknown>> => api.get('/sd/tickets', { params }),
  myQueue:                 (): Promise<Response<unknown>> => api.get('/sd/tickets/my-queue'),
  get:                     (id: Id): Promise<Response<unknown>> => api.get(`/sd/tickets/${id}`),
  create:                  (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/tickets', data),
  update:                  (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/tickets/${id}`, data),
  close:                   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/sd/tickets/${id}/close`, data),
  comment:                 (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/sd/tickets/${id}/comments`, data),
  aiSuggest:               (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/tickets/${id}/ai-suggest`, data),
  split:                   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/sd/tickets/${id}/split`, data),
  links:                   (id: Id): Promise<Response<unknown>> => api.get(`/sd/tickets/${id}/links`),
  addLink:                 (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/sd/tickets/${id}/links`, data),
  timelog:                 (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/tickets/${id}/time-log`, data),
  restorePending:          (id: Id): Promise<Response<unknown>> => api.post(`/sd/tickets/${id}/restore-pending`, {}),
  escalate:                (id: Id, level = 'l2'): Promise<Response<unknown>> =>
    api.post(`/sd/tickets/${id}/escalate?to_level=${level}`, {}),
  slaPause:                (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/sd/tickets/${id}/sla/pause`, data),
  slaResume:               (id: Id): Promise<Response<unknown>> => api.post(`/sd/tickets/${id}/sla/resume`),
  internalComments:        (id: Id): Promise<Response<unknown>> => api.get(`/sd/tickets/${id}/internal-comments`),
  createInternalComment:   (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/tickets/${id}/internal-comments`, data),
  updateInternalComment:   (id: Id, cid: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/sd/tickets/${id}/internal-comments/${cid}`, data),
  deleteInternalComment:   (id: Id, cid: Id): Promise<Response<unknown>> =>
    api.delete(`/sd/tickets/${id}/internal-comments/${cid}`),
  recommendAssignment:     (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/tickets/${id}/recommend-assignment`, data),
  autoResolutionFeedback:  (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/tickets/${id}/auto-resolution/feedback`, data),
}

export const problemsApi = {
  list:               (params?: Params): Promise<Response<unknown>> => api.get('/sd/problems', { params }),
  get:                (id: Id): Promise<Response<unknown>> => api.get(`/sd/problems/${id}`),
  create:             (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/problems', data),
  update:             (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/problems/${id}`, data),
  delete:             (id: Id): Promise<Response<unknown>> => api.delete(`/sd/problems/${id}`),
  promoteKnownError:  (id: Id): Promise<Response<unknown>> => api.post(`/sd/problems/${id}/promote-known-error`),
  rcaWizardGet:       (id: Id): Promise<Response<unknown>> => api.get(`/sd/problems/${id}/rca-wizard`),
  rcaWizardStart:     (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/problems/${id}/rca-wizard/start`, data),
  rcaWizardStep:      (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/problems/${id}/rca-wizard/step`, data),
  rcaWizardComplete:  (id: Id): Promise<Response<unknown>> => api.post(`/sd/problems/${id}/rca-wizard/complete`),
  rcaWizardAiAssist:  (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/problems/${id}/rca-wizard/ai-assist`, data),
}

export const changesApi = {
  list:    (params?: Params): Promise<Response<unknown>> => api.get('/sd/changes', { params }),
  get:     (id: Id): Promise<Response<unknown>> => api.get(`/sd/changes/${id}`),
  create:  (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/changes', data),
  update:  (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/changes/${id}`, data),
  delete:  (id: Id): Promise<Response<unknown>> => api.delete(`/sd/changes/${id}`),
  approve: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/sd/changes/${id}/approve`, data),
}

export const sdDynamicFormsApi = {
  get:            (): Promise<Response<unknown>> => api.get('/sd/dynamic-forms'),
  save:           (data: JsonBody): Promise<Response<unknown>> => api.put('/sd/dynamic-forms', data),
  history:        (): Promise<Response<unknown>> => api.get('/sd/dynamic-forms/history'),
  diff:           (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/dynamic-forms/diff', data),
  contextOptions: (params?: Params): Promise<Response<unknown>> => api.get('/sd/dynamic-forms/context-options', { params }),
  rollback:       (snapshot_id: Id): Promise<Response<unknown>> =>
    api.post('/sd/dynamic-forms/rollback', { snapshot_id }),
  importPreview:  (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/dynamic-forms/import/preview', data),
  importApply:    (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/dynamic-forms/import/apply', data),
}

export const sdMetricsApi = {
  itil:             (params?: Params): Promise<Response<unknown>> => api.get('/sd/metrics/itil', { params }),
  agentPerformance: (params?: Params): Promise<Response<unknown>> => api.get('/sd/metrics/agent-performance', { params }),
}

export const sdCatalogApi = {
  list:           (): Promise<Response<unknown>> => api.get('/sd/catalog'),
  get:            (): Promise<Response<unknown>> => api.get('/sd/catalog'),
  createCategory: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/catalog/categories', data),
  updateCategory: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/catalog/categories/${id}`, data),
  deleteCategory: (id: Id): Promise<Response<unknown>> => api.delete(`/sd/catalog/categories/${id}`),
  createService:  (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/catalog/services', data),
  updateService:  (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/catalog/services/${id}`, data),
  deleteService:  (id: Id): Promise<Response<unknown>> => api.delete(`/sd/catalog/services/${id}`),
}

export const sdSlaPoliciesApi = {
  list:   (): Promise<Response<unknown>> => api.get('/sd/sla-policies'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/sla-policies', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/sla-policies/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/sd/sla-policies/${id}`),
}

export const sdGroupsApi = {
  list:         (): Promise<Response<unknown>> => api.get('/sd/groups'),
  create:       (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/groups', data),
  update:       (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/groups/${id}`, data),
  delete:       (id: Id): Promise<Response<unknown>> => api.delete(`/sd/groups/${id}`),
  addMember:    (gid: Id, uid: Id): Promise<Response<unknown>> => api.post(`/sd/groups/${gid}/members/${uid}`),
  removeMember: (gid: Id, uid: Id): Promise<Response<unknown>> => api.delete(`/sd/groups/${gid}/members/${uid}`),
}

export const sdTemplatesApi = {
  list:   (): Promise<Response<unknown>> => api.get('/sd/ticket-templates'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/ticket-templates', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/ticket-templates/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/sd/ticket-templates/${id}`),
}

export const sdCannedApi = {
  list:   (params?: Params): Promise<Response<unknown>> => api.get('/sd/canned-responses', { params }),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/canned-responses', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/canned-responses/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/sd/canned-responses/${id}`),
}

export const sdAnnouncementsApi = {
  list:   (): Promise<Response<unknown>> => api.get('/sd/announcements'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/announcements', data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/sd/announcements/${id}`),
}

export const sdRoutingApi = {
  list:                (): Promise<Response<unknown>> => api.get('/sd/routing-rules'),
  create:              (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/routing-rules', data),
  update:              (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/routing-rules/${id}`, data),
  delete:              (id: Id): Promise<Response<unknown>> => api.delete(`/sd/routing-rules/${id}`),
  queue:               (params?: Params): Promise<Response<unknown>> => api.get('/sd/tickets/my-queue', { params }),
  tickets:             (params?: Params): Promise<Response<unknown>> => api.get('/sd/tickets', { params }),
  majorIncidents:      (): Promise<Response<unknown>> => api.get('/sd/major-incidents'),
  createMajorIncident: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/major-incidents', data),
}

export const sdKbApi = {
  list:              (params?: Params): Promise<Response<unknown>> => api.get('/sd/kb', { params }),
  create:            (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/kb', data),
  update:            (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sd/kb/${id}`, data),
  delete:            (id: Id): Promise<Response<unknown>> => api.delete(`/sd/kb/${id}`),
  knownErrors:       (): Promise<Response<unknown>> => api.get('/sd/known-errors'),
  knownErrorTickets: (id: Id): Promise<Response<unknown>> => api.get(`/sd/known-errors/${id}/tickets`),
}

export const sdWorkflowDesignerApi = {
  schema:          (): Promise<Response<unknown>> => api.get('/sd/workflow-designer/schema'),
  templates:       (): Promise<Response<unknown>> => api.get('/sd/workflow-designer/templates'),
  blueprints:      (params?: Params): Promise<Response<unknown>> => api.get('/sd/workflow-designer/blueprints', { params }),
  blueprint:       (id: Id): Promise<Response<unknown>> => api.get(`/sd/workflow-designer/blueprints/${id}`),
  createBlueprint: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/workflow-designer/blueprints', data),
  createVersion:   (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/workflow-designer/blueprints/${id}/versions`, data),
  publish:         (id: Id, version: string | number): Promise<Response<unknown>> =>
    api.post(`/sd/workflow-designer/blueprints/${id}/publish/${version}`),
  validate:        (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/workflow-designer/validate', data),
  clone:           (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/workflow-designer/blueprints/${id}/clone`, data),
  archive:         (id: Id): Promise<Response<unknown>> => api.delete(`/sd/workflow-designer/blueprints/${id}`),
  startRun:        (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/workflow-designer/blueprints/${id}/runs`, data),
  runs:            (params?: Params): Promise<Response<unknown>> => api.get('/sd/workflow-designer/runs', { params }),
  run:             (rid: Id): Promise<Response<unknown>> => api.get(`/sd/workflow-designer/runs/${rid}`),
  resumeRun:       (rid: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/workflow-designer/runs/${rid}/resume`, data),
  cancelRun:       (rid: Id, reason?: string): Promise<Response<unknown>> =>
    api.post(`/sd/workflow-designer/runs/${rid}/cancel`, { reason }),
}

export const majorIncidentsApi = {
  list:   (): Promise<Response<unknown>> => api.get('/sd/major-incidents'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/major-incidents', data),
}

export const sdMajorIncidentsApi = majorIncidentsApi

export const slaSchedulesApi = {
  list:   (params?: Params): Promise<Response<unknown>> => api.get('/sla-schedules', { params }),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/sla-schedules', data),
  update: (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/sla-schedules/${id}`, data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/sla-schedules/${id}`),
}

export const slaCalendarsApi = {
  list:          (): Promise<Response<unknown>> => api.get('/cmdb/sla-calendars'),
  create:        (data: JsonBody): Promise<Response<unknown>> => api.post('/cmdb/sla-calendars', data),
  update:        (id: Id, data: JsonBody): Promise<Response<unknown>> => api.patch(`/cmdb/sla-calendars/${id}`, data),
  delete:        (id: Id): Promise<Response<unknown>> => api.delete(`/cmdb/sla-calendars/${id}`),
  holidays:      (calId: Id): Promise<Response<unknown>> => api.get(`/cmdb/sla-calendars/${calId}/holidays`),
  createHoliday: (calId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/cmdb/sla-calendars/${calId}/holidays`, data),
  updateHoliday: (calId: Id, id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.patch(`/cmdb/sla-calendars/${calId}/holidays/${id}`, data),
  deleteHoliday: (calId: Id, id: Id): Promise<Response<unknown>> =>
    api.delete(`/cmdb/sla-calendars/${calId}/holidays/${id}`),
  checkDate:     (calId: Id, date: string): Promise<Response<unknown>> =>
    api.get(`/cmdb/sla-calendars/${calId}/check-date?check_date=${encodeURIComponent(date)}`),
}

export const autoResolutionApi = {
  getConfig:   (): Promise<Response<unknown>> => api.get('/sd/auto-resolution/config'),
  getStats:    (): Promise<Response<unknown>> => api.get('/sd/auto-resolution/stats'),
  patchConfig: (data: JsonBody): Promise<Response<unknown>> => api.patch('/sd/auto-resolution/config', data),
  runJob:      (params?: Params): Promise<Response<unknown>> =>
    api.post('/sd/auto-resolution/run-job', null, { params }),
  runCloseJob: (): Promise<Response<unknown>> => api.post('/sd/auto-resolution/run-close-job'),
}

export const alertClustersApi = {
  list:    (): Promise<Response<unknown>> => api.get('/sd/alert-clusters'),
  stats:   (): Promise<Response<unknown>> => api.get('/sd/alert-clusters/stats'),
  merge:   (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/alert-clusters/merge', data),
  runScan: (): Promise<Response<unknown>> => api.post('/sd/alert-clusters/run-scan'),
}

export const changeRolloutApi = {
  listPlans:    (changeId: Id): Promise<Response<unknown>> => api.get(`/sd/changes/${changeId}/rollout-plans`),
  getPlan:      (id: Id): Promise<Response<unknown>> => api.get(`/sd/changes/rollout-plans/${id}`),
  createPlan:   (changeId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/changes/${changeId}/rollout-plans`, data),
  approvePlan:  (id: Id): Promise<Response<unknown>> => api.post(`/sd/changes/rollout-plans/${id}/approve`),
  advancePhase: (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/changes/rollout-plans/${id}/advance-phase`, data),
  simulate:     (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/changes/rollout-plans/simulate', data),
  simulatePlan: (changeId: Id, planId: Id): Promise<Response<unknown>> =>
    api.post(`/sd/changes/${changeId}/rollout-plans/${planId}/simulate`, {}),
  rollback:     (changeId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/changes/${changeId}/rollback`, data),
}

export const cabApi = {
  changes: (): Promise<Response<unknown>> => api.get('/cab/changes'),
  windows: (): Promise<Response<unknown>> => api.get('/cab/windows'),
  vote:    (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/cab/changes/${id}/vote`, data),
  close:   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/cab/changes/${id}/close`, data),
}

export const voiceAgentApi = {
  getConfig:     (): Promise<Response<unknown>> => api.get('/sd/voice/config'),
  updateConfig:  (data: JsonBody): Promise<Response<unknown>> => api.put('/sd/voice/config', data),
  createSession: (data: JsonBody): Promise<Response<unknown>> => api.post('/sd/voice/sessions', data),
  listSessions:  (params?: Params): Promise<Response<unknown>> => api.get('/sd/voice/sessions', { params }),
  getSession:    (id: Id): Promise<Response<unknown>> => api.get(`/sd/voice/sessions/${id}`),
  addTurn:       (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/voice/sessions/${id}/turn`, data),
  closeSession:  (id: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/voice/sessions/${id}/close`, data),
  createTicket:  (id: Id): Promise<Response<unknown>> => api.post(`/sd/voice/sessions/${id}/ticket`),
}

export const incidentAssignmentApi = {
  recommend: (ticketId: Id, data: JsonBody): Promise<Response<unknown>> =>
    api.post(`/sd/tickets/${ticketId}/recommend-assignment`, data),
  stats:     (): Promise<Response<unknown>> => api.get('/sd/assignment/stats'),
}

export const wsApi = {
  ticket: (): Promise<Response<unknown>> => api.get('/ws/ticket'),
}
