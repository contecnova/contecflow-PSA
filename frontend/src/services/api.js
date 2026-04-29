import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,  // send httpOnly cookies on every request
  timeout: 30000,
})

// Strip Content-Type for FormData so the browser sets the correct multipart boundary.
// Authentication is handled exclusively via httpOnly cookies (withCredentials: true).
// No tokens are read from or written to localStorage to prevent XSS exposure.
api.interceptors.request.use((config) => {
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

// Singleton refresh promise — ensures only one /auth/refresh call is in flight at a time.
// All concurrent 401s wait for the same promise instead of each firing their own refresh,
// which would invalidate the rotating refresh token for all but the first caller.
let _refreshPromise = null

// Auto-refresh on 401 — cookies are sent automatically; no localStorage needed
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    const status = err.response?.status
    const requestPath = original?.url || ''
    const isAuthFlowRequest = requestPath.includes('/auth/login') || requestPath.includes('/auth/refresh') || requestPath.includes('/auth/me')

    // Avoid infinite loops: skip if already retried or if there's no response
    if (!err.response || original._retry || isAuthFlowRequest) {
      return Promise.reject(err)
    }

    // 401 — token expirado: intentar refresh silencioso via cookie
    if (status === 401) {
      original._retry = true
      try {
        // Reuse an in-flight refresh instead of firing a new one — prevents token rotation
        // from invalidating the refresh token before all concurrent callers have retried.
        if (!_refreshPromise) {
          _refreshPromise = axios
            .post(`${BASE_URL}/auth/refresh`, null, { withCredentials: true })
            .finally(() => { _refreshPromise = null })
        }
        await _refreshPromise
        // New access_token cookie is now set — retry original request
        return api(original)
      } catch {
        _refreshPromise = null
        // Refresh falló — notificar a la UI para que el usuario vuelva a hacer login
        window.dispatchEvent(new CustomEvent('auth:session-expired'))
      }
    }

    return Promise.reject(err)
  }
)


// ── Rate Cards ────────────────────────────────────────────────────────────────
export const rateCardsApi = {
  list:            ()         => api.get('/rate-cards'),
  get:             (id)       => api.get(`/rate-cards/${id}`),
  create:          (d)        => api.post('/rate-cards', d),
  update:          (id, d)    => api.patch(`/rate-cards/${id}`, d),
  delete:          (id)       => api.delete(`/rate-cards/${id}`),
  duplicate:       (id, d)    => api.post(`/rate-cards/${id}/duplicate`, d),
  addEntry:        (id, d)    => api.post(`/rate-cards/${id}/entries`, d),
  updateEntry:     (id,eid,d) => api.patch(`/rate-cards/${id}/entries/${eid}`, d),
  deleteEntry:     (id,eid)   => api.delete(`/rate-cards/${id}/entries/${eid}`),
  addOverride:     (id, d)    => api.post(`/rate-cards/${id}/overrides`, d),
  deleteOverride:  (id,oid)   => api.delete(`/rate-cards/${id}/overrides/${oid}`),
  effectiveRate:   (params)   => api.get('/rate-cards/effective', { params }),
}

// ── Milestones (SOW flow) ─────────────────────────────────────────────────────
export const milestonesApi = {
  list:            (projectId) => api.get(`/milestones/project/${projectId}`),
  create:          (pid, d)    => api.post(`/milestones/project/${pid}`, d),
  update:          (id, d)     => api.patch(`/milestones/${id}`, d),
  delete:          (id)        => api.delete(`/milestones/${id}`),
  complete:        (id)        => api.post(`/milestones/${id}/complete`),
  uncomplete:      (id)        => api.post(`/milestones/${id}/uncomplete`),
  requestApproval: (id, d)     => api.post(`/milestones/${id}/request-approval`, d || {}),
  approve:         (id, d)     => api.post(`/milestones/${id}/approve`, d),
  generateInvoice: (id)        => api.post(`/milestones/${id}/generate-invoice`),
  dashboard:       ()          => api.get('/milestones/dashboard/pending'),
}

// ── Resource Forecast ─────────────────────────────────────────────────────────
export const forecastApi = {
  heatmap:      (params) => api.get('/resource-forecast/weeks',        { params }),
  userDetail:   (uid, p) => api.get(`/resource-forecast/users/${uid}`, { params: p }),
  availability: (params) => api.get('/resource-forecast/availability',  { params }),
  summary:      (params) => api.get('/resource-forecast/summary',       { params }),
}

// ── Approvals ─────────────────────────────────────────────────────────────────
export const approvalsApi = {
  listWorkflows:     (params)      => api.get('/approvals/workflows', { params }),
  getWorkflow:       (id)          => api.get(`/approvals/workflows/${id}`),
  createWorkflow:    (d)           => api.post('/approvals/workflows', d),
  updateWorkflow:    (id, d)       => api.patch(`/approvals/workflows/${id}`, d),
  deleteWorkflow:    (id)          => api.delete(`/approvals/workflows/${id}`),
  addStep:           (wid, d)      => api.post(`/approvals/workflows/${wid}/steps`, d),
  updateStep:        (wid, sid, d) => api.patch(`/approvals/workflows/${wid}/steps/${sid}`, d),
  deleteStep:        (wid, sid)    => api.delete(`/approvals/workflows/${wid}/steps/${sid}`),
  listRequests:      (params)      => api.get('/approvals/requests', { params }), // ya estaba correcto
  pendingMyAction:   ()            => api.get('/approvals/requests/pending-my-action'),
  createRequest:     (d)           => api.post('/approvals/requests', d),
  decide:            (id, d)       => api.post(`/approvals/requests/${id}/decide`, d),
  cancel:            (id)          => api.post(`/approvals/requests/${id}/cancel`),
  stats:             ()            => api.get('/approvals/stats'),
}

export const uatApi = {
  list:   (projectId, params) => api.get(`/projects/${projectId}/uat`, { params }),
  create: (projectId, data)   => api.post(`/projects/${projectId}/uat`, data),
  update: (projectId, id, d)  => api.patch(`/projects/${projectId}/uat/${id}`, d),
  remove: (projectId, id)     => api.delete(`/projects/${projectId}/uat/${id}`),
  export: (projectId)         => api.get(`/projects/${projectId}/uat/export`),
}

export default api

// ── Typed API helpers ─────────────────────────────────────────────────────────

export const authApi = {
  login:          (credentials) => api.post('/auth/login', credentials),
  forgotPassword: (payload)     => api.post('/auth/password/forgot', payload),
  resetPassword:  (payload)     => api.post('/auth/password/reset', payload),
  me:             ()            => api.get('/auth/me'),
  syncLdap:       ()            => api.post('/auth/ldap/sync'),
}

export const usersApi = {
  list:           (params) => api.get('/users', { params }),
  withRates:      () => api.get('/users/with-rates'),
  load:           (params) => api.get('/users/load', { params }),
  get:            (id) => api.get(`/users/${id}`),
  create:         (data) => api.post('/users', data),
  update:         (id, data) => api.patch(`/users/${id}`, data),
  deactivate:     (id) => api.delete(`/users/${id}`),
  deletePermanent:(id) => api.delete(`/users/${id}/permanent`),
  productivity:   (id, params) => api.get(`/users/${id}/productivity`, { params }),
}

export const projectsApi = {
  list:       (params) => api.get('/projects', { params }),
  get:        (id) => api.get(`/projects/${id}`),
  create:     (data) => api.post('/projects', data),
  update:     (id, data) => api.patch(`/projects/${id}`, data),
  team:       (id) => api.get(`/projects/${id}/team`),
  addPhase:   (id, data) => api.post(`/projects/${id}/phases`, data),
}

export const tasksApi = {
  list:       (params) => api.get('/tasks', { params }),
  kanban:     (projectId) => api.get(`/tasks/kanban/${projectId}`),
  get:        (id) => api.get(`/tasks/${id}`),
  create:     (data) => api.post('/tasks', data),
  update:     (id, data) => api.patch(`/tasks/${id}`, data),
  delete:     (id) => api.delete(`/tasks/${id}`),
  comment:    (id, data) => api.post(`/tasks/${id}/comments`, data),
  bulkUpdate: (data) => api.post('/tasks/bulk-update', data),
}

export const imputationsApi = {
  list:           (params) => api.get('/imputations', { params }),
  myWeek:         (params) => api.get('/imputations/my/week', { params }),
  create:         (data) => api.post('/imputations', data),
  update:         (id, data) => api.patch(`/imputations/${id}`, data),
  delete:         (id) => api.delete(`/imputations/${id}`),
  approve:        (id) => api.post(`/imputations/${id}/approve`),
  timerCurrent:   () => api.get('/imputations/timer/current'),
  timerStart:     (data) => api.post('/imputations/timer/start', data),
  timerPause:     () => api.post('/imputations/timer/pause'),
  timerResume:    () => api.post('/imputations/timer/resume'),
  timerStop:      (data) => api.post('/imputations/timer/stop', data),
}

export const analyticsApi = {
  query:        (metricId, params) => api.get(`/analytics/query/${metricId}`, { params }),
  filterOptions: ()                => api.get('/analytics/filters/options'),
  hoursWeek:    (params)           => api.get('/analytics/hours_by_week', { params }),
  utilization:  (params)           => api.get('/analytics/utilization/advanced', { params }),
  metricBreaches: (params)         => api.get('/analytics/alerts/metric-breaches', { params }),
  // BI / OLAP
  narrative:       (params)        => api.get('/analytics/narrative', { params }),
  ask:             (question)      => api.post('/analytics/ask', { question }),
  olapKpis:        ()              => api.get('/analytics/olap/kpis'),
  olapFunnel:      ()              => api.get('/analytics/olap/pipeline-funnel'),
  olapPortfolio:   ()              => api.get('/analytics/olap/portfolio-health'),
  olapMargin:      (months)        => api.get('/analytics/olap/margin-evolution', { params: { months } }),
  olapUtilization: ()              => api.get('/analytics/olap/utilization'),
}

export const biCollaborationApi = {
  listComments:   (params)             => api.get('/bi/collaboration/comments', { params }),
  createComment:  (payload)            => api.post('/bi/collaboration/comments', payload),
  resolveComment: (commentId)          => api.patch(`/bi/collaboration/comments/${commentId}/resolve`),
  listSharedViews: (params)            => api.get('/bi/collaboration/shared-views', { params }),
  createSharedView: (payload)          => api.post('/bi/collaboration/shared-views', payload),
  patchSharedView: (viewId, payload)   => api.patch(`/bi/collaboration/shared-views/${viewId}`, payload),
  governanceOverview: ()               => api.get('/bi/governance/overview'),
  governanceRules: ()                  => api.get('/bi/governance/rules'),
  updateGovernanceRules: (payload)     => api.patch('/bi/governance/rules', payload),
  runGovernanceChecks: ()              => api.post('/bi/governance/run-checks'),
  lastGovernanceRun: ()                => api.get('/bi/governance/last-run'),
}

export const biIntelligenceApi = {
  revenueForecast: (params)            => api.get('/bi/intelligence/ml/forecast/revenue', { params }),
  revenueAnomalies: (params)           => api.get('/bi/intelligence/ml/anomalies/revenue', { params }),
  listConnectors: ()                   => api.get('/bi/intelligence/connectors'),
  patchConnector: (name, payload)      => api.patch(`/bi/intelligence/connectors/${name}`, payload),
  syncConnector: (name)                => api.post(`/bi/intelligence/connectors/${name}/sync`),
  reportPresets: ()                    => api.get('/bi/intelligence/reports/presets'),
  previewPreset: (payload)             => api.post('/bi/intelligence/reports/preview', payload),
  queryBuilderSchema: ()               => api.get('/bi/intelligence/query-builder/schema'),
  queryBuilderPreview: (payload)       => api.post('/bi/intelligence/query-builder/preview', payload),
  queryBuilderTemplates: ()            => api.get('/bi/intelligence/query-builder/templates'),
  saveQueryBuilderTemplate: (payload)  => api.post('/bi/intelligence/query-builder/templates', payload),
  deleteQueryBuilderTemplate: (id)     => api.delete(`/bi/intelligence/query-builder/templates/${id}`),
  deliveryOverview: ()                 => api.get('/bi/intelligence/delivery/overview'),
  runDeliveryNow: (reportId)           => api.post(`/bi/intelligence/delivery/run/${reportId}`),
  realtimeToken: ()                    => api.get('/bi/intelligence/realtime/token'),
}

export const biPlatformApi = {
  sdkManifest: ()                      => api.get('/bi/platform/embed/sdk'),
  embedSettings: ()                    => api.get('/bi/platform/embed/settings'),
  patchEmbedSettings: (payload)        => api.patch('/bi/platform/embed/settings', payload),
  embedToken: (payload)                => api.post('/bi/platform/embed/token', payload),
  connectorCatalog: ()                 => api.get('/bi/platform/connectors/catalog'),
  patchCatalogConnector: (name, p)     => api.patch(`/bi/platform/connectors/catalog/${name}`, p),
  listCustomConnectors: ()             => api.get('/bi/platform/connectors/custom'),
  createCustomConnector: (payload)     => api.post('/bi/platform/connectors/custom', payload),
  deleteCustomConnector: (id)          => api.delete(`/bi/platform/connectors/custom/${id}`),
  testCustomConnector: (id)            => api.post(`/bi/platform/connectors/custom/${id}/test`),
  lineage: ()                          => api.get('/bi/platform/governance/lineage'),
  upsertLineageEdge: (payload)         => api.post('/bi/platform/governance/lineage/edges', payload),
  logAccess: (payload)                 => api.post('/bi/platform/governance/audit/access', payload),
  createSnapshot: (datasetKey, p)      => api.post(`/bi/platform/versioning/${datasetKey}/snapshots`, p),
  listSnapshots: (datasetKey)          => api.get(`/bi/platform/versioning/${datasetKey}/snapshots`),
  diffSnapshots: (datasetKey, fromId, toId) => api.get(`/bi/platform/versioning/${datasetKey}/diff`, { params: { from_id: fromId, to_id: toId } }),
}

export const biSmartAlertsApi = {
  supportedMetrics: ()                 => api.get('/bi/alerts/supported-metrics'),
  listRules: ()                        => api.get('/bi/alerts/rules'),
  createRule: (payload)                => api.post('/bi/alerts/rules', payload),
  updateRule: (ruleId, payload)        => api.patch(`/bi/alerts/rules/${ruleId}`, payload),
  deleteRule: (ruleId)                 => api.delete(`/bi/alerts/rules/${ruleId}`),
  evaluate: ()                         => api.post('/bi/alerts/evaluate'),
  getHistory: (limit = 100)            => api.get('/bi/alerts/history', { params: { limit } }),
  acknowledge: (alertId)               => api.post(`/bi/alerts/history/${alertId}/acknowledge`),
  seedDefaults: ()                     => api.post('/bi/alerts/seed-defaults'),
}

export const biBookmarksApi = {
  list: ()                             => api.get('/bi/bookmarks'),
  create: (payload)                    => api.post('/bi/bookmarks', payload),
  get: (id)                            => api.get(`/bi/bookmarks/${id}`),
  update: (id, payload)                => api.patch(`/bi/bookmarks/${id}`, payload),
  delete: (id)                         => api.delete(`/bi/bookmarks/${id}`),
}

export const biReportBuilderV2Api = {
  listPresets: (params)                => api.get('/bi/reports/v2/presets', { params }),
  getPreset: (presetId)                => api.get(`/bi/reports/v2/presets/${presetId}`),
  categories: ()                       => api.get('/bi/reports/v2/categories'),
  customize: (presetId, payload)       => api.post(`/bi/reports/v2/presets/${presetId}/customize`, payload),
  resetCustomize: (presetId)           => api.delete(`/bi/reports/v2/presets/${presetId}/customize`),
  preview: (presetId, limit = 50)      => api.get(`/bi/reports/v2/presets/${presetId}/preview`, { params: { limit } }),
  export: (presetId, format = 'json')  => api.get(`/bi/reports/v2/presets/${presetId}/export`, { params: { format } }),
}

export const dashboardApi = {
  kpis:           () => api.get('/dashboard/kpis'),
  projectsHealth: (params) => api.get('/dashboard/projects-health', { params }),
  resourceLoad:   (params) => api.get('/dashboard/resource-load', { params }),
  profitability:  (params) => api.get('/dashboard/profitability', { params }),
  teamProductivity: (params) => api.get('/dashboard/productivity/team', { params }),
}

export const alertsApi = {
  list:     (params) => api.get('/alerts', { params }),
  run:      () => api.post('/alerts/run'),
  read:     (id) => api.patch(`/alerts/${id}/read`),
  resolve:  (id) => api.patch(`/alerts/${id}/resolve`),
}

export const integrationsApi = {
  exportImputations: (data) => api.post('/integrations/export/imputations', data, { responseType: 'blob' }),
  exportProjects:    (data) => api.post('/integrations/export/projects', data, { responseType: 'blob' }),
  jiraSync:          (projectId) => api.post(`/integrations/jira/sync/${projectId}`),
  jiraStatus:        (projectId) => api.get(`/integrations/jira/status/${projectId}`),
}

export const clientsApi = {
  list:         (params)     => api.get('/clients', { params }),
  get:          (id)         => api.get(`/clients/${id}`),
  create:       (data)       => api.post('/clients', data),
  update:       (id, data)   => api.patch(`/clients/${id}`, data),
  delete:       (id)         => api.delete(`/clients/${id}`),
  contacts:     (id)         => api.get(`/clients/${id}/contacts`),
  addContact:   (id, data)   => api.post(`/clients/${id}/contacts`, data),
  deleteContact:(id, cid)    => api.delete(`/clients/${id}/contacts/${cid}`),
  view360:      (id)         => api.get(`/clients/${id}/360`),
}

// ── Sprints ───────────────────────────────────────────────────────────────────
export const sprintsApi = {
  list:    (projectId, params) => api.get('/sprints', { params: { project_id: projectId, ...params } }),
  get:     (id)                => api.get(`/sprints/${id}`),
  create:  (data)              => api.post('/sprints', data),
  update:  (id, data)          => api.patch(`/sprints/${id}`, data),
  delete:  (id)                => api.delete(`/sprints/${id}`),
  start:   (id)                => api.post(`/sprints/${id}/start`),
  complete:(id)                => api.post(`/sprints/${id}/complete`),
  burndown:(id)                => api.get(`/sprints/${id}/burndown`),
  velocity:(projectId)         => api.get(`/sprints/velocity/${projectId}`),
}

// ── Epics ─────────────────────────────────────────────────────────────────────
export const epicsApi = {
  list:   (projectId) => api.get('/epics', { params: { project_id: projectId } }),
  get:    (id)        => api.get(`/epics/${id}`),
  create: (data)      => api.post('/epics', data),
  update: (id, data)  => api.patch(`/epics/${id}`, data),
  delete: (id)        => api.delete(`/epics/${id}`),
}

// ── Contracts ─────────────────────────────────────────────────────────────────
export const contractsApi = {
  list:       (params)      => api.get('/contracts', { params }),
  get:        (id)          => api.get(`/contracts/${id}`),
  create:     (data)        => api.post('/contracts', data),
  update:     (id, data)    => api.patch(`/contracts/${id}`, data),
  delete:     (id)          => api.delete(`/contracts/${id}`),
  workOrders: (id)          => api.get(`/contracts/${id}/work-orders`),
}

// ── Expenses ──────────────────────────────────────────────────────────────────
export const expensesApi = {
  list:    (params)   => api.get('/expenses', { params }),
  my:      (params)   => api.get('/expenses/my', { params }),
  pending: ()         => api.get('/expenses/pending'),
  get:     (id)       => api.get(`/expenses/${id}`),
  create:  (data)     => api.post('/expenses', data),
  update:  (id, data) => api.patch(`/expenses/${id}`, data),
  approve: (id)       => api.post(`/expenses/${id}/approve`),
  reject:  (id, data) => api.post(`/expenses/${id}/reject`, data),
  delete:  (id)       => api.delete(`/expenses/${id}`),
}

// ── Risks ─────────────────────────────────────────────────────────────────────
export const risksApi = {
  list:   (projectId, params) => api.get(`/risks/${projectId}`, { params }),
  get:    (projectId, riskId) => api.get(`/risks/${projectId}/${riskId}`),
  create: (projectId, data)   => api.post(`/risks/${projectId}`, data),
  update: (projectId, riskId, data) => api.patch(`/risks/${projectId}/${riskId}`, data),
  delete: (projectId, riskId) => api.delete(`/risks/${projectId}/${riskId}`),
  scores: ()                  => api.get('/risks/scores'),
}

// ── OKRs ─────────────────────────────────────────────────────────────────────
export const okrsApi = {
  list:       (params)      => api.get('/okrs', { params }),
  get:        (id)          => api.get(`/okrs/${id}`),
  create:     (data)        => api.post('/okrs', data),
  update:     (id, data)    => api.patch(`/okrs/${id}`, data),
  delete:     (id)          => api.delete(`/okrs/${id}`),
  updateKR:   (id, krid, d) => api.patch(`/okrs/${id}/key-results/${krid}`, d),
}

// ── Pipeline (opportunities) ──────────────────────────────────────────────────
export const pipelineApi = {
  list:       (params)    => api.get('/pipeline', { params }),
  get:        (id)        => api.get(`/pipeline/${id}`),
  create:     (data)      => api.post('/pipeline', data),
  update:     (id, data)  => api.patch(`/pipeline/${id}`, data),
  delete:     (id)        => api.delete(`/pipeline/${id}`),
  activities:       (id)          => api.get(`/pipeline/${id}/activities`),
  addActivity:      (id, data)    => api.post(`/pipeline/${id}/activities`, data),
  generateProposal: (id, payload) => api.post(`/pipeline/${id}/generate-proposal`, payload || {}),
  markProposalSent: (id)          => api.post(`/pipeline/${id}/mark-proposal-sent`),
  convertToProject: (id)          => api.post(`/pipeline/${id}/convert`),
  getProposal:      (id)          => api.get(`/pipeline/${id}/proposal`),
}

// ── Deliverables ──────────────────────────────────────────────────────────────
export const deliverablesApi = {
  list:    (projectId) => api.get('/deliverables', { params: { project_id: projectId } }),
  get:     (id)        => api.get(`/deliverables/${id}`),
  create:  (data)      => api.post('/deliverables', data),
  update:  (id, data)  => api.patch(`/deliverables/${id}`, data),
  delete:  (id)        => api.delete(`/deliverables/${id}`),
  overview:()          => api.get('/deliverables/overview'),
}

// ── Subcontractors ────────────────────────────────────────────────────────────
export const subcontractorsApi = {
  list:        (params)    => api.get('/subcontractors', { params }),
  get:         (id)        => api.get(`/subcontractors/${id}`),
  create:      (data)      => api.post('/subcontractors', data),
  update:      (id, data)  => api.patch(`/subcontractors/${id}`, data),
  delete:      (id)        => api.delete(`/subcontractors/${id}`),
  assignments: (id)        => api.get(`/subcontractors/${id}/assignments`),
  timelogs:    (id, params)=> api.get(`/subcontractors/${id}/timelogs`, { params }),
  invoices:    (id)        => api.get(`/subcontractors/${id}/invoices`),
}

// ── Training ──────────────────────────────────────────────────────────────────
export const trainingApi = {
  courses:     (params)    => api.get('/training/courses', { params }),
  course:      (id)        => api.get(`/training/courses/${id}`),
  createCourse:(data)      => api.post('/training/courses', data),
  updateCourse:(id, data)  => api.patch(`/training/courses/${id}`, data),
  deleteCourse:(id)        => api.delete(`/training/courses/${id}`),
  certs:       (params)    => api.get('/training/certifications', { params }),
  cert:        (id)        => api.get(`/training/certifications/${id}`),
  createCert:  (data)      => api.post('/training/certifications', data),
  updateCert:  (id, data)  => api.patch(`/training/certifications/${id}`, data),
  deleteCert:  (id)        => api.delete(`/training/certifications/${id}`),
  enroll:      (data)      => api.post('/training/enrollments', data),
  enrollments: (params)    => api.get('/training/enrollments', { params }),
}

// ── Absences ──────────────────────────────────────────────────────────────────
export const absencesApi = {
  my:        (params)    => api.get('/absences/my', { params }),
  pending:   ()          => api.get('/absences/pending'),
  team:      (params)    => api.get('/absences/team', { params }),
  calendar:  (params)    => api.get('/absences/calendar', { params }),
  get:       (id)        => api.get(`/absences/${id}`),
  create:    (data)      => api.post('/absences', data),
  update:    (id, data)  => api.patch(`/absences/${id}`, data),
  approve:   (id)        => api.post(`/absences/${id}/approve`),
  reject:    (id, data)  => api.post(`/absences/${id}/reject`, data),
  delete:    (id)        => api.delete(`/absences/${id}`),
  balance:   (params)    => api.get('/absences/balance', { params }),
  policies:  ()          => api.get('/absences/policies'),
}

// ── ALM — Assets, Licenses, Vendors ──────────────────────────────────────────
export const assetsApi = {
  list:    (params)   => api.get('/alm/assets', { params }),
  get:     (id)       => api.get(`/alm/assets/${id}`),
  create:  (data)     => api.post('/alm/assets', data),
  update:  (id, data) => api.patch(`/alm/assets/${id}`, data),
  delete:  (id)       => api.delete(`/alm/assets/${id}`),
  cmdb:    (id)       => api.get(`/alm/assets/${id}/cmdb`),
}

export const licensesApi = {
  list:    (params)   => api.get('/alm/licenses', { params }),
  get:     (id)       => api.get(`/alm/licenses/${id}`),
  create:  (data)     => api.post('/alm/licenses', data),
  update:  (id, data) => api.patch(`/alm/licenses/${id}`, data),
  delete:  (id)       => api.delete(`/alm/licenses/${id}`),
  assign:  (id, data) => api.post(`/alm/licenses/${id}/assign`, data),
  revoke:  (id, uid)  => api.delete(`/alm/licenses/${id}/users/${uid}`),
}

export const vendorsApi = {
  list:   (params)   => api.get('/alm/vendors', { params }),
  get:    (id)       => api.get(`/alm/vendors/${id}`),
  create: (data)     => api.post('/alm/vendors', data),
  update: (id, data) => api.patch(`/alm/vendors/${id}`, data),
  delete: (id)       => api.delete(`/alm/vendors/${id}`),
}

// ── Service Desk ──────────────────────────────────────────────────────────────
export const ticketsApi = {
  list:    (params)   => api.get('/sd/tickets', { params }),
  get:     (id)       => api.get(`/sd/tickets/${id}`),
  create:  (data)     => api.post('/sd/tickets', data),
  update:  (id, data) => api.patch(`/sd/tickets/${id}`, data),
  close:   (id, data) => api.post(`/sd/tickets/${id}/close`, data),
  comment: (id, data) => api.post(`/sd/tickets/${id}/comments`, data),
  aiSuggest: (id, data) => api.post(`/sd/tickets/${id}/ai-suggest`, data),
  split:   (id, data) => api.post(`/sd/tickets/${id}/split`, data),
  links:   (id)       => api.get(`/sd/tickets/${id}/links`),
  addLink: (id, data) => api.post(`/sd/tickets/${id}/links`, data),
}

export const problemsApi = {
  list:   (params)   => api.get('/sd/problems', { params }),
  get:    (id)       => api.get(`/sd/problems/${id}`),
  create: (data)     => api.post('/sd/problems', data),
  update: (id, data) => api.patch(`/sd/problems/${id}`, data),
  delete: (id)       => api.delete(`/sd/problems/${id}`),
}

export const changesApi = {
  list:    (params)   => api.get('/sd/changes', { params }),
  get:     (id)       => api.get(`/sd/changes/${id}`),
  create:  (data)     => api.post('/sd/changes', data),
  update:  (id, data) => api.patch(`/sd/changes/${id}`, data),
  delete:  (id)       => api.delete(`/sd/changes/${id}`),
  approve: (id, data) => api.post(`/sd/changes/${id}/approve`, data),
}

// ── ML Predictions ────────────────────────────────────────────────────────────
export const predictionsApi = {
  overrunRisk:    (projectId)  => api.post('/predictions/overrun-risk', { project_id: projectId }),
  portfolioRisk:  ()           => api.get('/predictions/portfolio-risk'),
  train:          ()           => api.post('/predictions/train'),
  models:         ()           => api.get('/predictions/models'),
  logs:           (params)     => api.get('/predictions/logs', { params }),
}

// ── Revenue Recognition (ASC 606) ─────────────────────────────────────────────
export const revenueRecognitionApi = {
  dashboard:           (year, months) => api.get('/revenue-recognition/dashboard', { params: { year, months } }),
  contracts:           (params)       => api.get('/revenue-recognition/contracts', { params }),
  getContract:         (id)           => api.get(`/revenue-recognition/contracts/${id}`),
  createContract:      (data)         => api.post('/revenue-recognition/contracts', data),
  updateContract:      (id, data)     => api.patch(`/revenue-recognition/contracts/${id}`, data),
  deleteContract:      (id)           => api.delete(`/revenue-recognition/contracts/${id}`),
  obligations:         (contractId)   => api.get(`/revenue-recognition/contracts/${contractId}/obligations`),
  createObligation:    (contractId, d)=> api.post(`/revenue-recognition/contracts/${contractId}/obligations`, d),
  updateObligation:    (id, data)     => api.patch(`/revenue-recognition/obligations/${id}`, data),
  deleteObligation:    (id)           => api.delete(`/revenue-recognition/obligations/${id}`),
  entries:             (params)       => api.get('/revenue-recognition/entries', { params }),
  reverseEntry:        (id)           => api.post(`/revenue-recognition/entries/${id}/reverse`),
  periodCloses:        ()             => api.get('/revenue-recognition/period-closes'),
  closePeriod:         (data)         => api.post('/revenue-recognition/period-closes', data),
  reopenPeriod:        (year, month)  => api.delete(`/revenue-recognition/period-closes/${year}/${month}`),
  runMonthly:          (data)         => api.post('/revenue-recognition/run-monthly', data),
}

// ── CMDB ──────────────────────────────────────────────────────────────────────
export const cmdbApi = {
  items:          (params)   => api.get('/cmdb/items', { params }),
  getItem:        (id)       => api.get(`/cmdb/items/${id}`),
  createItem:     (data)     => api.post('/cmdb/items', data),
  updateItem:     (id, data) => api.patch(`/cmdb/items/${id}`, data),
  deleteItem:     (id)       => api.delete(`/cmdb/items/${id}`),
  changelog:      (id)       => api.get(`/cmdb/items/${id}/changelog`),
  categories:     ()         => api.get('/cmdb/categories'),
  relations:      (id)       => api.get(`/cmdb/items/${id}/relations`),
  createRelation: (data)     => api.post('/cmdb/relations', data),
  deleteRelation: (id)       => api.delete(`/cmdb/relations/${id}`),
  topology:       (id, r)    => api.get(`/sd/cmdb/${id}/topology`, { params: { radius: r } }),
  topologyItems:  ()         => api.get('/sd/cmdb'),
}

// ── Timesheets ────────────────────────────────────────────────────────────────
export const timesheetsApi = {
  my:          ()              => api.get('/timesheets/my'),
  pending:     ()              => api.get('/timesheets/pending'),
  team:        ()              => api.get('/timesheets/team'),
  weekLines:   (weekStart)     => api.get(`/timesheets/my/${weekStart}/lines`),
  submit:      (weekStart)     => api.post(`/timesheets/my/${weekStart}/submit`),
  review:      (id, data)      => api.post(`/timesheets/${id}/review`, data),
}

// ── Documents ─────────────────────────────────────────────────────────────────
export const documentsApi = {
  list:      (params)   => api.get('/documents', { params }),
  get:       (id)       => api.get(`/documents/${id}`),
  upload:    (fd)       => api.post('/documents/upload', fd),
  update:    (id, data) => api.patch(`/documents/${id}`, data),
  delete:    (id)       => api.delete(`/documents/${id}`),
  approve:   (id, data) => api.post(`/documents/${id}/approve`, data),
  aiSummary: (id)       => api.post(`/documents/${id}/ai-summary`),
  addVersion:(id, fd)   => api.post(`/documents/${id}/versions`, fd),
}

// ── Custom Fields ─────────────────────────────────────────────────────────────
export const customFieldsApi = {
  list:   (projectId)          => api.get(`/custom-fields/${projectId}`),
  create: (projectId, data)    => api.post(`/custom-fields/${projectId}`, data),
  update: (projectId, id, data)=> api.patch(`/custom-fields/${projectId}/${id}`, data),
  delete: (projectId, id)      => api.delete(`/custom-fields/${projectId}/${id}`),
}

// ── Wiki ──────────────────────────────────────────────────────────────────────
export const wikiApi = {
  spaces:       ()              => api.get('epics/wiki/spaces'),
  createSpace:  (data)          => api.post('epics/wiki/spaces', data),
  pages:        (spaceId)       => api.get(`epics/wiki/spaces/${spaceId}/pages`),
  getPage:      (id)            => api.get(`epics/wiki/pages/${id}`),
  createPage:   (spaceId, data) => api.post(`epics/wiki/spaces/${spaceId}/pages`, data),
  updatePage:   (id, data)      => api.patch(`epics/wiki/pages/${id}`, data),
  deletePage:   (id)            => api.delete(`epics/wiki/pages/${id}`),
  versions:     (id)            => api.get(`epics/wiki/pages/${id}/versions`),
  restorePage:  (id, vn)        => api.post(`epics/wiki/pages/${id}/restore/${vn}`),
  search:       (q, spaceId)    => api.get(`epics/wiki/search`, { params: { q, space_id: spaceId } }),
  tags:         (space)         => api.get(`/wiki-tags/${space}`),
  createTag:    (space, data)   => api.post(`/wiki-tags/${space}`, data),
  updateTag:    (id, data)      => api.patch(`/wiki-tags/${id}`, data),
  deleteTag:    (id)            => api.delete(`/wiki-tags/${id}`),
}

/** Normalise a Pydantic v2 / FastAPI error detail to a plain string.
 *  detail can be an array of {type,loc,msg,input,url} objects or a plain string. */
export function apiErrorMsg(e, fallback = 'Error') {
  const raw = e?.response?.data?.detail
  if (Array.isArray(raw)) return raw.map(d => d.msg).join(', ')
  return raw || e?.message || fallback
}
