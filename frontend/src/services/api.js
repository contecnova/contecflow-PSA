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

    // 429 — Rate limit: dispatch event so the UI can show a user-facing warning
    if (status === 429) {
      const retryAfter = err.response?.headers?.['retry-after']
      window.dispatchEvent(new CustomEvent('api:rate-limited', {
        detail: {
          retryAfter: retryAfter ? Number(retryAfter) : null,
          path: original?.url || '',
        },
      }))
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
  catalogue:       ()              => api.get('/analytics/catalogue'),
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

export const biGovernanceAuditApi = {
  // BI Governance — audit trail, data lineage, field sensitivity
  logAccessEvent: (payload)            => api.post('/bi/governance/audit/access', payload),
  getAccessHistory: (params)           => api.get('/bi/governance/audit/access', { params }),
  listLineage: (target_table)          => api.get('/bi/governance/lineage', { params: target_table ? { target_table } : undefined }),
  trackLineage: (payload)              => api.post('/bi/governance/lineage', payload),
  listFieldSensitivity: (dataset_id)   => api.get('/bi/governance/field-sensitivity', { params: dataset_id ? { dataset_id } : undefined }),
  upsertFieldSensitivity: (payload)    => api.put('/bi/governance/field-sensitivity', payload),
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
  list:                (params)           => api.get('/contracts', { params }),
  get:                 (id)               => api.get(`/contracts/${id}`),
  create:              (data)             => api.post('/contracts', data),
  update:              (id, data)         => api.patch(`/contracts/${id}`, data),
  delete:              (id)               => api.delete(`/contracts/${id}`),
  workOrders:          (id)               => api.get(`/contracts/${id}/work-orders`),
  createWorkOrder:     (id, data)         => api.post(`/contracts/${id}/work-orders`, data),
  updateWorkOrderStatus:(id, woId, status)=> api.patch(`/contracts/${id}/work-orders/${woId}/status`, null, { params: { status } }),
}

// ── Expenses ──────────────────────────────────────────────────────────────────
export const expensesApi = {
  list:      (params)    => api.get('/expenses', { params }),
  my:        (params)    => api.get('/expenses/my', { params }),
  pending:   ()          => api.get('/expenses/pending'),
  team:      (params)    => api.get('/expenses/team', { params }),
  get:       (id)        => api.get(`/expenses/${id}`),
  create:    (data)      => api.post('/expenses', data),
  update:    (id, data)  => api.patch(`/expenses/${id}`, data),
  updateMy:  (id, data)  => api.patch(`/expenses/my/${id}`, data),
  approve:   (id)        => api.post(`/expenses/${id}/approve`),
  reject:    (id, data)  => api.post(`/expenses/${id}/reject`, data),
  review:    (id, data)  => api.post(`/expenses/${id}/review`, data),
  submitMy:  (id)        => api.post(`/expenses/my/${id}/submit`),
  recall:    (id)        => api.post(`/expenses/my/${id}/recall`),
  reimburse: (id)        => api.post(`/expenses/${id}/reimburse`),
  delete:    (id)        => api.delete(`/expenses/${id}`),
  deleteMy:  (id)        => api.delete(`/expenses/my/${id}`),
  ocr:       (fd)        => api.post('/expenses/ocr', fd),
}

// ── Risks ─────────────────────────────────────────────────────────────────────
export const risksApi = {
  list:         (projectId, params) => api.get(`/risks/${projectId}`, { params }),
  get:          (projectId, riskId) => api.get(`/risks/${projectId}/${riskId}`),
  create:       (projectId, data)   => api.post(`/risks/${projectId}`, data),
  update:       (projectId, riskId, data) => api.patch(`/risks/${projectId}/${riskId}`, data),
  delete:       (projectId, riskId) => api.delete(`/risks/${projectId}/${riskId}`),
  scores:       ()                  => api.get('/risks/scores'),
  portfolioAll: ()                  => api.get('/risks/all/portfolio'),
}

// ── OKRs ─────────────────────────────────────────────────────────────────────
export const okrsApi = {
  list:     (params)      => api.get('/okrs', { params }),
  get:      (id)          => api.get(`/okrs/${id}`),
  create:   (data)        => api.post('/okrs', data),
  update:   (id, data)    => api.patch(`/okrs/${id}`, data),
  delete:   (id)          => api.delete(`/okrs/${id}`),
  updateKR: (id, krid, d) => api.patch(`/okrs/${id}/key-results/${krid}`, d),
  createKR: (data)        => api.post('/okrs/key-results', data),
  deleteKR: (id)          => api.delete(`/okrs/key-results/${id}`),
  checkin:  (krId, data)  => api.post(`/okrs/key-results/${krId}/checkin`, data),
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
  my:             (params)    => api.get('/absences/my', { params }),
  pending:        ()          => api.get('/absences/pending'),
  team:           (params)    => api.get('/absences/team', { params }),
  calendar:       (params)    => api.get('/absences/calendar', { params }),
  get:            (id)        => api.get(`/absences/${id}`),
  create:         (data)      => api.post('/absences', data),
  createMy:       (data)      => api.post('/absences/my', data),
  update:         (id, data)  => api.patch(`/absences/${id}`, data),
  updateMy:       (id, data)  => api.patch(`/absences/my/${id}`, data),
  approve:        (id)        => api.post(`/absences/${id}/approve`),
  reject:         (id, data)  => api.post(`/absences/${id}/reject`, data),
  review:         (id, data)  => api.post(`/absences/${id}/review`, data),
  delete:         (id)        => api.delete(`/absences/${id}`),
  deleteMy:       (id)        => api.delete(`/absences/my/${id}`),
  balance:        (params)    => api.get('/absences/balance', { params }),
  vacationBalance:()          => api.get('/absences/my/vacation-balance'),
  policies:       ()          => api.get('/absences/policies'),
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
  addLink:    (id, data) => api.post(`/sd/tickets/${id}/links`, data),
  timelog:    (id, data) => api.post(`/sd/tickets/${id}/timelog`, data),
  escalate:   (id)       => api.post(`/sd/tickets/${id}/escalate`),
  slaPause:   (id, data) => api.post(`/sd/tickets/${id}/sla/pause`, data),
  slaResume:  (id)       => api.post(`/sd/tickets/${id}/sla/resume`),
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

// ── Revenue (legacy engine) ───────────────────────────────────────────────────
export const revenueApi = {
  rules:       ()               => api.get('/revenue/rules'),
  summary:     ()               => api.get('/revenue/summary'),
  createRule:  (data)           => api.post('/revenue/rules', data),
  autoCompute: (period)         => api.post('/revenue/auto-compute', { period }),
  compute:     (id, period)     => api.post(`/revenue/rules/${id}/compute`, { period }),
}

// ── Invoices ──────────────────────────────────────────────────────────────────
export const invoicesApi = {
  list:          (params)          => api.get('/invoices', { params }),
  get:           (id)              => api.get(`/invoices/${id}`),
  summary:       ()                => api.get('/invoices/summary'),
  create:        (data)            => api.post('/invoices', data),
  updateStatus:  (id, status)      => api.patch(`/invoices/${id}/status`, { status }),
  pdf:           (id)              => api.get(`/invoices/${id}/pdf`, { responseType: 'blob' }),
  fromTimesheets:(data)            => api.post('/invoices/from-timesheets', data),
}

// ── Accounting Hub (Xero / QuickBooks) ────────────────────────────────────────
export const accountingApi = {
  syncStatus:    ()                => api.get('/accounting/sync-status'),
  xeroTest:      ()                => api.post('/accounting/xero/test'),
  qbTest:        ()                => api.post('/accounting/qb/test'),
  pushInvoice:   (data)            => api.post('/accounting/push-invoice', data),
  pushBulk:      (data)            => api.post('/accounting/push-invoices-bulk', data),
  xeroContacts:  ()                => api.get('/accounting/xero/contacts'),
}

// ── Currency Rates ────────────────────────────────────────────────────────────
const getWithFallback = async (paths, config) => {
  let lastErr
  for (const path of paths) {
    try {
      return await api.get(path, config)
    } catch (err) {
      lastErr = err
      if (err?.response?.status !== 404) throw err
    }
  }
  throw lastErr
}

const postWithFallback = async (paths, data, config) => {
  let lastErr
  for (const path of paths) {
    try {
      return await api.post(path, data, config)
    } catch (err) {
      lastErr = err
      if (err?.response?.status !== 404) throw err
    }
  }
  throw lastErr
}

export const currencyApi = {
  rates:   (params)        => getWithFallback(['/currency-rates/currency/rates', '/bookings/currency/rates', '/currency/rates'], { params }),
  upsert:  (data)          => postWithFallback(['/currency-rates/currency/rates', '/bookings/currency/rates', '/currency/rates'], data),
  convert: (params)        => getWithFallback(['/currency-rates/currency/convert', '/currency/convert'], { params }),
  report:  (params)        => getWithFallback(['/currency-rates/currency/report', '/currency/report'], { params }),
}

// ── Predictive Observability ──────────────────────────────────────────────────
export const predictiveObservabilityApi = {
  status:        (orgId)   => api.get('/bi/predictive/observability/status', { params: orgId ? { organization_id: orgId } : {} }),
  health:        (params)  => api.get('/bi/predictive/observability/health', { params }),
  triggerRetrain:()        => api.post('/bi/predictive/observability/trigger-retrain'),
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
  delete:    (projectId, id)           => api.delete(`/custom-fields/${projectId}/${id}`),
  getValues: (projectId, taskId)       => api.get(`/custom-fields/${projectId}/values/${taskId}`),
  setValues: (projectId, taskId, data) => api.post(`/custom-fields/${projectId}/values/${taskId}`, data),
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

// ── Skills ────────────────────────────────────────────────────────────────────
export const skillsApi = {
  catalog:        ()               => api.get('/skills/catalog'),
  createCatalog:  (data)           => api.post('/skills/catalog', data),
  deleteCatalog:  (id)             => api.delete(`/skills/catalog/${id}`),
  userSkills:     (userId)         => api.get(`/skills/users/${userId}`),
  userHistory:    (userId)         => api.get(`/skills/users/${userId}/history`),
  addUserSkill:   (userId, data)   => api.post(`/skills/users/${userId}`, data),
  removeUserSkill:(userId, skillId)=> api.delete(`/skills/users/${userId}/${skillId}`),
  matrix:         ()               => api.get('/skills/matrix'),
  search:         (params)         => api.get('/skills/search', { params }),
}

// ── Enterprise Subcontractors ─────────────────────────────────────────────────
export const enterpriseSubsApi = {
  dashboard:        ()                     => api.get('/enterprise/subcontractors-dashboard'),
  list:             ()                     => api.get('/enterprise/subcontractors'),
  create:           (data)                 => api.post('/enterprise/subcontractors', data),
  update:           (id, data)             => api.patch(`/enterprise/subcontractors/${id}`, data),
  delete:           (id)                   => api.delete(`/enterprise/subcontractors/${id}`),
  workers:          (subId)                => api.get(`/enterprise/subcontractors/${subId}/workers`),
  createWorker:     (subId, data)          => api.post(`/enterprise/subcontractors/${subId}/workers`, data),
  updateWorker:     (id, data)             => api.patch(`/enterprise/subcontractors/workers/${id}`, data),
  deleteWorker:     (id)                   => api.delete(`/enterprise/subcontractors/workers/${id}`),
  addWorkerSkill:   (id, data)             => api.post(`/enterprise/subcontractors/workers/${id}/skills`, data),
  removeWorkerSkill:(id, skillId)          => api.delete(`/enterprise/subcontractors/workers/${id}/skills/${skillId}`),
  assignments:      (subId)                => api.get(`/enterprise/subcontractors/${subId}/assignments`),
  createAssignment: (subId, data)          => api.post(`/enterprise/subcontractors/${subId}/assignments`, data),
  timelogs:         (subId)                => api.get(`/enterprise/subcontractors/${subId}/timelogs`),
  createTimelog:    (subId, data)          => api.post(`/enterprise/subcontractors/${subId}/timelogs`, data),
  invoices:         (subId)                => api.get(`/enterprise/subcontractors/${subId}/invoices`),
  createInvoice:    (subId, data)          => api.post(`/enterprise/subcontractors/${subId}/invoices`, data),
  updateInvoice:    (subId, id, data)      => api.patch(`/enterprise/subcontractors/${subId}/invoices/${id}`, data),
}

// ── ALM Extended (contracts, cost-centers, compliance) ────────────────────────
export const almExtApi = {
  dashboard:       ()              => api.get('/alm/dashboard'),
  contracts:       ()              => api.get('/alm/contracts'),
  createContract:  (data)          => api.post('/alm/contracts', data),
  updateContract:  (id, data)      => api.patch(`/alm/contracts/${id}`, data),
  deleteContract:  (id)            => api.delete(`/alm/contracts/${id}`),
  costCenters:     ()              => api.get('/alm/cost-centers'),
  createCostCenter:(data)          => api.post('/alm/cost-centers', data),
  updateCostCenter:(id, data)      => api.patch(`/alm/cost-centers/${id}`, data),
  deleteCostCenter:(id)            => api.delete(`/alm/cost-centers/${id}`),
  compliance:      ()              => api.get('/alm/compliance'),
}

// ── CAB (Change Advisory Board) ───────────────────────────────────────────────
export const cabApi = {
  changes: ()             => api.get('/cab/changes'),
  windows: ()             => api.get('/cab/windows'),
  vote:    (id, data)     => api.post(`/cab/changes/${id}/vote`, data),
  close:   (id, data)     => api.post(`/cab/changes/${id}/close`, data),
}

// ── Project Change Requests ───────────────────────────────────────────────────
export const projectChangesApi = {
  list:       (projectId)           => api.get(`/changes/${projectId}`),
  allPending: ()                    => api.get('/changes/all/pending'),
  create:     (projectId, data)     => api.post(`/changes/${projectId}`, data),
  update:     (projectId, id, data) => api.patch(`/changes/${projectId}/${id}`, data),
  review:     (projectId, id, data) => api.post(`/changes/${projectId}/${id}/review`, data),
  submit:     (projectId, id)       => api.post(`/changes/${projectId}/${id}/submit`),
  implement:  (projectId, id)       => api.post(`/changes/${projectId}/${id}/implement`),
  delete:     (projectId, id)       => api.delete(`/changes/${projectId}/${id}`),
}

// ── NPS ───────────────────────────────────────────────────────────────────────
export const npsApi = {
  leaderboard:    ()            => api.get('/nps/leaderboard'),
  summary:        (id, days)    => api.get(`/nps/${id}/summary`, { params: { days } }),
  health:         (id, limit)   => api.get(`/nps/${id}/health`, { params: { limit } }),
  healthCompute:  (id)          => api.post(`/nps/${id}/health-compute`),
  respond:        (id, data)    => api.post(`/nps/${id}/responses`, data),
}

// ── Portfolios ────────────────────────────────────────────────────────────────
export const portfolioApi = {
  list:          ()             => api.get('/portfolios'),
  get:           (id)           => api.get(`/portfolios/${id}`),
  dashboard:     (id)           => api.get(`/portfolios/${id}/dashboard`),
  create:        (data)         => api.post('/portfolios', data),
  update:        (id, data)     => api.patch(`/portfolios/${id}`, data),
  delete:        (id)           => api.delete(`/portfolios/${id}`),
  addProject:    (id, pid)      => api.post(`/portfolios/${id}/projects`, { project_id: pid }),
  removeProject: (id, pid)      => api.delete(`/portfolios/${id}/projects/${pid}`),
}

// ── Performance Reviews ───────────────────────────────────────────────────────
export const performanceApi = {
  cycles:        ()             => api.get('/performance/cycles'),
  myReviews:     ()             => api.get('/performance/my-reviews'),
  cycleReviews:  (id)           => api.get(`/performance/cycles/${id}/reviews`),
  createCycle:   (data)         => api.post('/performance/cycles', data),
  activateCycle: (id)           => api.post(`/performance/cycles/${id}/activate`),
  closeCycle:    (id)           => api.post(`/performance/cycles/${id}/close`),
  updateReview:  (id, data)     => api.patch(`/performance/reviews/${id}`, data),
  submitReview:  (id)           => api.post(`/performance/reviews/${id}/submit`),
}

// ── Capacity Planning ─────────────────────────────────────────────────────────
export const capacityApi = {
  board:       (params)         => api.get('/capacity/board', { params }),
  createPlan:  (data)           => api.post('/capacity/plans', data),
  updatePlan:  (id, data)       => api.patch(`/capacity/plans/${id}`, data),
  deletePlan:  (id)             => api.delete(`/capacity/plans/${id}`),
}

// ── Profitability ─────────────────────────────────────────────────────────────
export const profitabilityApi = {
  get:             (projectId)          => api.get(`/profitability/${projectId}`),
  summary:         (params)             => api.get('/profitability/summary', { params }),
  createMilestone: (projectId, data)    => api.post(`/profitability/${projectId}/milestones`, data),
  updateMilestone: (projectId, id, data)=> api.patch(`/profitability/${projectId}/milestones/${id}`, data),
  deleteMilestone: (projectId, id)      => api.delete(`/profitability/${projectId}/milestones/${id}`),
}

// ── BI Forecasting ────────────────────────────────────────────────────────────
export const biForecastingApi = {
  getMetrics:     ()                   => api.get('/bi/forecasting/metrics'),
  forecast:       (metric, params)     => api.get(`/bi/forecasting/${metric}`, { params }),
  multiForecast:  (data)               => api.post('/bi/forecasting/multi', data),
}

// ── BI Anomaly / Churn ────────────────────────────────────────────────────────
export const biAnomalyApi = {
  getInfo:        ()                   => api.get('/bi/anomaly/info'),
  detect:         (data)               => api.post('/bi/anomaly/detect', data),
  predictChurn:   (data)               => api.post('/bi/anomaly/churn', data),
}

// ── BI GDPR ───────────────────────────────────────────────────────────────────
export const biGdprApi = {
  recordConsent:  (data)               => api.post('/bi/gdpr/consent', data),
  getConsent:     (params)             => api.get('/bi/gdpr/consent', { params }),
  createDsr:      (data)               => api.post('/bi/gdpr/dsr', data),
  listDsr:        (params)             => api.get('/bi/gdpr/dsr', { params }),
  resolveDsr:     (id, data)           => api.patch(`/bi/gdpr/dsr/${id}/resolve`, data),
  setFieldMask:   (data)               => api.post('/bi/gdpr/field-masks', data),
  getFieldMasks:  ()                   => api.get('/bi/gdpr/field-masks'),
}

// ── BI Dashboard Collaboration ────────────────────────────────────────────────
export const biDashboardCollabApi = {
  addComment:     (data)               => api.post('/bi/collab/comments', data),
  listComments:   (params)             => api.get('/bi/collab/comments', { params }),
  resolveComment: (id)                 => api.patch(`/bi/collab/comments/${id}/resolve`),
  saveView:       (data)               => api.post('/bi/collab/views', data),
  listViews:      (params)             => api.get('/bi/collab/views', { params }),
  addReaction:    (data)               => api.post('/bi/collab/reactions', data),
}

// ── BI Query Builder ──────────────────────────────────────────────────────────
export const biQueryBuilderApi = {
  getSchema:      (params)             => api.get('/bi/query-builder/schema', { params }),
  saveQuery:      (data)               => api.post('/bi/query-builder/queries', data),
  listQueries:    ()                   => api.get('/bi/query-builder/queries'),
  executeQuery:   (id)                 => api.post(`/bi/query-builder/queries/${id}/execute`),
  deleteQuery:    (id)                 => api.delete(`/bi/query-builder/queries/${id}`),
}

// ── BI Conditional Delivery ───────────────────────────────────────────────────
export const biConditionalDeliveryApi = {
  createRule:     (data)               => api.post('/bi/delivery/rules', data),
  listRules:      ()                   => api.get('/bi/delivery/rules'),
  updateRule:     (id, data)           => api.patch(`/bi/delivery/rules/${id}`, data),
  deleteRule:     (id)                 => api.delete(`/bi/delivery/rules/${id}`),
  evaluate:       (id)                 => api.post(`/bi/delivery/rules/${id}/evaluate`),
}

// ── BI ETL Connectors ─────────────────────────────────────────────────────────
export const biEtlApi = {
  listConnectors: ()                   => api.get('/bi/etl/connectors'),
  getConnector:   (id)                 => api.get(`/bi/etl/connectors/${id}`),
  triggerSync:    (id, data)           => api.post(`/bi/etl/connectors/${id}/sync`, data),
  getLog:         (id)                 => api.get(`/bi/etl/connectors/${id}/log`),
  getData:        (id, params)         => api.get(`/bi/etl/data/${id}`, { params }),
}

// ── BI Office 365 ─────────────────────────────────────────────────────────────
export const biO365Api = {
  getConfig:      ()                   => api.get('/bi/o365/config'),
  saveConfig:     (data)               => api.put('/bi/o365/config', data),
  triggerSync:    (data)               => api.post('/bi/o365/sync', data),
  getReport:      (name, params)       => api.get(`/bi/o365/reports/${name}`, { params }),
  getAdoption:    ()                   => api.get('/bi/o365/adoption'),
  getSyncLog:     ()                   => api.get('/bi/o365/sync-log'),
}

// ── Voice Agent (IVR) ─────────────────────────────────────────────────────────
export const voiceAgentApi = {
  getConfig:      ()                   => api.get('/sd/voice/config'),
  updateConfig:   (data)               => api.put('/sd/voice/config', data),
  createSession:  (data)               => api.post('/sd/voice/sessions', data),
  listSessions:   (params)             => api.get('/sd/voice/sessions', { params }),
  getSession:     (id)                 => api.get(`/sd/voice/sessions/${id}`),
  addTurn:        (id, data)           => api.post(`/sd/voice/sessions/${id}/turn`, data),
  closeSession:   (id, data)           => api.post(`/sd/voice/sessions/${id}/close`, data),
  createTicket:   (id)                 => api.post(`/sd/voice/sessions/${id}/ticket`),
}

// ── Incident Assignment ML ────────────────────────────────────────────────────
export const incidentAssignmentApi = {
  recommend:      (ticketId, data)     => api.post(`/sd/incidents/${ticketId}/assign/recommend`, data),
  stats:          ()                   => api.get('/sd/incidents/assign/stats'),
}

// ── Change Rollout ────────────────────────────────────────────────────────────
export const changeRolloutApi = {
  listPlans:      (params)             => api.get('/sd/change/rollout-plans', { params }),
  getPlan:        (id)                 => api.get(`/sd/change/rollout-plans/${id}`),
  createPlan:     (data)               => api.post('/sd/change/rollout-plans', data),
  approvePlan:    (id, data)           => api.post(`/sd/change/rollout-plans/${id}/approve`, data),
  advancePhase:   (id, data)           => api.post(`/sd/change/rollout-plans/${id}/advance`, data),
  rollback:       (id, data)           => api.post(`/sd/change/rollout-plans/${id}/rollback`, data),
  simulate:       (id)                 => api.get(`/sd/change/rollout-plans/${id}/simulate`),
}

// ── CMDB 3D Graph ─────────────────────────────────────────────────────────────
export const cmdb3dApi = {
  getGraph:       (params)             => api.get('/sd/cmdb/3d-graph', { params }),
  blastRadius:    (ciId)               => api.get(`/sd/cmdb/blast-radius/${ciId}`),
  createLink:     (data)               => api.post('/sd/cmdb/asset-links', data),
  listLinks:      (params)             => api.get('/sd/cmdb/asset-links', { params }),
  getImpact:      (assetId)            => api.get(`/sd/cmdb/asset-impact/${assetId}`),
}

// ── WebSocket Ticket ──────────────────────────────────────────────────────────
export const wsApi = {
  ticket: () => api.get('/ws/ticket'),
}

// ── Sprint (project-scoped) ───────────────────────────────────────────────────
export const projectSprintsApi = {
  list:          (projectId)                    => api.get(`/sprints/${projectId}/sprints`),
  create:        (projectId, data)              => api.post(`/sprints/${projectId}/sprints`, data),
  update:        (projectId, id, data)          => api.patch(`/sprints/${projectId}/sprints/${id}`, data),
  start:         (projectId, id)                => api.post(`/sprints/${projectId}/sprints/${id}/start`),
  close:         (projectId, id)                => api.post(`/sprints/${projectId}/sprints/${id}/close`),
  burndown:      (projectId, id)                => api.get(`/sprints/${projectId}/sprints/${id}/burndown`),
  backlog:       (projectId)                    => api.get(`/sprints/${projectId}/backlog`),
  velocity:      (projectId)                    => api.get(`/sprints/${projectId}/velocity`),
  addTasks:      (projectId, sprintId, taskIds) => api.post(`/sprints/${projectId}/sprints/${sprintId}/tasks`, { task_ids: taskIds }),
  removeTask:    (projectId, sprintId, taskId)  => api.delete(`/sprints/${projectId}/sprints/${sprintId}/tasks/${taskId}`),
  retrospective: (projectId, sprintId)          => api.get(`/projects/${projectId}/sprints/${sprintId}/retrospective`),
}

// ── Semantic ──────────────────────────────────────────────────────────────────
export const semanticApi = {
  suggestTask:    (data) => api.post('/semantic/suggest/task', data),
  estimateEffort: (data) => api.post('/semantic/estimate/effort', data),
}

// ── GRC ───────────────────────────────────────────────────────────────────────
export const grcApi = {
  permissions:      ()                           => api.get('/grc/permissions'),
  seedPermissions:  ()                           => api.post('/grc/permissions/seed'),
  updatePermission: (role, module, action, data) => api.patch(`/grc/permissions/${role}/${module}/${action}`, data),
  sodRules:         ()                           => api.get('/grc/sod-rules'),
  createSodRule:    (data)                       => api.post('/grc/sod-rules', data),
  updateSodRule:    (id, data)                   => api.patch(`/grc/sod-rules/${id}`, data),
  deleteSodRule:    (id)                         => api.delete(`/grc/sod-rules/${id}`),
  sodCheck:         ()                           => api.get('/grc/sod-check'),
  violations:       (params)                     => api.get('/grc/violations', { params }),
  resolveViolation: (id, data)                   => api.patch(`/grc/violations/${id}/resolve`, data),
  auditLog:         (params)                     => api.get('/grc/audit-log', { params }),
}

// ── Automations ───────────────────────────────────────────────────────────────
export const automationsApi = {
  list:       ()         => api.get('/automations'),
  templates:  ()         => api.get('/automations/templates/list'),
  create:     (data)     => api.post('/automations', data),
  update:     (id, data) => api.patch(`/automations/${id}`, data),
  delete:     (id)       => api.delete(`/automations/${id}`),
  test:       (id)       => api.post(`/automations/${id}/test`),
  executions: (id)       => api.get(`/automations/${id}/executions`),
}

export const autoWorkflowsApi = {
  list:   ()             => api.get('/automation-workflows'),
  update: (id, data)     => api.patch(`/automation-workflows/${id}`, data),
  delete: (id)           => api.delete(`/automation-workflows/${id}`),
}

export const workflowsLegacyApi = {
  list:   ()         => api.get('/workflows'),
  create: (data)     => api.post('/workflows', data),
  update: (id, data) => api.patch(`/workflows/${id}`, data),
}

// ── Scheduled Reports ─────────────────────────────────────────────────────────
export const scheduledReportsApi = {
  list:   ()         => api.get('/scheduled-reports'),
  create: (data)     => api.post('/scheduled-reports', data),
  delete: (id)       => api.delete(`/scheduled-reports/${id}`),
  run:    (id)       => api.post(`/scheduled-reports/${id}/run`),
  toggle: (id, data) => api.patch(`/scheduled-reports/${id}`, data),
}

// ── AI Providers ──────────────────────────────────────────────────────────────
export const aiProvidersApi = {
  list:        ()         => api.get('/ai-providers'),
  catalog:     ()         => api.get('/ai-providers/catalog'),
  stats:       ()         => api.get('/ai-providers/stats'),
  diagnostics: ()         => api.get('/ai-providers/diagnostics'),
  create:      (data)     => api.post('/ai-providers', data),
  update:      (id, data) => api.patch(`/ai-providers/${id}`, data),
  delete:      (id)       => api.delete(`/ai-providers/${id}`),
  test:        (id)       => api.post(`/ai-providers/${id}/test`),
  syncModels:  (id)       => api.post(`/ai-providers/${id}/sync-models`),
  setDefault:  (id)       => api.post(`/ai-providers/${id}/set-default`),
  syncAll:     ()         => api.post('/ai-providers/sync-models/all'),
}

// ── Service Desk Config ───────────────────────────────────────────────────────
export const sdCatalogApi = {
  get:            ()         => api.get('/sd/catalog'),
  createCategory: (data)     => api.post('/sd/catalog/categories', data),
  updateCategory: (id, data) => api.patch(`/sd/catalog/categories/${id}`, data),
  deleteCategory: (id)       => api.delete(`/sd/catalog/categories/${id}`),
  createService:  (data)     => api.post('/sd/catalog/services', data),
  updateService:  (id, data) => api.patch(`/sd/catalog/services/${id}`, data),
  deleteService:  (id)       => api.delete(`/sd/catalog/services/${id}`),
}

export const sdSlaPoliciesApi = {
  list:   ()         => api.get('/sd/sla-policies'),
  create: (data)     => api.post('/sd/sla-policies', data),
  update: (id, data) => api.patch(`/sd/sla-policies/${id}`, data),
  delete: (id)       => api.delete(`/sd/sla-policies/${id}`),
}

export const sdGroupsApi = {
  list:         ()         => api.get('/sd/groups'),
  create:       (data)     => api.post('/sd/groups', data),
  update:       (id, data) => api.patch(`/sd/groups/${id}`, data),
  delete:       (id)       => api.delete(`/sd/groups/${id}`),
  addMember:    (gid, uid) => api.post(`/sd/groups/${gid}/members/${uid}`),
  removeMember: (gid, uid) => api.delete(`/sd/groups/${gid}/members/${uid}`),
}

export const sdTemplatesApi = {
  list:   ()         => api.get('/sd/ticket-templates'),
  create: (data)     => api.post('/sd/ticket-templates', data),
  update: (id, data) => api.patch(`/sd/ticket-templates/${id}`, data),
  delete: (id)       => api.delete(`/sd/ticket-templates/${id}`),
}

export const sdCannedApi = {
  list:   (params)   => api.get('/sd/canned-responses', { params }),
  create: (data)     => api.post('/sd/canned-responses', data),
  update: (id, data) => api.patch(`/sd/canned-responses/${id}`, data),
  delete: (id)       => api.delete(`/sd/canned-responses/${id}`),
}

export const sdAnnouncementsApi = {
  list:   ()     => api.get('/sd/announcements'),
  create: (data) => api.post('/sd/announcements', data),
  delete: (id)   => api.delete(`/sd/announcements/${id}`),
}

export const sdRoutingApi = {
  list:                ()         => api.get('/sd/routing-rules'),
  create:              (data)     => api.post('/sd/routing-rules', data),
  update:              (id, data) => api.patch(`/sd/routing-rules/${id}`, data),
  delete:              (id)       => api.delete(`/sd/routing-rules/${id}`),
  queue:               (params)   => api.get('/sd/tickets/my-queue', { params }),
  tickets:             (params)   => api.get('/sd/tickets', { params }),
  majorIncidents:      ()         => api.get('/sd/major-incidents'),
  createMajorIncident: (data)     => api.post('/sd/major-incidents', data),
}

export const sdKbApi = {
  list:        (params)   => api.get('/sd/kb', { params }),
  create:      (data)     => api.post('/sd/kb', data),
  update:      (id, data) => api.patch(`/sd/kb/${id}`, data),
  delete:      (id)       => api.delete(`/sd/kb/${id}`),
  knownErrors: ()         => api.get('/sd/known-errors'),
}

// ── Enterprise ────────────────────────────────────────────────────────────────
export const webhooksApi = {
  list:   ()         => api.get('/webhooks'),
  create: (data)     => api.post('/webhooks', data),
  delete: (id)       => api.delete(`/webhooks/${id}`),
  logs:   (id)       => api.get(`/webhooks/${id}/logs`),
}

export const gdprApi = {
  list:    ()     => api.get('/gdpr/requests'),
  create:  (data) => api.post('/gdpr/requests', data),
  process: (id)   => api.post(`/gdpr/requests/${id}/process`),
}

export const emailApi = {
  catalog:        ()     => api.get('/email/templates'),
  logs:           ()     => api.get('/email/logs'),
  send:           (data) => api.post('/email/send', data),
  createTemplate: (data) => api.post('/email/templates', data),
}

export const oauthIntegrationsApi = {
  list:   ()             => api.get('/oauth-integrations'),
  create: (data)         => api.post('/oauth-integrations', data),
  delete: (id)           => api.delete(`/oauth-integrations/${id}`),
  sync:   (id, data)     => api.post(`/oauth-integrations/${id}/sync`, data),
}

export const enterpriseApi = {
  auditLog:  (params) => api.get('/enterprise/audit-log', { params }),
  ssoList:   ()       => api.get('/enterprise/sso'),
  ssoCreate: (data)   => api.post('/enterprise/sso', data),
  ssoDelete: (id)     => api.delete(`/enterprise/sso/${id}`),
  ssoTest:   (id)     => api.post(`/enterprise/sso/${id}/test`),
}

export const integrationsHubApi = {
  testSlack:  (data) => api.post('/integrations-hub/slack/test', data),
  testTeams:  (data) => api.post('/integrations-hub/teams/test', data),
  testJira:   (data) => api.post('/integrations-hub/jira/test', data),
}

export const apiKeysApi = {
  list:   ()         => api.get('/api-keys'),
  create: (data)     => api.post('/api-keys', data),
  delete: (id)       => api.delete(`/api-keys/${id}`),
}

// ── Client Portal ─────────────────────────────────────────────────────────────
export const portalApi = {
  clients:              (params)          => api.get('/portal/clients', { params }),
  createClient:         (data)            => api.post('/portal/clients', data),
  updateClient:         (id, data)        => api.patch(`/portal/clients/${id}`, data),
  deleteClient:         (id)              => api.delete(`/portal/clients/${id}`),
  uat:                  (params)          => api.get('/portal/uat/team', { params }),
  createUat:            (projectId, data) => api.post(`/portal/uat/${projectId}`, data),
  addTestCase:          (id, data)        => api.post(`/portal/uat/${id}/test-cases`, data),
  updateUatStatus:      (id, params)      => api.patch(`/portal/uat/issues/${id}`, null, { params }),
  featureRequests:      (params)          => api.get('/portal/feature-requests/team', { params }),
  respondFeatureRequest:(id, data)        => api.post(`/portal/feature-requests/${id}/respond`, data),
  documents:            (params)          => api.get('/portal/documents/team', { params }),
  createDocument:       (projectId, data) => api.post('/portal/documents', data, { params: { project_id: projectId } }),
  stats:                (projectId)       => api.get(`/portal/stats/${projectId}`),
}

// ── Client Extensions ─────────────────────────────────────────────────────────
export const clientExtApi = {
  projects:           (cid)       => api.get(`/clients/${cid}/projects`),
  availableProjects:  (cid)       => api.get(`/clients/${cid}/projects/available`),
  linkProject:        (cid, pid)  => api.post(`/clients/${cid}/projects/${pid}/link`),
  unlinkProject:      (cid, pid)  => api.delete(`/clients/${cid}/projects/${pid}/link`),
  contacts:           (cid)       => api.get(`/clients/${cid}/contacts`),
  createContact:      (cid, data) => api.post(`/clients/${cid}/contacts`, data),
  deleteContact:      (cid, id)   => api.delete(`/clients/${cid}/contacts/${id}`),
  licenses:           (cid)       => api.get(`/clients/${cid}/licenses`),
  linkLicense:        (cid, data) => api.post(`/clients/${cid}/licenses`, data),
  unlinkLicense:      (cid, id)   => api.delete(`/clients/${cid}/licenses/${id}`),
  contracts:          (cid)       => api.get(`/clients/${cid}/contracts`),
  linkContract:       (cid, data) => api.post(`/clients/${cid}/contracts`, data),
  unlinkContract:     (cid, id)   => api.delete(`/clients/${cid}/contracts/${id}`),
  portalConfig:       (cid)       => api.get(`/clients/${cid}/portal-config`),
  updatePortalConfig: (cid, data) => api.patch(`/clients/${cid}/portal-config`, data),
}

/** Normalise a Pydantic v2 / FastAPI error detail to a plain string.
 *  detail can be an array of {type,loc,msg,input,url} objects or a plain string. */
export function apiErrorMsg(e, fallback = 'Error') {
  const raw = e?.response?.data?.detail
  if (Array.isArray(raw)) return raw.map(d => d.msg).join(', ')
  return raw || e?.message || fallback
}
