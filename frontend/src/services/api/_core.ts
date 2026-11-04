import axios, { type AxiosRequestConfig } from 'axios'

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) || '/api/v1'

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,  // send httpOnly cookies on every request
  timeout: 30000,
})

// Helper: read a non-httpOnly cookie by name (used for CSRF double-submit token).
function _readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/[.$?*|{}()[\]\\/+^]/g, '\\$&') + '=([^;]*)'))
  return m ? decodeURIComponent(m[1]) : null
}

// Strip Content-Type for FormData so the browser sets the correct multipart boundary.
// Authentication is handled exclusively via httpOnly cookies (withCredentials: true).
// No tokens are read from or written to localStorage to prevent XSS exposure.
// Audit #C1: also echo the CSRF token from the readable `csrf_token` cookie into
// the X-CSRF-Token header on unsafe methods (no-op if the cookie is absent —
// preparation for backend-side CSRF_DOUBLE_SUBMIT=1).
api.interceptors.request.use((config) => {
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  const method = (config.method || 'get').toUpperCase()
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
    const csrf = _readCookie('csrf_token')
    if (csrf) {
      config.headers = (config.headers || {}) as typeof config.headers
      ;(config.headers as Record<string, string>)['X-CSRF-Token'] = csrf
    }
  }
  return config
})

// Singleton refresh promise — ensures only one /auth/refresh call is in flight at a time.
// All concurrent 401s wait for the same promise instead of each firing their own refresh,
// which would invalidate the rotating refresh token for all but the first caller.
let _refreshPromise: Promise<unknown> | null = null

// APIListResponse compatibility — audit #67 migrated many list endpoints to
// `{ items: T[], meta: { total, page, page_size, has_more } }`. Consumers that
// iterate `response.data` directly would crash with "X is not iterable". This
// interceptor detects the exact APIListResponse shape and unwraps it to the
// items array, exposing the meta on `response.meta` for callers that need
// pagination. Endpoints that return bare arrays or single objects are unchanged.
api.interceptors.response.use((res) => {
  const body = res?.data
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const keys = Object.keys(body)
    // Envelope de LISTA (APIListResponse): { items, meta } → expone el array en res.data
    // y la meta de paginación en res.meta.
    if (
      Array.isArray(body.items) &&
      body.meta && typeof body.meta === 'object' &&
      keys.length === 2
    ) {
      ;(res as { meta?: unknown }).meta = body.meta
      res.data = body.items
    }
    // Envelope de OBJETO (APIResponse): exactamente { data, meta } → expone el payload en
    // res.data (que es lo que el frontend espera de forma universal) y la meta en res.meta.
    // Guard estricto (2 claves exactas 'data'+'meta') para no tocar payloads que casualmente
    // tengan una clave 'data' (p.ej. {data, weeks}).
    else if (keys.length === 2 && 'data' in body && 'meta' in body) {
      ;(res as { meta?: unknown }).meta = (body as { meta?: unknown }).meta
      res.data = (body as { data?: unknown }).data
    }
  }
  return res
})

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
  get:             (id: any)       => api.get(`/rate-cards/${id}`),
  create:          (d: unknown)        => api.post('/rate-cards', d),
  update:          (id: any, d: unknown)    => api.patch(`/rate-cards/${id}`, d),
  delete:          (id: any)       => api.delete(`/rate-cards/${id}`),
  duplicate:       (id: any, d: unknown)    => api.post(`/rate-cards/${id}/duplicate`, d),
  addEntry:        (id: any, d: unknown)    => api.post(`/rate-cards/${id}/entries`, d),
  updateEntry:     (id: any,eid: any,d: unknown) => api.patch(`/rate-cards/${id}/entries/${eid}`, d),
  deleteEntry:     (id: any,eid: any)   => api.delete(`/rate-cards/${id}/entries/${eid}`),
  addOverride:     (id: any, d: unknown)    => api.post(`/rate-cards/${id}/overrides`, d),
  deleteOverride:  (id: any,oid: any)   => api.delete(`/rate-cards/${id}/overrides/${oid}`),
  effectiveRate:   (params?: any)   => api.get('/rate-cards/effective', { params }),
}

// ── Milestones (SOW flow) ─────────────────────────────────────────────────────
export const milestonesApi = {
  list:            (projectId: any) => api.get(`/milestones/project/${projectId}`),
  create:          (pid: any, d: unknown)    => api.post(`/milestones/project/${pid}`, d),
  update:          (id: any, d: unknown)     => api.patch(`/milestones/${id}`, d),
  delete:          (id: any)        => api.delete(`/milestones/${id}`),
  complete:        (id: any)        => api.post(`/milestones/${id}/complete`),
  uncomplete:      (id: any)        => api.post(`/milestones/${id}/uncomplete`),
  requestApproval: (id: any, d: unknown)     => api.post(`/milestones/${id}/request-approval`, d || {}),
  approve:         (id: any, d: unknown)     => api.post(`/milestones/${id}/approve`, d),
  generateInvoice: (id: any)        => api.post(`/milestones/${id}/generate-invoice`),
  dashboard:       ()          => api.get('/milestones/dashboard/pending'),
}

// ── Resource Forecast ─────────────────────────────────────────────────────────
export const forecastApi = {
  heatmap:      (params?: any) => api.get('/resource-forecast/weeks',        { params }),
  userDetail:   (uid: any, p: any) => api.get(`/resource-forecast/users/${uid}`, { params: p }),
  availability: (params?: any) => api.get('/resource-forecast/availability',  { params }),
  summary:      (params?: any) => api.get('/resource-forecast/summary',       { params }),
}

// ── Approvals ─────────────────────────────────────────────────────────────────
export const approvalsApi = {
  listWorkflows:     (params?: any)      => api.get('/approvals/workflows', { params }),
  listTemplates:     ()            => api.get('/approvals/workflow-templates'),
  getWorkflow:       (id: any)          => api.get(`/approvals/workflows/${id}`),
  createWorkflow:    (d: unknown)           => api.post('/approvals/workflows', d),
  createFromTemplate:(d: unknown)           => api.post('/approvals/workflows/from-template', d),
  updateWorkflow:    (id: any, d: unknown)       => api.patch(`/approvals/workflows/${id}`, d),
  validateWorkflow:  (id: any)          => api.get(`/approvals/workflows/${id}/validate`),
  publishWorkflow:   (id: any)          => api.post(`/approvals/workflows/${id}/publish`),
  cloneVersion:      (id: any, d: unknown)       => api.post(`/approvals/workflows/${id}/clone-version`, d || {}),
  deleteWorkflow:    (id: any)          => api.delete(`/approvals/workflows/${id}`),
  addStep:           (wid: any, d: unknown)      => api.post(`/approvals/workflows/${wid}/steps`, d),
  updateStep:        (wid: any, sid: any, d: unknown) => api.patch(`/approvals/workflows/${wid}/steps/${sid}`, d),
  deleteStep:        (wid: any, sid: any)    => api.delete(`/approvals/workflows/${wid}/steps/${sid}`),
  simulate:          (d: unknown)           => api.post('/approvals/simulate', d),
  bottlenecks:       (params?: any)      => api.get('/approvals/analytics/bottlenecks', { params }),
  approverLoad:      (params?: any)      => api.get('/approvals/analytics/approver-load', { params }),
  listRequests:      (params?: any)      => api.get('/approvals/requests', { params }),
  pendingMyAction:   ()            => api.get('/approvals/requests/pending-my-action'),
  createRequest:     (d: unknown)           => api.post('/approvals/requests', d),
  decide:            (id: any, d: unknown)       => api.post(`/approvals/requests/${id}/decide`, d),
  cancel:            (id: any)          => api.post(`/approvals/requests/${id}/cancel`),
  stats:             ()            => api.get('/approvals/stats'),
  // Groups
  listGroups:        ()            => api.get('/approvals/groups'),
  getGroup:          (id: any)          => api.get(`/approvals/groups/${id}`),
  createGroup:       (d: unknown)           => api.post('/approvals/groups', d),
  updateGroup:       (id: any, d: unknown)       => api.patch(`/approvals/groups/${id}`, d),
  deleteGroup:       (id: any)          => api.delete(`/approvals/groups/${id}`),
}

export const uatApi = {
  list:   (projectId: any, params?: any) => api.get(`/projects/${projectId}/uat`, { params }),
  create: (projectId: any, data: unknown)   => api.post(`/projects/${projectId}/uat`, data),
  update: (projectId: any, id: any, d: unknown)  => api.patch(`/projects/${projectId}/uat/${id}`, d),
  remove: (projectId: any, id: any)     => api.delete(`/projects/${projectId}/uat/${id}`),
  export: (projectId: any)         => api.get(`/projects/${projectId}/uat/export`),
}

export default api

// ── Response shape helpers ────────────────────────────────────────────────────
/**
 * Normaliza la respuesta de un endpoint de listado a un array garantizado.
 * Soporta tres shapes que el backend usa indistintamente:
 *   1) array crudo: `[a, b, c]`
 *   2) paginado: `{ items: [...], count?, total? }`
 *   3) clave alternativa: `{ rows | results | data | tickets | sessions: [...] }`
 *
 * Uso:
 *   unwrapList(response)                  → busca array en data, items, rows...
 *   unwrapList(response, 'tickets')       → fuerza la clave 'tickets' como prioridad
 *
 * Nunca devuelve null/undefined — siempre array (vacío si no hay match).
 */
export function unwrapList(response: unknown, key?: string): unknown[] {
  const data = (response as { data?: unknown } | null | undefined)?.data ?? response
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>
    if (key && Array.isArray(obj[key])) return obj[key] as unknown[]
    for (const k of ['items', 'results', 'rows', 'data', 'list']) {
      if (Array.isArray(obj[k])) return obj[k] as unknown[]
    }
  }
  return []
}

/**
 * Variante "raw data" — devuelve el objeto data si no es array, o el primer
 * array que encuentre. Útil cuando el endpoint puede devolver objeto o array
 * y necesitas también los metadatos paginated (`{items, count}` mantiene `count`).
 */
export function unwrapData(response: { data?: unknown } | null | undefined) {
  return response?.data ?? response ?? null
}

// ── Typed API helpers ─────────────────────────────────────────────────────────

export const authApi = {
  login:          (credentials: any) => api.post('/auth/login', credentials),
  forgotPassword: (payload: unknown)     => api.post('/auth/password/forgot', payload),
  resetPassword:  (payload: unknown)     => api.post('/auth/password/reset', payload),
  me:             ()            => api.get('/auth/me'),
  changePassword: (data: unknown)        => api.post('/auth/change-password', data),
}

export const usersApi = {
  list:           (params?: any) => api.get('/users', { params }),
  withRates:      () => api.get('/users/with-rates'),
  load:           (params?: any) => api.get('/users/load', { params }),
  get:            (id: any) => api.get(`/users/${id}`),
  create:         (data: unknown) => api.post('/users', data),
  update:         (id: any, data: unknown) => api.patch(`/users/${id}`, data),
  deactivate:     (id: any) => api.delete(`/users/${id}`),
  deletePermanent:(id: any) => api.delete(`/users/${id}/permanent`),
  productivity:   (id: any, params?: any) => api.get(`/users/${id}/productivity`, { params }),
  orgChart:       () => api.get('/users/org-chart'),
  updateManager:  (id: any, data: unknown) => api.patch(`/users/${id}/manager`, data),
  updateMe:       (data: unknown) => api.patch('/users/me', data),
  approvalChain:  (userId: any)   => api.get(`/users/${userId}/approval-chain`),
  myApprovalChain: ()        => api.get('/users/me/approval-chain'),
}

export const projectsApi = {
  list:              (params?: any)    => api.get('/projects', { params }),
  get:               (id: any)       => api.get(`/projects/${id}`),
  create:            (data: unknown)     => api.post('/projects', data),
  update:            (id: any, data: unknown) => api.patch(`/projects/${id}`, data),
  delete:            (id: any)       => api.delete(`/projects/${id}`),
  team:              (id: any)       => api.get(`/projects/${id}/team`),
  addPhase:          (id: any, data: unknown) => api.post(`/projects/${id}/phases`, data),
  members:           (id: any)       => api.get(`/projects/${id}/members`),
  addMember:         (id: any, data: unknown) => api.post(`/projects/${id}/members`, data),
  removeMember:      (id: any, memberId: any) => api.delete(`/projects/${id}/members/${memberId}`),
  milestones:        (params?: any)   => api.get('/projects/milestones', { params }),
  changelog:         (id: any, params?: any) => api.get(`/projects/${id}/changelog`, { params }),
  createChangelog:   (id: any, data: unknown) => api.post(`/projects/${id}/changelog`, data),
  generateChangelog: (id: any, data: unknown) => api.post(`/projects/${id}/changelog/generate`, data),
  deleteChangelog:   (id: any, entryId: any) => api.delete(`/projects/${id}/changelog/${entryId}`),
  raci:              (id: any)       => api.get(`/projects/${id}/raci`),
  updateRaci:        (id: any, data: unknown) => api.put(`/projects/${id}/raci`, data),
  deleteRaci:        (id: any, entryId: any) => api.delete(`/projects/${id}/raci/${entryId}`),
  evm:               (id: any)       => api.get(`/projects/${id}/evm`),
  evmPortfolio:      ()         => api.get('/projects/evm/portfolio'),
}

export const aiCopilotApi = {
  ganttSuggestions:     (projectId: any) => api.get(`/ai/suggestions/gantt/${projectId}`),
  timesheetSuggestions: (userId: any)    => api.get(`/ai/suggestions/timesheets/${userId}`),
}

export const tasksApi = {
  list:        (params?: any)    => api.get('/tasks', { params }),
  kanban:      (projectId: any) => api.get(`/tasks/kanban/${projectId}`),
  get:         (id: any)        => api.get(`/tasks/${id}`),
  create:      (data: unknown)      => api.post('/tasks', data),
  update:      (id: any, data: unknown)  => api.patch(`/tasks/${id}`, data),
  delete:      (id: any)        => api.delete(`/tasks/${id}`),
  comment:     (id: any, data: unknown)  => api.post(`/tasks/${id}/comments`, data),
  bulkUpdate:  (data: unknown)      => api.post('/tasks/bulk-update', data),
  movementLog: (id: any)        => api.get(`/tasks/${id}/movement-log`),
}

export const imputationsApi = {
  list:           (params?: any) => api.get('/imputations', { params }),
  myWeek:         (params?: any) => api.get('/imputations/my/week', { params }),
  create:         (data: unknown) => api.post('/imputations', data),
  update:         (id: any, data: unknown) => api.patch(`/imputations/${id}`, data),
  delete:         (id: any) => api.delete(`/imputations/${id}`),
  approve:        (id: any) => api.post(`/imputations/${id}/approve`),
  reject:         (id: any) => api.post(`/imputations/${id}/reject`),
  timerCurrent:   () => api.get('/imputations/timer/current'),
  timerStart:     (data: unknown) => api.post('/imputations/timer/start', data),
  timerPause:     () => api.post('/imputations/timer/pause'),
  timerResume:    () => api.post('/imputations/timer/resume'),
  timerCancel:    () => api.post('/imputations/timer/cancel'),
  timerStop:      (data: unknown) => api.post('/imputations/timer/stop', data),
}

export const analyticsApi = {
  query:        (metricId: any, params?: any) => api.get(`/analytics/query/${metricId}`, { params }),
  filterOptions: ()                => api.get('/analytics/filters/options'),
  hoursWeek:    (params?: any)           => api.get('/analytics/hours_by_week', { params }),
  utilization:  (params?: any)           => api.get('/analytics/utilization/advanced', { params }),
  metricBreaches: (params?: any)         => api.get('/analytics/alerts/metric-breaches', { params }),
  // BI / OLAP
  narrative:       (params?: any)        => api.get('/analytics/narrative', { params }),
  ask:             (question: any)      => api.post('/analytics/ask', { question }),
  olapKpis:        (params?: any)        => api.get('/analytics/olap/kpis', { params }),
  olapFunnel:      ()              => api.get('/analytics/olap/pipeline-funnel'),
  olapPortfolio:   ()              => api.get('/analytics/olap/portfolio-health'),
  olapMargin:      (months: any)        => api.get('/analytics/olap/margin-evolution', { params: { months } }),
  olapUtilization: ()              => api.get('/analytics/olap/utilization'),
  catalogue:       ()              => api.get('/analytics/catalogue'),
}

export const biCollaborationApi = {
  listComments:   (params?: any)             => api.get('/bi/collaboration/comments', { params }),
  createComment:  (payload: unknown)            => api.post('/bi/collaboration/comments', payload),
  resolveComment: (commentId: any)          => api.patch(`/bi/collaboration/comments/${commentId}/resolve`),
  listSharedViews: (params?: any)            => api.get('/bi/collaboration/shared-views', { params }),
  createSharedView: (payload: unknown)          => api.post('/bi/collaboration/shared-views', payload),
  patchSharedView: (viewId: any, payload: unknown)   => api.patch(`/bi/collaboration/shared-views/${viewId}`, payload),
  governanceOverview: ()               => api.get('/bi/governance/overview'),
  governanceRules: ()                  => api.get('/bi/governance/rules'),
  updateGovernanceRules: (payload: unknown)     => api.patch('/bi/governance/rules', payload),
  runGovernanceChecks: ()              => api.post('/bi/governance/run-checks'),
  lastGovernanceRun: ()                => api.get('/bi/governance/last-run'),
  // Dashboard shares
  listDashboardShares:    (key: any)              => api.get(`/bi/collaboration/dashboards/${key}/shares`),
  shareDashboard:         (key: any, data: unknown)        => api.post(`/bi/collaboration/dashboards/${key}/shares`, data),
  revokeShare:            (key: any, shareId: any)     => api.delete(`/bi/collaboration/dashboards/${key}/shares/${shareId}`),
  // Dashboard versions
  listDashboardVersions:  (key: any)              => api.get(`/bi/collaboration/dashboards/${key}/versions`),
  restoreDashboardVersion:(key: any, versionId: any)   => api.post(`/bi/collaboration/dashboards/${key}/versions/${versionId}/restore`),
  // Notifications
  listNotifications:      (params?: any)           => api.get('/bi/collaboration/notifications', { params }),
  patchNotification:      (id: any, data: unknown)         => api.patch(`/bi/collaboration/notifications/${id}`, data),
}

export const biIntelligenceApi = {
  revenueForecast: (params?: any)            => api.get('/bi/intelligence/ml/forecast/revenue', { params }),
  revenueAnomalies: (params?: any)           => api.get('/bi/intelligence/ml/anomalies/revenue', { params }),
  listConnectors: ()                   => api.get('/bi/intelligence/connectors'),
  patchConnector: (name: any, payload: unknown)      => api.patch(`/bi/intelligence/connectors/${name}`, payload),
  syncConnector: (name: any)                => api.post(`/bi/intelligence/connectors/${name}/sync`),
  reportPresets: ()                    => api.get('/bi/intelligence/reports/presets'),
  previewPreset: (payload: unknown)             => api.post('/bi/intelligence/reports/preview', payload),
  queryBuilderSchema: ()               => api.get('/bi/intelligence/query-builder/schema'),
  queryBuilderPreview: (payload: unknown)       => api.post('/bi/intelligence/query-builder/preview', payload),
  queryBuilderTemplates: ()            => api.get('/bi/intelligence/query-builder/templates'),
  saveQueryBuilderTemplate: (payload: unknown)  => api.post('/bi/intelligence/query-builder/templates', payload),
  deleteQueryBuilderTemplate: (id: any)     => api.delete(`/bi/intelligence/query-builder/templates/${id}`),
  deliveryOverview: ()                 => api.get('/bi/intelligence/delivery/overview'),
  runDeliveryNow: (reportId: any)           => api.post(`/bi/intelligence/delivery/run/${reportId}`),
  realtimeToken: ()                    => api.get('/bi/intelligence/realtime/token'),
}

export const biPlatformApi = {
  sdkManifest: ()                      => api.get('/bi/platform/embed/sdk'),
  embedSettings: ()                    => api.get('/bi/platform/embed/settings'),
  patchEmbedSettings: (payload: unknown)        => api.patch('/bi/platform/embed/settings', payload),
  embedToken: (payload: unknown)                => api.post('/bi/platform/embed/token', payload),
  connectorCatalog: ()                 => api.get('/bi/platform/connectors/catalog'),
  patchCatalogConnector: (name: any, p: any)     => api.patch(`/bi/platform/connectors/catalog/${name}`, p),
  listCustomConnectors: ()             => api.get('/bi/platform/connectors/custom'),
  createCustomConnector: (payload: unknown)     => api.post('/bi/platform/connectors/custom', payload),
  deleteCustomConnector: (id: any)          => api.delete(`/bi/platform/connectors/custom/${id}`),
  testCustomConnector: (id: any)            => api.post(`/bi/platform/connectors/custom/${id}/test`),
  lineage: ()                          => api.get('/bi/platform/governance/lineage'),
  upsertLineageEdge: (payload: unknown)         => api.post('/bi/platform/governance/lineage/edges', payload),
  logAccess: (payload: unknown)                 => api.post('/bi/platform/governance/audit/access', payload),
  createSnapshot: (datasetKey: any, p: any)      => api.post(`/bi/platform/versioning/${datasetKey}/snapshots`, p),
  listSnapshots: (datasetKey: any)          => api.get(`/bi/platform/versioning/${datasetKey}/snapshots`),
  diffSnapshots: (datasetKey: any, fromId: any, toId: any) => api.get(`/bi/platform/versioning/${datasetKey}/diff`, { params: { from_id: fromId, to_id: toId } }),
}

export const biSmartAlertsApi = {
  supportedMetrics: ()                 => api.get('/bi/alerts/supported-metrics'),
  listRules: ()                        => api.get('/bi/alerts/rules'),
  createRule: (payload: unknown)                => api.post('/bi/alerts/rules', payload),
  updateRule: (ruleId: any, payload: unknown)        => api.patch(`/bi/alerts/rules/${ruleId}`, payload),
  deleteRule: (ruleId: any)                 => api.delete(`/bi/alerts/rules/${ruleId}`),
  evaluate: ()                         => api.post('/bi/alerts/evaluate'),
  getHistory: (limit: number = 100)            => api.get('/bi/alerts/history', { params: { limit } }),
  acknowledge: (alertId: any)               => api.post(`/bi/alerts/history/${alertId}/acknowledge`),
  seedDefaults: ()                     => api.post('/bi/alerts/seed-defaults'),
  listCustomMetrics: ()                => api.get('/bi/alerts/custom-metrics'),
  createCustomMetric: (payload: unknown)        => api.post('/bi/alerts/custom-metrics', payload),
  deleteCustomMetric: (key: any)            => api.delete(`/bi/alerts/custom-metrics/${key}`),
}

export const biBookmarksApi = {
  list: ()                             => api.get('/bi/bookmarks'),
  create: (payload: unknown)                    => api.post('/bi/bookmarks', payload),
  get: (id: any)                            => api.get(`/bi/bookmarks/${id}`),
  update: (id: any, payload: unknown)                => api.patch(`/bi/bookmarks/${id}`, payload),
  delete: (id: any)                         => api.delete(`/bi/bookmarks/${id}`),
}

export const biGovernanceAuditApi = {
  // BI Governance — audit trail, data lineage, field sensitivity
  logAccessEvent: (payload: unknown)            => api.post('/bi/governance/audit/access', payload),
  getAccessHistory: (params?: any)           => api.get('/bi/governance/audit/access', { params }),
  listLineage: (target_table: any)          => api.get('/bi/governance/lineage', { params: target_table ? { target_table } : undefined }),
  trackLineage: (payload: unknown)              => api.post('/bi/governance/lineage', payload),
  listFieldSensitivity: (dataset_id: any)   => api.get('/bi/governance/field-sensitivity', { params: dataset_id ? { dataset_id } : undefined }),
  upsertFieldSensitivity: (payload: unknown)    => api.put('/bi/governance/field-sensitivity', payload),
}

export const biReportBuilderV2Api = {
  listPresets: (params?: any)                => api.get('/bi/reports/v2/presets', { params }),
  getPreset: (presetId: any)                => api.get(`/bi/reports/v2/presets/${presetId}`),
  categories: ()                       => api.get('/bi/reports/v2/categories'),
  customize: (presetId: any, payload: unknown)       => api.post(`/bi/reports/v2/presets/${presetId}/customize`, payload),
  resetCustomize: (presetId: any)           => api.delete(`/bi/reports/v2/presets/${presetId}/customize`),
  preview: (presetId: any, limit: number = 50)      => api.get(`/bi/reports/v2/presets/${presetId}/preview`, { params: { limit } }),
  export: (presetId: any, format: string = 'json')  => api.get(`/bi/reports/v2/presets/${presetId}/export`, { params: { format } }),
}

export const dashboardApi = {
  kpis:           () => api.get('/dashboard/kpis'),
  projectsHealth: (params?: any) => api.get('/dashboard/projects-health', { params }),
  resourceLoad:   (params?: any) => api.get('/dashboard/resource-load', { params }),
  profitability:  (params?: any) => api.get('/dashboard/profitability', { params }),
  teamProductivity: (params?: any) => api.get('/dashboard/productivity/team', { params }),
}

export const alertsApi = {
  list:     (params?: any) => api.get('/alerts', { params }),
  run:      () => api.post('/alerts/run'),
  read:     (id: any) => api.patch(`/alerts/${id}/read`),
  resolve:  (id: any) => api.patch(`/alerts/${id}/resolve`),
}

export const integrationsApi = {
  // Auditoria 2026-08 (hallazgo 37): estas dos apuntaban a
  // `POST /integrations/export/...`, rutas que no existen en ningun router, asi
  // que los dos botones de la pantalla de exportaciones devolvian 404. El
  // export de imputaciones si existia con otro verbo y otra ruta; el de
  // proyectos hubo que anadirlo (`/analytics/exports/projects-csv`).
  exportImputations: (params: unknown) => api.get('/analytics/exports/imputations-csv', { params, responseType: 'blob' }),
  exportProjects:    (params: unknown) => api.get('/analytics/exports/projects-csv', { params, responseType: 'blob' }),
  jiraSync:          (projectId: any) => api.post(`/integrations/jira/sync/${projectId}`),
}

export const clientsApi = {
  list:         (params?: any)     => api.get('/clients', { params }),
  get:          (id: any)         => api.get(`/clients/${id}`),
  create:       (data: unknown)       => api.post('/clients', data),
  update:       (id: any, data: unknown)   => api.patch(`/clients/${id}`, data),
  delete:       (id: any)         => api.delete(`/clients/${id}`),
  contacts:     (id: any)         => api.get(`/clients/${id}/contacts`),
  addContact:   (id: any, data: unknown)   => api.post(`/clients/${id}/contacts`, data),
  deleteContact:(id: any, cid: any)    => api.delete(`/clients/${id}/contacts/${cid}`),
  view360:      (id: any)         => api.get(`/clients/${id}/360`),
}

// ── Sprints ───────────────────────────────────────────────────────────────────
export const sprintsApi = {
  list:    (projectId: any, params?: any) => api.get('/sprints', { params: { project_id: projectId, ...params } }),
}

// ── Epics ─────────────────────────────────────────────────────────────────────
export const epicsApi = {
  list:            (projectId: any) => api.get('/epics', { params: { project_id: projectId } }),
  get:             (id: any)        => api.get(`/epics/${id}`),
  create:          (data: unknown)      => api.post('/epics', data),
  createForProject:(projectId: any, data: unknown) => api.post('/epics', data, { params: { project_id: projectId } }),
  update:          (id: any, data: unknown)  => api.patch(`/epics/${id}`, data),
  delete:          (id: any)        => api.delete(`/epics/${id}`),
  // Auditoria 2026-08: llamaba a `/roadmap`, que no existe — y su duplicado
  // correcto, `roadmapByProject`, estaba en la linea de abajo apuntando a
  // `/epics/roadmap`. `EpicsPage` usaba el roto. Los dos son ahora la misma
  // llamada; se conserva `roadmapByProject` para no romper a quien la use.
  roadmap:         (projectId: any) => api.get('/epics/roadmap', { params: { project_id: projectId } }),
  roadmapByProject:(projectId: any) => api.get('/epics/roadmap', { params: { project_id: projectId } }),
  cfd:             (params?: any)    => api.get('/epics/cfd', { params }),
  cfdSnapshot:     (projectId: any) => api.post('/epics/cfd/snapshot', null, { params: { project_id: projectId } }),
  nqlSearch:       (data: unknown)      => api.post('/epics/nql/search', data),
}

// ── Contracts ─────────────────────────────────────────────────────────────────
export const contractsApi = {
  list:                (params?: any)           => api.get('/contracts', { params }),
  get:                 (id: any)               => api.get(`/contracts/${id}`),
  create:              (data: unknown)             => api.post('/contracts', data),
  update:              (id: any, data: unknown)         => api.patch(`/contracts/${id}`, data),
  delete:              (id: any)               => api.delete(`/contracts/${id}`),
  createWorkOrder:     (id: any, data: unknown)         => api.post(`/contracts/${id}/work-orders`, data),
  updateWorkOrderStatus:(id: any, woId: any, status: any)=> api.patch(`/contracts/${id}/work-orders/${woId}/status`, null, { params: { status } }),
}

// ── Expenses ──────────────────────────────────────────────────────────────────
export const expensesApi = {
  list:      (params?: any)    => api.get('/expenses', { params }),
  my:        (params?: any)    => api.get('/expenses/my', { params }),
  pending:   ()          => api.get('/expenses/pending'),
  team:      (params?: any)    => api.get('/expenses/team', { params }),
  create:    (data: unknown)      => api.post('/expenses', data),
  update:    (id: any, data: unknown)  => api.patch(`/expenses/${id}`, data),
  updateMy:  (id: any, data: unknown)  => api.patch(`/expenses/my/${id}`, data),
  review:    (id: any, data: unknown)  => api.post(`/expenses/${id}/review`, data),
  submitMy:  (id: any)        => api.post(`/expenses/my/${id}/submit`),
  recall:    (id: any)        => api.post(`/expenses/my/${id}/recall`),
  reimburse: (id: any)        => api.post(`/expenses/${id}/reimburse`),
  deleteMy:  (id: any)        => api.delete(`/expenses/my/${id}`),
  ocr:       (fd: unknown)        => api.post('/expenses/ocr', fd),
}

// ── Risks ─────────────────────────────────────────────────────────────────────
export const risksApi = {
  list:         (projectId: any, params?: any) => api.get(`/risks/${projectId}`, { params }),
  get:          (projectId: any, riskId: any) => api.get(`/risks/${projectId}/${riskId}`),
  create:       (projectId: any, data: unknown)   => api.post(`/risks/${projectId}`, data),
  update:       (projectId: any, riskId: any, data: unknown) => api.patch(`/risks/${projectId}/${riskId}`, data),
  delete:       (projectId: any, riskId: any) => api.delete(`/risks/${projectId}/${riskId}`),
  portfolioAll: ()                  => api.get('/risks/all/portfolio'),
}

// ── OKRs ─────────────────────────────────────────────────────────────────────
export const okrsApi = {
  list:     (params?: any)      => api.get('/okrs', { params }),
  create:   (data: unknown)        => api.post('/okrs', data),
  update:   (id: any, data: unknown)    => api.patch(`/okrs/${id}`, data),
  delete:   (id: any)          => api.delete(`/okrs/${id}`),
  // El key result se identifica solo: el objetivo no va en la ruta. Auditoria #37.
  updateKR: (krid: any, d: unknown) => api.patch(`/okrs/key-results/${krid}`, d),
  createKR: (data: unknown)        => api.post('/okrs/key-results', data),
  deleteKR: (id: any)          => api.delete(`/okrs/key-results/${id}`),
  checkin:  (krId: any, data: unknown)  => api.post(`/okrs/key-results/${krId}/checkin`, data),
}

// ── Pipeline (opportunities) ──────────────────────────────────────────────────
export const pipelineApi = {
  list:       (params?: any)    => api.get('/pipeline', { params }),
  get:        (id: any)        => api.get(`/pipeline/${id}`),
  create:     (data: unknown)      => api.post('/pipeline', data),
  update:     (id: any, data: unknown)  => api.patch(`/pipeline/${id}`, data),
  delete:     (id: any)        => api.delete(`/pipeline/${id}`),
  activities:       (id: any)          => api.get(`/pipeline/${id}/activities`),
  addActivity:      (id: any, data: unknown)    => api.post(`/pipeline/${id}/activities`, data),
  generateProposal: (id: any, payload: unknown) => api.post(`/pipeline/${id}/generate-proposal`, payload || {}),
  markProposalSent: (id: any)          => api.post(`/pipeline/${id}/mark-proposal-sent`),
  convertToProject: (id: any)          => api.post(`/pipeline/${id}/convert`),
  getProposal:      (id: any)          => api.get(`/pipeline/${id}/proposal`),
}

// ── Deliverables ──────────────────────────────────────────────────────────────
export const deliverablesApi = {
  listByProject:   (projectId: any) => api.get(`/deliverables/${projectId}`),
  overviewAll:     ()          => api.get('/deliverables/all/overview'),
  get:             (id: any)        => api.get(`/deliverables/${id}`),
  createForProject:(projectId: any, data: unknown) => api.post(`/deliverables/${projectId}`, data),
  updateInProject: (projectId: any, id: any, data: unknown) => api.patch(`/deliverables/${projectId}/${id}`, data),
  updateStatus:    (projectId: any, id: any, status: any) => api.patch(`/deliverables/${projectId}/${id}`, { status }),
  deleteFromProject:(projectId: any, id: any) => api.delete(`/deliverables/${projectId}/${id}`),
  accept:          (projectId: any, id: any) => api.post(`/deliverables/${projectId}/${id}/accept`),
  reject:          (projectId: any, id: any, reason: any) => api.post(`/deliverables/${projectId}/${id}/reject`, {}, { params: { reason } }),
}

// ── Subcontractors ────────────────────────────────────────────────────────────
export const subcontractorsApi = {
  // Auditoria 2026-08: el prefijo real es `/enterprise/`. Sin el, el selector
  // de entidades no cargaba ningun subcontratista. Hay otro cliente en este
  // mismo fichero que ya apuntaba bien — dos clientes para lo mismo, uno
  // roto y otro correcto.
  list:        (params?: any)    => api.get('/enterprise/subcontractors', { params }),
  create:      (data: unknown)      => api.post('/enterprise/subcontractors', data),
  update:      (id: any, data: unknown)  => api.patch(`/enterprise/subcontractors/${id}`, data),
  delete:      (id: any)        => api.delete(`/enterprise/subcontractors/${id}`),
  assignments: (id: any)        => api.get(`/enterprise/subcontractors/${id}/assignments`),
  timelogs:    (id: any, params?: any)=> api.get(`/enterprise/subcontractors/${id}/timelogs`, { params }),
  invoices:    (id: any)        => api.get(`/enterprise/subcontractors/${id}/invoices`),
}

// ── Training ──────────────────────────────────────────────────────────────────
export const trainingApi = {
  courses:     (params?: any)    => api.get('/training/courses', { params }),
  createCourse:(data: unknown)      => api.post('/training/courses', data),
  updateCourse:(id: any, data: unknown)  => api.patch(`/training/courses/${id}`, data),
  deleteCourse:(id: any)        => api.delete(`/training/courses/${id}`),
  certs:       (params?: any)    => api.get('/training/certifications', { params }),
  createCert:  (data: unknown)      => api.post('/training/certifications', data),
  updateCert:  (id: any, data: unknown)  => api.patch(`/training/certifications/${id}`, data),
  deleteCert:  (id: any)        => api.delete(`/training/certifications/${id}`),
  enroll:      (data: unknown)      => api.post('/training/enrollments', data),
  enrollments: (params?: any)    => api.get('/training/enrollments', { params }),
}

// ── Absences ──────────────────────────────────────────────────────────────────
export const absencesApi = {
  list:           (params?: any)    => import('./todasLasPaginas').then(m => m.todasLasPaginas<any>('/absences', params)) as Promise<any>,
  my:             (params?: any)    => api.get('/absences/my', { params }),
  pending:        ()          => api.get('/absences/pending'),
  team:           (params?: any)    => api.get('/absences/team', { params }),
  calendar:       (params?: any)    => api.get('/absences/calendar', { params }),
  createMy:       (data: unknown)      => api.post('/absences/my', data),
  updateMy:       (id: any, data: unknown)  => api.patch(`/absences/my/${id}`, data),
  review:         (id: any, data: unknown)  => api.post(`/absences/${id}/review`, data),
  deleteMy:       (id: any)        => api.delete(`/absences/my/${id}`),
  vacationBalance:()          => api.get('/absences/my/vacation-balance'),
}

// ── ALM — Assets, Licenses, Vendors ──────────────────────────────────────────
export const assetsApi = {
  list:    (params?: any)   => api.get('/alm/assets', { params }),
  get:     (id: any)       => api.get(`/alm/assets/${id}`),
  create:  (data: unknown)     => api.post('/alm/assets', data),
  update:  (id: any, data: unknown) => api.patch(`/alm/assets/${id}`, data),
  delete:  (id: any)       => api.delete(`/alm/assets/${id}`),
  history: (id: any)       => api.get(`/alm/assets/${id}/history`),
  expiring: (days: number) => api.get('/alm/assets/expiring', { params: { days } }),
  refreshTicket: (id: any) => api.post(`/alm/assets/${id}/refresh-ticket`),
}

export const licensesApi = {
  list:    (params?: any)   => api.get('/alm/licenses', { params }),
  get:     (id: any)       => api.get(`/alm/licenses/${id}`),
  create:  (data: unknown)     => api.post('/alm/licenses', data),
  update:  (id: any, data: unknown) => api.patch(`/alm/licenses/${id}`, data),
  delete:  (id: any)       => api.delete(`/alm/licenses/${id}`),
  assign:  (id: any, data: unknown) => api.post(`/alm/licenses/${id}/assign`, data),
}

export const vendorsApi = {
  list:   (params?: any)   => api.get('/alm/vendors', { params }),
  get:    (id: any)       => api.get(`/alm/vendors/${id}`),
  create: (data: unknown)     => api.post('/alm/vendors', data),
  update: (id: any, data: unknown) => api.patch(`/alm/vendors/${id}`, data),
  delete: (id: any)       => api.delete(`/alm/vendors/${id}`),
}

// ── Service Desk ──────────────────────────────────────────────────────────────
export const ticketsApi = {
  watchers:  (id: any)      => api.get(`/sd/tickets/${id}/watchers`),
  watch:     (id: any)      => api.post(`/sd/tickets/${id}/watch`),
  unwatch:   (id: any)      => api.delete(`/sd/tickets/${id}/watch`),
  mergeInto: (id: any, data: unknown) => api.post(`/sd/tickets/${id}/merge`, data),
  list:    (params?: any)   => api.get('/sd/tickets', { params }),
  myQueue: ()         => api.get('/sd/tickets/my-queue'),
  get:     (id: any)       => api.get(`/sd/tickets/${id}`),
  create:  (data: unknown)     => api.post('/sd/tickets', data),
  update:  (id: any, data: unknown) => api.patch(`/sd/tickets/${id}`, data),
  comment: (id: any, data: unknown) => api.post(`/sd/tickets/${id}/comments`, data),
  aiSuggest: (id: any, data: unknown) => api.post(`/sd/tickets/${id}/ai-suggest`, data),
  split:   (id: any, data: unknown) => api.post(`/sd/tickets/${id}/split`, data),
  links:   (id: any)       => api.get(`/sd/tickets/${id}/links`),
  addLink:    (id: any, data: unknown) => api.post(`/sd/tickets/${id}/links`, data),
  timelog:    (id: any, data: unknown)         => api.post(`/sd/tickets/${id}/time-log`, data),
  restorePending: (id: any)           => api.post(`/sd/tickets/${id}/restore-pending`, {}),
  escalate:   (id: any, level: string = 'l2') => api.post(`/sd/tickets/${id}/escalate?to_level=${level}`, {}),
  slaPause:   (id: any, data: unknown) => api.post(`/sd/tickets/${id}/sla/pause`, data),
  slaResume:  (id: any)       => api.post(`/sd/tickets/${id}/sla/resume`),
  internalComments:      (id: any)         => api.get(`/sd/tickets/${id}/internal-comments`),
  createInternalComment: (id: any, data: unknown)   => api.post(`/sd/tickets/${id}/internal-comments`, data),
  updateInternalComment: (id: any, cid: any, data: unknown) => api.patch(`/sd/tickets/${id}/internal-comments/${cid}`, data),
  deleteInternalComment: (id: any, cid: any)    => api.delete(`/sd/tickets/${id}/internal-comments/${cid}`),
  recommendAssignment:   (id: any, data: unknown)   => api.post(`/sd/tickets/${id}/recommend-assignment`, data),
  autoResolutionFeedback:(id: any, data: unknown)   => api.post(`/sd/tickets/${id}/auto-resolution/feedback`, data),
}

export const problemsApi = {
  list:   (params?: any)   => api.get('/sd/problems', { params }),
  create: (data: unknown)     => api.post('/sd/problems', data),
  update: (id: any, data: unknown) => api.patch(`/sd/problems/${id}`, data),
  delete:             (id: any)       => api.delete(`/sd/problems/${id}`),
  // Auditoria 2026-08: la ruta real acaba en `promote-kedb`, no en
  // `promote-known-error`. La pestaña de conocimiento de ITSM daba 404.
  promoteKnownError:  (id: any)       => api.post(`/sd/problems/${id}/promote-kedb`),
  // RCA Wizard
  rcaWizardGet:      (id: any)        => api.get(`/sd/problems/${id}/rca-wizard`),
  rcaWizardStart:    (id: any, data: unknown)  => api.post(`/sd/problems/${id}/rca-wizard/start`, data),
  rcaWizardStep:     (id: any, data: unknown)  => api.post(`/sd/problems/${id}/rca-wizard/step`, data),
  rcaWizardComplete: (id: any)        => api.post(`/sd/problems/${id}/rca-wizard/complete`),
  rcaWizardAiAssist: (id: any, data: unknown)  => api.post(`/sd/problems/${id}/rca-wizard/ai-assist`, data),
}

export const changesApi = {
  list:    (params?: any)   => api.get('/sd/changes', { params }),
  get:     (id: any)       => api.get(`/sd/changes/${id}`),
  create:  (data: unknown)     => api.post('/sd/changes', data),
  update:  (id: any, data: unknown) => api.patch(`/sd/changes/${id}`, data),
  delete:  (id: any)       => api.delete(`/sd/changes/${id}`),
  approve: (id: any, data: unknown) => api.post(`/sd/changes/${id}/approve`, data),
}

export const sdDynamicFormsApi = {
  get:           () => api.get('/sd/dynamic-forms'),
  save:          (data: unknown) => api.put('/sd/dynamic-forms', data),
  history:       () => api.get('/sd/dynamic-forms/history'),
  diff:          (data: unknown) => api.post('/sd/dynamic-forms/diff', data),
  contextOptions:(params?: any) => api.get('/sd/dynamic-forms/context-options', { params }),
  rollback:      (snapshot_id: any) => api.post('/sd/dynamic-forms/rollback', { snapshot_id }),
  importPreview: (data: unknown) => api.post('/sd/dynamic-forms/import/preview', data),
  importApply:   (data: unknown) => api.post('/sd/dynamic-forms/import/apply', data),
}

// ── Revenue (legacy engine) ───────────────────────────────────────────────────
export const revenueApi = {
  rules:       ()               => api.get('/revenue/rules'),
  summary:     ()               => api.get('/revenue/summary'),
  createRule:  (data: unknown)           => api.post('/revenue/rules', data),
  autoCompute: (period: any)         => api.post('/revenue/auto-compute', { period }),
  compute:     (id: any, period: any)     => api.post(`/revenue/rules/${id}/compute`, { period }),
}

// ── Invoices ──────────────────────────────────────────────────────────────────
export const invoicesApi = {
  list:          (params?: any)          => api.get('/invoices', { params }),
  summary:       ()                => api.get('/invoices/summary'),
  create:        (data: unknown)            => api.post('/invoices', data),
  updateStatus:  (id: any, status: any)      => api.patch(`/billing-reports/invoices/${id}/status`, { status }),
  pdf:           (id: any)              => api.get(`/invoices/${id}/pdf`, { responseType: 'blob' }),
  fromTimesheets:(data: unknown)            => api.post('/invoices/from-timesheets', data),
}

// ── Accounting Hub (Xero / QuickBooks) ────────────────────────────────────────
export const accountingApi = {
  syncStatus:    ()                => api.get('/accounting/sync-status'),
  xeroTest:      ()                => api.post('/accounting/xero/test'),
  qbTest:        ()                => api.post('/accounting/qb/test'),
  pushInvoice:   (data: unknown)            => api.post('/accounting/push-invoice', data),
  pushBulk:      (data: unknown)            => api.post('/accounting/push-invoices-bulk', data),
  xeroContacts:  ()                => api.get('/accounting/xero/contacts'),
}

// ── Currency Rates ────────────────────────────────────────────────────────────
const getWithFallback = async (paths: string[], config?: AxiosRequestConfig) => {
  let lastErr: unknown
  for (const path of paths) {
    try {
      return await api.get(path, config)
    } catch (err) {
      lastErr = err
      if ((err as { response?: { status?: number } })?.response?.status !== 404) throw err
    }
  }
  throw lastErr
}

const postWithFallback = async (paths: string[], data?: unknown, config?: AxiosRequestConfig) => {
  let lastErr: unknown
  for (const path of paths) {
    try {
      return await api.post(path, data, config)
    } catch (err) {
      lastErr = err
      if ((err as { response?: { status?: number } })?.response?.status !== 404) throw err
    }
  }
  throw lastErr
}

export const currencyApi = {
  // Canonical platform routes go first to avoid dev-console 404 noise from legacy probes.
  rates:   (params?: any)        => getWithFallback(['/currency/rates', '/currency-rates/currency/rates', '/bookings/currency/rates'], { params }),
  upsert:  (data: unknown)          => postWithFallback(['/currency/rates', '/currency-rates/currency/rates', '/bookings/currency/rates'], data),
  convert: (params?: any)        => getWithFallback(['/currency/convert', '/currency-rates/currency/convert'], { params }),
  report:  (params?: any)        => getWithFallback(['/currency/report', '/currency-rates/currency/report'], { params }),
}

// ── Predictive Observability ──────────────────────────────────────────────────
export const predictiveObservabilityApi = {
  status:        (orgId: any)   => api.get('/bi/predictive/observability/status', { params: orgId ? { organization_id: orgId } : {} }),
  health:        (params?: any)  => api.get('/bi/predictive/observability/health', { params }),
  triggerRetrain:()        => api.post('/bi/predictive/observability/trigger-retrain'),
}

// ── ML Predictions ────────────────────────────────────────────────────────────
export const predictionsApi = {
  overrunRisk:    (projectId: any)  => api.post('/predictions/overrun-risk', { project_id: projectId }),
  portfolioRisk:  ()           => api.get('/predictions/portfolio-risk'),
  train:          ()           => api.post('/predictions/train'),
  models:         ()           => api.get('/predictions/models'),
  logs:           (params?: any)     => api.get('/predictions/logs', { params }),
}

// ── Revenue Recognition (ASC 606) ─────────────────────────────────────────────
export const revenueRecognitionApi = {
  dashboard:           (year: any, months: any) => api.get('/revenue-recognition/dashboard', { params: { year, months } }),
  contracts:           (params?: any)       => api.get('/revenue-recognition/contracts', { params }),
  getContract:         (id: any)           => api.get(`/revenue-recognition/contracts/${id}`),
  createContract:      (data: unknown)         => api.post('/revenue-recognition/contracts', data),
  updateContract:      (id: any, data: unknown)     => api.patch(`/revenue-recognition/contracts/${id}`, data),
  deleteContract:      (id: any)           => api.delete(`/revenue-recognition/contracts/${id}`),
  obligations:         (contractId: any)   => api.get(`/revenue-recognition/contracts/${contractId}/obligations`),
  createObligation:    (contractId: any, d: unknown)=> api.post(`/revenue-recognition/contracts/${contractId}/obligations`, d),
  updateObligation:    (id: any, data: unknown)     => api.patch(`/revenue-recognition/obligations/${id}`, data),
  deleteObligation:    (id: any)           => api.delete(`/revenue-recognition/obligations/${id}`),
  entries:             (params?: any)       => api.get('/revenue-recognition/entries', { params }),
  reverseEntry:        (id: any)           => api.post(`/revenue-recognition/entries/${id}/reverse`),
  periodCloses:        ()             => api.get('/revenue-recognition/period-closes'),
  closePeriod:         (data: unknown)         => api.post('/revenue-recognition/period-closes', data),
  reopenPeriod:        (year: any, month: any)  => api.delete(`/revenue-recognition/period-closes/${year}/${month}`),
  runMonthly:          (data: unknown)         => api.post('/revenue-recognition/run-monthly', data),
}

// ── CMDB ──────────────────────────────────────────────────────────────────────
export const cmdbApi = {
  // Una sola CMDB (auditoría 2026-11): la del service desk, `/sd/cmdb`.
  sdList:         (params?: any)   => api.get('/sd/cmdb', { params }),
  sdCreate:       (data: unknown)     => api.post('/sd/cmdb', data),
  sdUpdate:       (id: any, data: unknown) => api.patch(`/sd/cmdb/${id}`, data),
  sdDelete:       (id: any)       => api.delete(`/sd/cmdb/${id}`),
  sdChangelog:    (id: any)       => api.get(`/sd/cmdb/${id}/changelog`),
  sdRelations:    (id: any)       => api.get(`/sd/cmdb/${id}/relations`),
  sdCreateRelation: (data: unknown)   => api.post('/sd/cmdb/relations', data),
  sdDeleteRelation: (id: any)     => api.delete(`/sd/cmdb/relations/${id}`),
  sdImpact:       (id: any)       => api.get(`/sd/cmdb/${id}/impact`),
  classFields:    ()              => api.get('/sd/cmdb/class-fields'),
  saveClassFields: (ciType: string, fields: unknown) => api.put(`/sd/cmdb/class-fields/${ciType}`, fields),
  topology:       (id: any, r: any)    => api.get(`/sd/cmdb/${id}/topology`, { params: { radius: r } }),
  // Agents
  agents:         ()         => api.get('/sd/cmdb/agents'),
  registerAgent:  (data: unknown)     => api.post('/sd/cmdb/agents/register', data),
  deleteAgent:    (id: any)       => api.delete(`/sd/cmdb/agents/${id}`),
  agentDashboard: (agentId: any, days: any) => api.get(`/cmdb/agent-dashboard/${agentId}?days=${days}`),
  assetsByCI:     (ciId: any)     => api.get(`/alm/assets/by-ci/${ciId}`),
}

// ── Timesheets ────────────────────────────────────────────────────────────────
export const timesheetsApi = {
  my:          ()              => api.get('/timesheets/my'),
  pending:     ()              => api.get('/timesheets/pending'),
  team:        ()              => api.get('/timesheets/team'),
  weekLines:   (weekStart: any)     => api.get(`/timesheets/my/${weekStart}/lines`),
  submit:      (weekStart: any)     => api.post(`/timesheets/my/${weekStart}/submit`),
  review:      (id: any, data: unknown)      => api.post(`/timesheets/${id}/review`, data),
}

// ── Documents ─────────────────────────────────────────────────────────────────
export const documentsApi = {
  list:      (params?: any)   => api.get('/documents', { params }),
  get:       (id: any)       => api.get(`/documents/${id}`),
  upload:    (fd: unknown)       => api.post('/documents/upload', fd),
  update:    (id: any, data: unknown) => api.patch(`/documents/${id}`, data),
  delete:    (id: any)       => api.delete(`/documents/${id}`),
  approve:   (id: any, data: unknown) => api.post(`/documents/${id}/approve`, data),
  submitApproval: (id: any)  => api.post(`/documents/${id}/submit-approval`),
  aiSummary: (id: any)       => api.post(`/documents/${id}/ai-summary`),
  addVersion:(id: any, fd: unknown)   => api.post(`/documents/${id}/versions`, fd),
  // Permisos
  listPermissions:   (id: any)              => api.get(`/documents/${id}/permissions`),
  grantPermission:   (id: any, data: unknown)        => api.post(`/documents/${id}/permissions`, data),
  revokePermission:  (id: any, permId: any)      => api.delete(`/documents/${id}/permissions/${permId}`),
  // By context
  byTask:    (taskId: any, params?: any)    => api.get(`/documents/by-task/${taskId}`, { params }),
  byTicket:  (ticketId: any, params?: any)  => api.get(`/documents/by-ticket/${ticketId}`, { params }),
  byProject: (projectId: any, params?: any) => api.get(`/documents/by-project/${projectId}`, { params }),
}

// ── Custom Fields ─────────────────────────────────────────────────────────────
export const customFieldsApi = {
  list:   (projectId: any)          => api.get(`/custom-fields/${projectId}`),
  create: (projectId: any, data: unknown)    => api.post(`/custom-fields/${projectId}`, data),
  update: (projectId: any, id: any, data: unknown)=> api.patch(`/custom-fields/${projectId}/${id}`, data),
  delete:    (projectId: any, id: any)           => api.delete(`/custom-fields/${projectId}/${id}`),
  getValues: (projectId: any, taskId: any)       => api.get(`/custom-fields/${projectId}/values/${taskId}`),
  setValues: (projectId: any, taskId: any, data: unknown) => api.post(`/custom-fields/${projectId}/values/${taskId}`, data),
}

// ── Wiki ──────────────────────────────────────────────────────────────────────
export const wikiApi = {
  spaces:       ()              => api.get('epics/wiki/spaces'),
  createSpace:  (data: unknown)          => api.post('epics/wiki/spaces', data),
  pages:        (spaceId: any)       => api.get(`epics/wiki/spaces/${spaceId}/pages`),
  getPage:      (id: any)            => api.get(`epics/wiki/pages/${id}`),
  createPage:   (spaceId: any, data: unknown) => api.post(`epics/wiki/spaces/${spaceId}/pages`, data),
  updatePage:   (id: any, data: unknown)      => api.patch(`epics/wiki/pages/${id}`, data),
  deletePage:   (id: any)            => api.delete(`epics/wiki/pages/${id}`),
  versions:     (id: any)            => api.get(`epics/wiki/pages/${id}/versions`),
  restorePage:  (id: any, vn: any)        => api.post(`epics/wiki/pages/${id}/restore/${vn}`),
  search:       (q: any, spaceId: any)    => api.get(`epics/wiki/search`, { params: { q, space_id: spaceId } }),
  // Auditoria 2026-08: las cuatro rutas de etiquetas viven bajo `/cmdb/`.
  // Sin el prefijo, toda la gestion de etiquetas del wiki devolvia 404.
  tags:             (space: any)         => api.get(`/cmdb/wiki-tags/${space}`),
  createTag:        (space: any, data: unknown)   => api.post(`/cmdb/wiki-tags/${space}`, data),
  updateTag:        (id: any, data: unknown)      => api.patch(`/cmdb/wiki-tags/${id}`, data),
  deleteTag:        (id: any)            => api.delete(`/cmdb/wiki-tags/${id}`),
  // portal-scoped wiki (different URL prefix)
  portalSpaces:     ()              => api.get('wiki/spaces'),
  portalPages:      (spaceId: any)       => api.get(`wiki/spaces/${spaceId}/pages`),
  portalUpdatePage: (id: any, data: unknown)      => api.patch(`wiki/pages/${id}`, data),
}

// ── Skills ────────────────────────────────────────────────────────────────────
export const skillsApi = {
  catalog:        ()               => api.get('/skills/catalog'),
  createCatalog:  (data: unknown)           => api.post('/skills/catalog', data),
  deleteCatalog:  (id: any)             => api.delete(`/skills/catalog/${id}`),
  userSkills:     (userId: any)         => api.get(`/skills/users/${userId}`),
  userHistory:    (userId: any)         => api.get(`/skills/users/${userId}/history`),
  addUserSkill:   (userId: any, data: unknown)   => api.post(`/skills/users/${userId}`, data),
  removeUserSkill:(userId: any, skillId: any)=> api.delete(`/skills/users/${userId}/${skillId}`),
  matrix:         ()               => api.get('/skills/matrix'),
  search:         (params?: any)         => api.get('/skills/search', { params }),
}

// ── Enterprise Subcontractors ─────────────────────────────────────────────────
export const enterpriseSubsApi = {
  dashboard:        ()                     => api.get('/enterprise/subcontractors-dashboard'),
  list:             ()                     => api.get('/enterprise/subcontractors'),
  create:           (data: unknown)                 => api.post('/enterprise/subcontractors', data),
  update:           (id: any, data: unknown)             => api.patch(`/enterprise/subcontractors/${id}`, data),
  delete:           (id: any)                   => api.delete(`/enterprise/subcontractors/${id}`),
  workers:          (subId: any)                => api.get(`/enterprise/subcontractors/${subId}/workers`),
  createWorker:     (subId: any, data: unknown)          => api.post(`/enterprise/subcontractors/${subId}/workers`, data),
  updateWorker:     (id: any, data: unknown)             => api.patch(`/enterprise/subcontractors/workers/${id}`, data),
  deleteWorker:     (id: any)                   => api.delete(`/enterprise/subcontractors/workers/${id}`),
  addWorkerSkill:   (id: any, data: unknown)             => api.post(`/enterprise/subcontractors/workers/${id}/skills`, data),
  removeWorkerSkill:(id: any, skillId: any)          => api.delete(`/enterprise/subcontractors/workers/${id}/skills/${skillId}`),
  assignments:      (subId: any)                => api.get(`/enterprise/subcontractors/${subId}/assignments`),
  createAssignment: (subId: any, data: unknown)          => api.post(`/enterprise/subcontractors/${subId}/assignments`, data),
  timelogs:         (subId: any)                => api.get(`/enterprise/subcontractors/${subId}/timelogs`),
  createTimelog:    (subId: any, data: unknown)          => api.post(`/enterprise/subcontractors/${subId}/timelogs`, data),
  invoices:         (subId: any)                => api.get(`/enterprise/subcontractors/${subId}/invoices`),
  createInvoice:    (subId: any, data: unknown)          => api.post(`/enterprise/subcontractors/${subId}/invoices`, data),
  updateInvoice:    (subId: any, id: any, data: unknown)      => api.patch(`/enterprise/subcontractors/${subId}/invoices/${id}`, data),
}

// ── ALM Extended (contracts, cost-centers, compliance) ────────────────────────
export const almExtApi = {
  dashboard:       ()              => api.get('/alm/dashboard'),
  contracts:       ()              => api.get('/alm/contracts'),
  createContract:  (data: unknown)          => api.post('/alm/contracts', data),
  updateContract:  (id: any, data: unknown)      => api.patch(`/alm/contracts/${id}`, data),
  deleteContract:  (id: any)            => api.delete(`/alm/contracts/${id}`),
  costCenters:     ()              => api.get('/alm/cost-centers'),
  createCostCenter:(data: unknown)          => api.post('/alm/cost-centers', data),
  updateCostCenter:(id: any, data: unknown)      => api.patch(`/alm/cost-centers/${id}`, data),
  deleteCostCenter:(id: any)            => api.delete(`/alm/cost-centers/${id}`),
  compliance:      ()              => api.get('/alm/compliance'),
}

// ── CAB (Change Advisory Board) ───────────────────────────────────────────────
export const cabApi = {
  changes: ()             => api.get('/cab/changes'),
  windows: ()             => api.get('/cab/windows'),
  vote:    (id: any, data: unknown)     => api.post(`/cab/changes/${id}/vote`, data),
  close:   (id: any, data: unknown)     => api.post(`/cab/changes/${id}/close`, data),
}

// ── Project Change Requests ───────────────────────────────────────────────────
export const projectChangesApi = {
  list:       (projectId: any)           => api.get(`/changes/${projectId}`),
  allPending: ()                    => api.get('/changes/all/pending'),
  create:     (projectId: any, data: unknown)     => api.post(`/changes/${projectId}`, data),
  update:     (projectId: any, id: any, data: unknown) => api.patch(`/changes/${projectId}/${id}`, data),
  review:     (projectId: any, id: any, data: unknown) => api.post(`/changes/${projectId}/${id}/review`, data),
  submit:     (projectId: any, id: any)       => api.post(`/changes/${projectId}/${id}/submit`),
  implement:  (projectId: any, id: any)       => api.post(`/changes/${projectId}/${id}/implement`),
  delete:     (projectId: any, id: any)       => api.delete(`/changes/${projectId}/${id}`),
}

// ── NPS ───────────────────────────────────────────────────────────────────────
export const npsApi = {
  leaderboard:    ()            => api.get('/nps/leaderboard'),
  summary:        (id: any, days: any)    => api.get(`/nps/${id}/summary`, { params: { days } }),
  health:         (id: any, limit: any)   => api.get(`/nps/${id}/health`, { params: { limit } }),
  healthCompute:  (id: any)          => api.post(`/nps/${id}/health-compute`),
  respond:        (id: any, data: unknown)    => api.post(`/nps/${id}/responses`, data),
}

// ── Portfolios ────────────────────────────────────────────────────────────────
export const portfolioApi = {
  list:          ()             => api.get('/portfolios'),
  get:           (id: any)           => api.get(`/portfolios/${id}`),
  dashboard:     (id: any)           => api.get(`/portfolios/${id}/dashboard`),
  create:        (data: unknown)         => api.post('/portfolios', data),
  update:        (id: any, data: unknown)     => api.patch(`/portfolios/${id}`, data),
  delete:        (id: any)           => api.delete(`/portfolios/${id}`),
  addProject:    (id: any, pid: any)      => api.post(`/portfolios/${id}/projects`, { project_id: pid }),
  removeProject: (id: any, pid: any)      => api.delete(`/portfolios/${id}/projects/${pid}`),
}

// ── Performance Reviews ───────────────────────────────────────────────────────
export const performanceApi = {
  cycles:        ()             => api.get('/performance/cycles'),
  myReviews:     ()             => api.get('/performance/my-reviews'),
  cycleReviews:  (id: any)           => api.get(`/performance/cycles/${id}/reviews`),
  createCycle:   (data: unknown)         => api.post('/performance/cycles', data),
  activateCycle: (id: any)           => api.post(`/performance/cycles/${id}/activate`),
  closeCycle:    (id: any)           => api.post(`/performance/cycles/${id}/close`),
  // Asignar evaluación (qué evaluador evalúa a qué evaluado dentro de un ciclo)
  createReview:  (cycleId: any, data: unknown) => api.post(`/performance/cycles/${cycleId}/reviews`, data),
  updateReview:  (id: any, data: unknown)     => api.patch(`/performance/reviews/${id}`, data),
  submitReview:  (id: any)           => api.post(`/performance/reviews/${id}/submit`),
  userHistory:   (userId: any)       => api.get(`/performance/users/${userId}/history`),
  // Plantilla de preguntas por ciclo
  listQuestions:    (cycleId: any)            => api.get(`/performance/cycles/${cycleId}/questions`),
  addQuestion:      (cycleId: any, data: unknown)      => api.post(`/performance/cycles/${cycleId}/questions`, data),
  updateQuestion:   (qId: any, data: unknown)          => api.patch(`/performance/questions/${qId}`, data),
  deleteQuestion:   (qId: any)                => api.delete(`/performance/questions/${qId}`),
  seedDefaultQuestions: (cycleId: any)        => api.post(`/performance/cycles/${cycleId}/questions/seed-default`),
  cloneQuestions:   (cycleId: any, sourceId: any)  => api.post(`/performance/cycles/${cycleId}/clone-questions/${sourceId}`),
  // Smart 360°: pool de evaluadores elegibles según tipo de revisión
  eligibleReviewers: (cycleId: any, revieweeId: any, type: any) =>
    api.get(`/performance/cycles/${cycleId}/eligible-reviewers/${revieweeId}/${type}`),
  // Campañas 360° (subject + multi-evaluator + dashboard agregado anonimizado)
  listCampaigns:    (cycleId: any)        => api.get(`/performance/cycles/${cycleId}/campaigns`),
  createCampaign:   (cycleId: any, data: unknown)  => api.post(`/performance/cycles/${cycleId}/campaigns`, data),
  closeCampaign:    (id: any)             => api.post(`/performance/campaigns/${id}/close`),
  campaignDashboard:(id: any)             => api.get(`/performance/campaigns/${id}/dashboard`),
  campaignDashboardPdf:(id: any)          => api.get(`/performance/campaigns/${id}/dashboard.pdf`,
                                                { responseType: 'blob' }),
  campaignReviews:  (id: any)             => api.get(`/performance/campaigns/${id}/reviews`),
  history360:       (userId: any)         => api.get(`/performance/users/${userId}/360-history`),
  // KPIs operativos (HR)
  orgKpis:          ()               => api.get('/performance/kpis'),
  cycleKpis:        (id: any)             => api.get(`/performance/cycles/${id}/kpis`),
  runReminders:     ()               => api.post('/performance/admin/run-reminders'),
  // Development plans
  listUserPlans:    (userId: any)         => api.get(`/performance/users/${userId}/dev-plans`),
  getPlan:          (id: any)             => api.get(`/performance/dev-plans/${id}`),
  createPlan:       (data: unknown)           => api.post('/performance/dev-plans', data),
  updatePlan:       (id: any, data: unknown)       => api.patch(`/performance/dev-plans/${id}`, data),
  addGoal:          (planId: any, data: unknown)   => api.post(`/performance/dev-plans/${planId}/goals`, data),
  updateGoal:       (id: any, data: unknown)       => api.patch(`/performance/dev-goals/${id}`, data),
  deleteGoal:       (id: any)             => api.delete(`/performance/dev-goals/${id}`),
}

// ── Capacity Planning ─────────────────────────────────────────────────────────
export const capacityApi = {
  board:       (params?: any)         => api.get('/capacity/board', { params }),
  createPlan:  (data: unknown)           => api.post('/capacity/plans', data),
  updatePlan:  (id: any, data: unknown)       => api.patch(`/capacity/plans/${id}`, data),
  deletePlan:  (id: any)             => api.delete(`/capacity/plans/${id}`),
}

// ── Profitability ─────────────────────────────────────────────────────────────
export const profitabilityApi = {
  get:             (projectId: any)          => api.get(`/profitability/${projectId}`),
  summary:         (params?: any)             => api.get('/profitability/summary', { params }),
  projects:        (params?: any)             => api.get('/profitability/projects', { params }),
  createMilestone: (projectId: any, data: unknown)    => api.post(`/profitability/${projectId}/milestones`, data),
  updateMilestone: (projectId: any, id: any, data: unknown)=> api.patch(`/profitability/${projectId}/milestones/${id}`, data),
  deleteMilestone: (projectId: any, id: any)      => api.delete(`/profitability/${projectId}/milestones/${id}`),
}

// ── BI Forecasting ────────────────────────────────────────────────────────────
export const biForecastingApi = {
  getMetrics:     ()                   => api.get('/bi/forecast/metrics'),
  // The backend forecasts a single metric via POST /bi/forecast {metric, ...}.
  forecast:       (metric: any, params?: any)     => api.post('/bi/forecast', { metric, ...(params || {}) }),
  multiForecast:  (data: unknown)               => api.post('/bi/forecast/multi', data),
  // Aliases kept for BiForecastingPanel (same canonical routes).
  listMetrics:    ()                   => api.get('/bi/forecast/metrics'),
  run:            (data: unknown)               => api.post('/bi/forecast', data),
}

// ── BI Anomaly / Churn ────────────────────────────────────────────────────────
export const biAnomalyApi = {
  getInfo:        ()                   => api.get('/bi/anomaly/info'),
  detect:         (data: unknown)               => api.post('/bi/anomaly/detect', data),
  churnPredict:   (data: unknown)               => api.post('/bi/churn/predict', data),
}

// ── BI GDPR ───────────────────────────────────────────────────────────────────
export const biGdprApi = {
  recordConsent:       (data: unknown)          => api.post('/bi/gdpr/consent', data),
  getConsent:          (params?: any)        => api.get('/bi/gdpr/consent', { params }),
  listConsents:        ()              => api.get('/bi/gdpr/consents'),
  getConsentHistory:   (userId: any)        => api.get(`/bi/gdpr/consent/${userId}/history`),
  createDsr:           (data: unknown)          => api.post('/bi/gdpr/dsr', data),
  getDsr:              (id: any)            => api.get(`/bi/gdpr/dsr/${id}`),
  listDsr:             (params?: any)        => api.get('/bi/gdpr/dsr', { params }),
  resolveDsr:          (id: any, data: unknown)      => api.patch(`/bi/gdpr/dsr/${id}/resolve`, data),
  executeDsrErasure:   (id: any)            => api.post(`/bi/gdpr/dsr/${id}/erasure-execute`),
  executeDsrPortability: (id: any)          => api.post(`/bi/gdpr/dsr/${id}/portability-export`),
  setFieldMask:        (data: unknown)          => api.post('/bi/gdpr/field-masks', data),
  getFieldMasks:       ()              => api.get('/bi/gdpr/field-masks'),
  getStats:            ()              => api.get('/bi/gdpr/stats'),
}

// ── BI Dashboard Collaboration ────────────────────────────────────────────────
export const biDashboardCollabApi = {
  addComment:     (data: unknown)               => api.post('/bi/collab/comments', data),
  listComments:   (params?: any)             => api.get('/bi/collab/comments', { params }),
  resolveComment: (id: any)                 => api.patch(`/bi/collab/comments/${id}/resolve`),
  saveView:       (data: unknown)               => api.post('/bi/collab/views', data),
  listViews:      (params?: any)             => api.get('/bi/collab/views', { params }),
  addReaction:    (data: unknown)               => api.post('/bi/collab/reactions', data),
}

// ── BI Query Builder ──────────────────────────────────────────────────────────
export const biQueryBuilderApi = {
  getSchema:      (params?: any)             => api.get('/bi/query-builder/schema', { params }),
  previewQuery:   (data: unknown)               => api.post('/bi/query-builder/preview', data),
  saveQuery:      (data: unknown)               => api.post('/bi/query-builder/queries', data),
  listQueries:    ()                   => api.get('/bi/query-builder/queries'),
  executeQuery:   (id: any)                 => api.post(`/bi/query-builder/queries/${id}/execute`),
  deleteQuery:    (id: any)                 => api.delete(`/bi/query-builder/queries/${id}`),
}

// ── BI Conditional Delivery ───────────────────────────────────────────────────
export const biConditionalDeliveryApi = {
  createRule:     (data: unknown)               => api.post('/bi/delivery/rules', data),
  listRules:      ()                   => api.get('/bi/delivery/rules'),
  updateRule:     (id: any, data: unknown)           => api.patch(`/bi/delivery/rules/${id}`, data),
  deleteRule:     (id: any)                 => api.delete(`/bi/delivery/rules/${id}`),
  evaluate:       (id: any, data: unknown = {})      => api.post(`/bi/delivery/rules/${id}/evaluate`, data),
}

// ── BI ETL Connectors ─────────────────────────────────────────────────────────
export const biEtlApi = {
  listConnectors: ()                   => api.get('/bi/etl/connectors'),
  getConnector:   (id: any)                 => api.get(`/bi/etl/connectors/${id}`),
  triggerSync:    (id: any, data: unknown)           => api.post(`/bi/etl/connectors/${id}/sync`, data),
  getLog:         (id: any)                 => api.get(`/bi/etl/connectors/${id}/log`),
  getData:        (id: any, params?: any)         => api.get(`/bi/etl/data/${id}`, { params }),
}

// ── BI Office 365 ─────────────────────────────────────────────────────────────
export const biO365Api = {
  getConfig:      ()                   => api.get('/bi/o365/config'),
  saveConfig:     (data: unknown)               => api.put('/bi/o365/config', data),
  triggerSync:    (data: unknown)               => api.post('/bi/o365/sync', data),
  getReport:      (name: any, params?: any)       => api.get(`/bi/o365/reports/${name}`, { params }),
  getAdoption:    ()                   => api.get('/bi/o365/adoption'),
  getSyncLog:     ()                   => api.get('/bi/o365/sync-log'),
}

// ── Voice Agent (IVR) ─────────────────────────────────────────────────────────
export const voiceAgentApi = {
  getConfig:      ()                   => api.get('/sd/voice/config'),
  updateConfig:   (data: unknown)               => api.put('/sd/voice/config', data),
  createSession:  (data: unknown)               => api.post('/sd/voice/sessions', data),
  listSessions:   (params?: any)             => api.get('/sd/voice/sessions', { params }),
  getSession:     (id: any)                 => api.get(`/sd/voice/sessions/${id}`),
  addTurn:        (id: any, data: unknown)           => api.post(`/sd/voice/sessions/${id}/turn`, data),
  closeSession:   (id: any, data: unknown)           => api.post(`/sd/voice/sessions/${id}/close`, data),
  createTicket:   (id: any)                 => api.post(`/sd/voice/sessions/${id}/ticket`),
}

// ── Incident Assignment ML ────────────────────────────────────────────────────
export const incidentAssignmentApi = {
  recommend:      (ticketId: any, data: unknown)     => api.post(`/sd/tickets/${ticketId}/recommend-assignment`, data),
  stats:          ()                   => api.get('/sd/assignment/stats'),
}

// ── Change Rollout ────────────────────────────────────────────────────────────
export const changeRolloutApi = {
  listPlans:      (changeId: any)           => api.get(`/sd/changes/${changeId}/rollout-plans`),
  getPlan:        (id: any)                 => api.get(`/sd/changes/rollout-plans/${id}`),
  createPlan:     (changeId: any, data: unknown)     => api.post(`/sd/changes/${changeId}/rollout-plans`, data),
  approvePlan:    (id: any)                 => api.post(`/sd/changes/rollout-plans/${id}/approve`),
  advancePhase:   (id: any, data: unknown)           => api.post(`/sd/changes/rollout-plans/${id}/advance-phase`, data),
  simulate:       (data: unknown)               => api.post('/sd/changes/rollout-plans/simulate', data),
  simulatePlan:   (changeId: any, planId: any)   => api.post(`/sd/changes/${changeId}/rollout-plans/${planId}/simulate`, {}),
  rollback:       (changeId: any, data: unknown)     => api.post(`/sd/changes/${changeId}/rollback`, data),
}

// ── CMDB 3D Graph ─────────────────────────────────────────────────────────────
export const cmdb3dApi = {
  getGraph:       (params?: any)             => api.get('/sd/cmdb/3d-graph', { params }),
  blastRadius:    (ciId: any)               => api.get(`/sd/cmdb/blast-radius/${ciId}`),
  createLink:     (data: unknown)               => api.post('/sd/cmdb/asset-links', data),
  listLinks:      (params?: any)             => api.get('/sd/cmdb/asset-links', { params }),
  getImpact:      (assetId: any)            => api.get(`/sd/cmdb/asset-impact/${assetId}`),
}

// ── WebSocket Ticket ──────────────────────────────────────────────────────────
export const wsApi = {
  ticket: () => api.get('/ws/ticket'),
}

// ── Sprint (project-scoped) ───────────────────────────────────────────────────
export const projectSprintsApi = {
  list:          (projectId: any)                    => api.get(`/sprints/${projectId}/sprints`),
  create:        (projectId: any, data: unknown)              => api.post(`/sprints/${projectId}/sprints`, data),
  update:        (projectId: any, id: any, data: unknown)          => api.patch(`/sprints/${projectId}/sprints/${id}`, data),
  start:         (projectId: any, id: any)                => api.post(`/sprints/${projectId}/sprints/${id}/start`),
  close:         (projectId: any, id: any)                => api.post(`/sprints/${projectId}/sprints/${id}/close`),
  burndown:      (projectId: any, id: any)                => api.get(`/sprints/${projectId}/sprints/${id}/burndown`),
  backlog:       (projectId: any)                    => api.get(`/sprints/${projectId}/backlog`),
  velocity:      (projectId: any)                    => api.get(`/sprints/${projectId}/velocity`),
  addTasks:      (projectId: any, sprintId: any, taskIds: any) => api.post(`/sprints/${projectId}/sprints/${sprintId}/tasks`, { task_ids: taskIds }),
  removeTask:    (projectId: any, sprintId: any, taskId: any)  => api.delete(`/sprints/${projectId}/sprints/${sprintId}/tasks/${taskId}`),
  retrospective:      (projectId: any, sprintId: any)       => api.get(`/projects/${projectId}/sprints/${sprintId}/retrospective`),
  saveRetrospective:  (projectId: any, sprintId: any, data: unknown) => api.put(`/projects/${projectId}/sprints/${sprintId}/retrospective`, data),
  burnup:             (projectId: any, sprintId: any)       => api.get(`/sprints/${projectId}/sprints/${sprintId}/burnup`),
}

// ── Portal Clients ────────────────────────────────────────────────────────────
export const portalClientsApi = {
  list:         (params?: any)   => api.get('/portal/clients', { params }),
  create:       (data: unknown)     => api.post('/portal/clients', data),
  update:       (id: any, data: unknown) => api.patch(`/portal/clients/${id}`, data),
  translations: ()         => api.get('/portal/translations'),
  saveTranslations: (data: unknown) => api.post('/portal/translations', data),
}

// ── Service Desk — Major Incidents ────────────────────────────────────────────
export const majorIncidentsApi = {
  list:   ()      => api.get('/sd/major-incidents'),
  create: (data: unknown)  => api.post('/sd/major-incidents', data),
}


// ── Settings ──────────────────────────────────────────────────────────────────
export const settingsApi = {
  general:      ()      => api.get('/settings/general'),
  logLevel:     ()      => api.get('/settings/log-level'),
  setLogLevel:  (data: unknown)  => api.post('/settings/log-level', data),
  // Runtime-flag groups (env → UI migration). See docs/CONFIG_MIGRATION_INVENTORY.md
  runtimeGroup: (group: any) => api.get(`/settings/runtime/${group}`),
  setRuntime:   (group: any, key: any, value: any) => api.put(`/settings/runtime/${group}/${key}`, { value: String(value) }),

  // Integration credentials (Phase 2 — encrypted per-org provider creds)
  integrations:        ()                     => api.get('/settings/integrations'),
  integrationProvider: (provider: any)             => api.get(`/settings/integrations/${provider}`),
  setIntegration:      (provider: any, key: any, value: any) => api.put(`/settings/integrations/${provider}/${key}`, { value: value == null ? '' : String(value) }),
  testIntegration:     (provider: any)             => api.post(`/settings/integrations/${provider}/test`),

  // Audit log (settings + credentials)
  auditLog: (params: unknown = {}) => api.get('/settings/audit-log', { params }),
}

// ── Semantic ──────────────────────────────────────────────────────────────────
export const semanticApi = {
  suggestTask:        (data: unknown) => api.post('/semantic/suggest/task', data),
  suggestTicket:      (data: unknown) => api.post('/semantic/suggest/ticket', data),
  estimateEffort:     (data: unknown) => api.post('/semantic/estimate/effort', data),
  estimateSprint:     (data: unknown) => api.post('/semantic/estimate/sprint-backlog', data),
  profiles:           () => api.get('/semantic/profiles'),
  createProfile:      (data: unknown) => api.post('/semantic/profiles', data),
  config:             () => api.get('/semantic/config'),
  updateConfig:       (data: unknown) => api.patch('/semantic/config', data),
  stats:              () => api.get('/semantic/stats'),
  autoGenerate:       () => api.post('/semantic/profiles/auto-generate'),
  rebuildEmbeddings:  () => api.post('/semantic/profiles/rebuild-embeddings'),
  recordAssignment:   (data: unknown) => api.post('/semantic/record-assignment', data),
}

// ── GRC ───────────────────────────────────────────────────────────────────────
export const grcApi = {
  permissions:      ()                           => api.get('/grc/permissions'),
  seedPermissions:  ()                           => api.post('/grc/permissions/seed'),
  updatePermission: (role: any, module: any, action: any, data: unknown) => api.patch(`/grc/permissions/${role}/${module}/${action}`, data),
  sodRules:         ()                           => api.get('/grc/sod-rules'),
  createSodRule:    (data: unknown)                       => api.post('/grc/sod-rules', data),
  updateSodRule:    (id: any, data: unknown)                   => api.patch(`/grc/sod-rules/${id}`, data),
  deleteSodRule:    (id: any)                         => api.delete(`/grc/sod-rules/${id}`),
  sodCheck:         ()                           => api.get('/grc/sod-check'),
  violations:       (params?: any)                     => api.get('/grc/violations', { params }),
  resolveViolation: (id: any, data: unknown)                   => api.patch(`/grc/violations/${id}/resolve`, data),
  auditLog:         (params?: any)                     => api.get('/grc/audit-log', { params }),
}

// ── Automations ───────────────────────────────────────────────────────────────
export const automationsApi = {
  list:       ()         => api.get('/automations'),
  templates:  ()         => api.get('/automations/templates/list'),
  create:     (data: unknown)     => api.post('/automations', data),
  update:     (id: any, data: unknown) => api.patch(`/automations/${id}`, data),
  delete:     (id: any)       => api.delete(`/automations/${id}`),
  test:       (id: any)       => api.post(`/automations/${id}/test`),
  executions: (id: any)       => api.get(`/automations/${id}/executions`),
  catalog:    ()         => api.get('/automations/catalog'),
}

export const autoWorkflowsApi = {
  list:   ()             => api.get('/automation-workflows'),
  update: (id: any, data: unknown)     => api.patch(`/automation-workflows/${id}`, data),
  delete: (id: any)           => api.delete(`/automation-workflows/${id}`),
}

export const workflowsLegacyApi = {
  list:   ()         => api.get('/billing-reports/automation-workflows'),
  create: (data: unknown)     => api.post('/billing-reports/automation-workflows', data),
  update: (id: any, data: unknown) => api.patch(`/billing-reports/automation-workflows/${id}`, data),
}

// ── Scheduled Reports ─────────────────────────────────────────────────────────
export const scheduledReportsApi = {
  list:   ()         => api.get('/billing-reports/scheduled-reports'),
  create: (data: unknown)     => api.post('/billing-reports/scheduled-reports', data),
  delete: (id: any)       => api.delete(`/billing-reports/scheduled-reports/${id}`),
  run:    (id: any)       => api.post(`/billing-reports/scheduled-reports/${id}/run`),
  toggle: (id: any, data: unknown) => api.patch(`/billing-reports/scheduled-reports/${id}`, data),
}

// ── AI Providers ──────────────────────────────────────────────────────────────
export const aiProvidersApi = {
  list:        ()         => api.get('/ai-providers'),
  catalog:     ()         => api.get('/ai-providers/catalog'),
  stats:       ()         => api.get('/ai-providers/stats'),
  diagnostics: ()         => api.get('/ai-providers/diagnostics'),
  create:      (data: unknown)     => api.post('/ai-providers', data),
  update:      (id: any, data: unknown) => api.patch(`/ai-providers/${id}`, data),
  delete:      (id: any)       => api.delete(`/ai-providers/${id}`),
  test:        (id: any)       => api.post(`/ai-providers/${id}/test`),
  syncModels:  (id: any)       => api.post(`/ai-providers/${id}/sync-models`),
  setDefault:  (id: any)       => api.post(`/ai-providers/${id}/set-default`),
  syncAll:     ()         => api.post('/ai-providers/sync-models/all'),
}

// ── Service Desk Config ───────────────────────────────────────────────────────
export const sdMetricsApi = {
  itil:             (params?: any) => api.get('/sd/metrics/itil', { params }),
  agentPerformance: (params?: any) => api.get('/sd/metrics/agent-performance', { params }),
}

export const sdCatalogApi = {
  list:           ()         => api.get('/sd/catalog'),
  get:            ()         => api.get('/sd/catalog'),
  createCategory: (data: unknown)     => api.post('/sd/catalog/categories', data),
  updateCategory: (id: any, data: unknown) => api.patch(`/sd/catalog/categories/${id}`, data),
  deleteCategory: (id: any)       => api.delete(`/sd/catalog/categories/${id}`),
  createService:  (data: unknown)     => api.post('/sd/catalog/services', data),
  updateService:  (id: any, data: unknown) => api.patch(`/sd/catalog/services/${id}`, data),
  deleteService:  (id: any)       => api.delete(`/sd/catalog/services/${id}`),
}

export const sdSlaPoliciesApi = {
  // Las dos rutas escritas enteras: el comprobador de rutas del frontal no
  // resuelve un segmento variable en medio («assign/${tipo}/…»).
  assign: (tipo: 'client' | 'contract', id: string, slaPolicyId: string | null) =>
    tipo === 'client'
      ? api.patch(`/sd/sla-policies/assign/client/${id}`, { sla_policy_id: slaPolicyId })
      : api.patch(`/sd/sla-policies/assign/contract/${id}`, { sla_policy_id: slaPolicyId }),
  list:   ()         => api.get('/sd/sla-policies'),
  create: (data: unknown)     => api.post('/sd/sla-policies', data),
  update: (id: any, data: unknown) => api.patch(`/sd/sla-policies/${id}`, data),
  delete: (id: any)       => api.delete(`/sd/sla-policies/${id}`),
}

export const sdEscalationApi = {
  list:   ()         => api.get('/sd/escalation-rules'),
  create: (data: unknown)     => api.post('/sd/escalation-rules', data),
  update: (id: string, data: unknown) => api.patch(`/sd/escalation-rules/${id}`, data),
  delete: (id: string)       => api.delete(`/sd/escalation-rules/${id}`),
  logs:   (limit = 20)       => api.get('/sd/escalation-rules/logs', { params: { limit } }),
}

export const sdNotificationTemplatesApi = {
  list:    ()                                   => api.get('/sd/notification-templates'),
  save:    (code: string, lang: string, data: unknown) => api.put(`/sd/notification-templates/${code}/${lang}`, data),
  restore: (code: string, lang: string)         => api.delete(`/sd/notification-templates/${code}/${lang}`),
  preview: (data: unknown)                      => api.post('/sd/notification-templates/preview', data),
}

export const sdChangePlanningApi = {
  calendar:        (desde: string, hasta: string) => api.get('/sd/change-calendar', { params: { desde, hasta } }),
  blackouts:       ()                       => api.get('/sd/change-blackouts'),
  createBlackout:  (data: unknown)          => api.post('/sd/change-blackouts', data),
  updateBlackout:  (id: string, data: unknown) => api.put(`/sd/change-blackouts/${id}`, data),
  deleteBlackout:  (id: string)             => api.delete(`/sd/change-blackouts/${id}`),
  releases:        ()                       => api.get('/sd/releases'),
  createRelease:   (data: unknown)          => api.post('/sd/releases', data),
  updateRelease:   (id: string, data: unknown) => api.put(`/sd/releases/${id}`, data),
  deleteRelease:   (id: string)             => api.delete(`/sd/releases/${id}`),
  cab:             (changeId: string | number) => api.get(`/sd/changes/${changeId}/cab/workflow`),
  vote:            (changeId: string | number, data: unknown) => api.post(`/sd/changes/${changeId}/cab/vote`, data),
}

export const sdOnCallApi = {
  schedules:      ()                          => api.get('/sd/oncall/schedules'),
  createSchedule: (data: unknown)             => api.post('/sd/oncall/schedules', data),
  deleteSchedule: (id: string)                => api.delete(`/sd/oncall/schedules/${id}`),
  addShift:       (scheduleId: string, data: unknown) => api.post(`/sd/oncall/schedules/${scheduleId}/entries`, data),
  deleteShift:    (id: string)                => api.delete(`/sd/oncall/entries/${id}`),
  current:        ()                          => api.get('/sd/oncall/current'),
}

export const sdMonitoringApi = {
  alerts: (limit = 30) => api.get('/sd/events/alerts', { params: { limit } }),
}

export const sdStatusPageApi = {
  link:            ()                    => api.get('/sd/status-page/link'),
  components:      ()                    => api.get('/sd/status-page/components'),
  createComponent: (data: unknown)       => api.post('/sd/status-page/components', data),
  updateComponent: (id: string, data: unknown) => api.patch(`/sd/status-page/components/${id}`, data),
  deleteComponent: (id: string)          => api.delete(`/sd/status-page/components/${id}`),
  declare:         (id: string, data: unknown) => api.post(`/sd/status-page/components/${id}/incidents`, data),
}

export const sdApprovalsApi = {
  mine:   ()                                  => api.get('/sd/approvals/mine'),
  decide: (ticketId: string, data: unknown)   => api.post(`/sd/tickets/${ticketId}/approval`, data),
}

export const sdInboundApi = {
  messages: (limit = 30) => api.get('/sd/inbound/messages', { params: { limit } }),
  test:     ()           => api.post('/sd/inbound/test'),
  run:      ()           => api.post('/sd/inbound/run'),
}

export const sdGroupsApi = {
  list:         ()         => api.get('/sd/groups'),
  create:       (data: unknown)     => api.post('/sd/groups', data),
  update:       (id: any, data: unknown) => api.patch(`/sd/groups/${id}`, data),
  delete:       (id: any)       => api.delete(`/sd/groups/${id}`),
  addMember:    (gid: any, uid: any) => api.post(`/sd/groups/${gid}/members/${uid}`),
  removeMember: (gid: any, uid: any) => api.delete(`/sd/groups/${gid}/members/${uid}`),
}

export const sdTemplatesApi = {
  list:   ()         => api.get('/sd/ticket-templates'),
  create: (data: unknown)     => api.post('/sd/ticket-templates', data),
  update: (id: any, data: unknown) => api.patch(`/sd/ticket-templates/${id}`, data),
  delete: (id: any)       => api.delete(`/sd/ticket-templates/${id}`),
}

export const sdCannedApi = {
  list:   (params?: any)   => api.get('/sd/canned-responses', { params }),
  create: (data: unknown)     => api.post('/sd/canned-responses', data),
  update: (id: any, data: unknown) => api.patch(`/sd/canned-responses/${id}`, data),
  delete: (id: any)       => api.delete(`/sd/canned-responses/${id}`),
}

export const sdAnnouncementsApi = {
  list:   ()     => api.get('/sd/announcements'),
  create: (data: unknown) => api.post('/sd/announcements', data),
  delete: (id: any)   => api.delete(`/sd/announcements/${id}`),
}

export const sdRoutingApi = {
  list:                ()         => api.get('/sd/routing-rules'),
  create:              (data: unknown)     => api.post('/sd/routing-rules', data),
  update:              (id: any, data: unknown) => api.patch(`/sd/routing-rules/${id}`, data),
  delete:              (id: any)       => api.delete(`/sd/routing-rules/${id}`),
  queue:               (params?: any)   => api.get('/sd/tickets/my-queue', { params }),
  tickets:             (params?: any)   => api.get('/sd/tickets', { params }),
  majorIncidents:      ()         => api.get('/sd/major-incidents'),
  createMajorIncident: (data: unknown)     => api.post('/sd/major-incidents', data),
}

export const sdKbApi = {
  list:        (params?: any)   => api.get('/sd/kb', { params }),
  create:      (data: unknown)     => api.post('/sd/kb', data),
  update:      (id: any, data: unknown) => api.patch(`/sd/kb/${id}`, data),
  delete:      (id: any)       => api.delete(`/sd/kb/${id}`),
  submit:      (id: any)       => api.post(`/sd/kb/${id}/submit`),
  review:      (id: any, data: unknown) => api.post(`/sd/kb/${id}/review`, data),
  knownErrors:        ()     => api.get('/sd/known-errors'),
  knownErrorTickets:  (id: any)   => api.get(`/sd/known-errors/${id}/tickets`),
}

// ── Enterprise ────────────────────────────────────────────────────────────────
export const webhooksApi = {
  list:   ()         => api.get('/webhooks'),
  create: (data: unknown)     => api.post('/webhooks', data),
  delete: (id: any)       => api.delete(`/webhooks/${id}`),
  logs:   (id: any)       => api.get(`/webhooks/${id}/logs`),
}

export const gdprApi = {
  list:    ()     => api.get('/gdpr/requests'),
  create:  (data: unknown) => api.post('/gdpr/requests', data),
  process: (id: any)   => api.post(`/gdpr/requests/${id}/process`),
}

export const emailApi = {
  catalog:        ()     => api.get('/email/templates'),
  logs:           ()     => api.get('/email/logs'),
  send:           (data: unknown) => api.post('/email/send', data),
  createTemplate: (data: unknown) => api.post('/email/templates', data),
}

export const oauthIntegrationsApi = {
  list:   ()             => api.get('/oauth-integrations'),
  create: (data: unknown)         => api.post('/oauth-integrations', data),
  delete: (id: any)           => api.delete(`/oauth-integrations/${id}`),
  sync:   (id: any, data: unknown)     => api.post(`/oauth-integrations/${id}/sync`, data),
}

export const enterpriseApi = {
  auditLog:                (params?: any) => api.get('/enterprise/audit-log', { params }),
  ssoList:                 ()       => api.get('/enterprise/sso'),
  ssoCreate:               (data: unknown)   => api.post('/enterprise/sso', data),
  ssoUpdate:               (id: any, data: unknown) => api.patch(`/enterprise/sso/${id}`, data),
  ssoDelete:               (id: any)     => api.delete(`/enterprise/sso/${id}`),
  ssoTest:                 (id: any)     => api.post(`/enterprise/sso/${id}/test`),
  notifications:           (params?: any) => api.get('/enterprise/notifications', { params }),
  markNotificationRead:    (id: any)     => api.post(`/enterprise/notifications/${id}/read`),
  markAllNotificationsRead:()       => api.post('/enterprise/notifications/read-all'),
  clearOldNotifications:  (params?: any)  => api.delete('/enterprise/notifications/clear-old', { params }),
}

export const integrationsHubApi = {
  testSlack:  (data: unknown) => api.post('/integrations-hub/slack/test', data),
  testTeams:  (data: unknown) => api.post('/integrations-hub/teams/test', data),
  testJira:   (data: unknown) => api.post('/integrations-hub/jira/test', data),
}

export const apiKeysApi = {
  list:   ()         => api.get('/bookings/api-keys'),
  create: (data: unknown)     => api.post('/bookings/api-keys', data),
  delete: (id: any)       => api.delete(`/bookings/api-keys/${id}`),
}

// ── Client Portal ─────────────────────────────────────────────────────────────
export const portalApi = {
  clients:              (params?: any)          => api.get('/portal/clients', { params }),
  createClient:         (data: unknown)            => api.post('/portal/clients', data),
  updateClient:         (id: any, data: unknown)        => api.patch(`/portal/clients/${id}`, data),
  deleteClient:         (id: any)              => api.delete(`/portal/clients/${id}`),
  uat:                  (params?: any)          => api.get('/portal/uat/team', { params }),
  createUat:            (projectId: any, data: unknown) => api.post(`/portal/uat/${projectId}`, data),
  addTestCase:          (id: any, data: unknown)        => api.post(`/portal/uat/${id}/test-cases`, data),
  updateUatStatus:      (id: any, params?: any)      => api.patch(`/portal/uat/issues/${id}`, null, { params }),
  featureRequests:      (params?: any)          => api.get('/portal/feature-requests/team', { params }),
  respondFeatureRequest:(id: any, data: unknown)        => api.post(`/portal/feature-requests/${id}/respond`, data),
  documents:            (params?: any)          => api.get('/portal/documents/team', { params }),
  createDocument:       (projectId: any, data: unknown) => api.post('/portal/documents', data, { params: { project_id: projectId } }),
  stats:                (projectId: any)       => api.get(`/portal/stats/${projectId}`),
  translations:         ()               => api.get('/portal/translations'),
  saveTranslations:     (data: unknown)           => api.post('/portal/translations', data),
}

// ── Client Extensions ─────────────────────────────────────────────────────────
export const clientExtApi = {
  projects:           (cid: any)       => api.get(`/clients/${cid}/projects`),
  availableProjects:  (cid: any)       => api.get(`/clients/${cid}/projects/available`),
  linkProject:        (cid: any, pid: any)  => api.post(`/clients/${cid}/projects/${pid}/link`),
  unlinkProject:      (cid: any, pid: any)  => api.delete(`/clients/${cid}/projects/${pid}/link`),
  contacts:           (cid: any)       => api.get(`/clients/${cid}/contacts`),
  createContact:      (cid: any, data: unknown) => api.post(`/clients/${cid}/contacts`, data),
  deleteContact:      (cid: any, id: any)   => api.delete(`/clients/${cid}/contacts/${id}`),
  licenses:           (cid: any)       => api.get(`/clients/${cid}/licenses`),
  linkLicense:        (cid: any, data: unknown) => api.post(`/clients/${cid}/licenses`, data),
  unlinkLicense:      (cid: any, id: any)   => api.delete(`/clients/${cid}/licenses/${id}`),
  contracts:          (cid: any)       => api.get(`/clients/${cid}/contracts`),
  linkContract:       (cid: any, data: unknown) => api.post(`/clients/${cid}/contracts`, data),
  unlinkContract:     (cid: any, id: any)   => api.delete(`/clients/${cid}/contracts/${id}`),
  portalConfig:       (cid: any)       => api.get(`/clients/${cid}/portal-config`),
  updatePortalConfig: (cid: any, data: unknown) => api.patch(`/clients/${cid}/portal-config`, data),
}

// ── SLA Calendars ─────────────────────────────────────────────────────────────
export const slaCalendarsApi = {
  list:          () => api.get('/cmdb/sla-calendars'),
  create:        (data: unknown) => api.post('/cmdb/sla-calendars', data),
  update:        (id: any, data: unknown) => api.patch(`/cmdb/sla-calendars/${id}`, data),
  delete:        (id: any) => api.delete(`/cmdb/sla-calendars/${id}`),
  holidays:      (calId: any) => api.get(`/cmdb/sla-calendars/${calId}/holidays`),
  createHoliday: (calId: any, data: unknown) => api.post(`/cmdb/sla-calendars/${calId}/holidays`, data),
  updateHoliday: (calId: any, id: any, data: unknown) => api.patch(`/cmdb/sla-calendars/${calId}/holidays/${id}`, data),
  deleteHoliday: (calId: any, id: any) => api.delete(`/cmdb/sla-calendars/${calId}/holidays/${id}`),
  checkDate:     (calId: any, date: any) => api.get(`/cmdb/sla-calendars/${calId}/check-date?check_date=${date}`),
}

// ── Project Workflows ─────────────────────────────────────────────────────────
export const projectWorkflowsApi = {
  get:              (projectId: any) => api.get(`/project-workflows/${projectId}`),
  init:             (projectId: any) => api.post(`/project-workflows/${projectId}/init`),
  createState:      (projectId: any, data: unknown) => api.post(`/project-workflows/${projectId}/states`, data),
  updateState:      (projectId: any, stateId: any, data: unknown) => api.patch(`/project-workflows/${projectId}/states/${stateId}`, data),
  deleteState:      (projectId: any, stateId: any) => api.delete(`/project-workflows/${projectId}/states/${stateId}`),
  createTransition: (projectId: any, data: unknown) => api.post(`/project-workflows/${projectId}/transitions`, data),
  deleteTransition: (projectId: any, transId: any) => api.delete(`/project-workflows/${projectId}/transitions/${transId}`),
  transitionTask:   (projectId: any, taskId: any, data: unknown) => api.post(`/project-workflows/${projectId}/tasks/${taskId}/transition`, data),
  resetWorkflow:    (projectId: any) => api.delete(`/project-workflows/${projectId}/reset`),
}

// ── Sprint Plans ──────────────────────────────────────────────────────────────
export const sprintPlansApi = {
  generate:     (data: unknown) => api.post('/cmdb/sprint-plans/generate', data),
  get:          (projectId: any) => api.get(`/cmdb/sprint-plans/${projectId}`),
  updateStatus: (id: any, status: any) => api.patch(`/cmdb/sprint-plans/${id}/status?status=${status}`),
  delete:       (id: any) => api.delete(`/cmdb/sprint-plans/${id}`),
}

// ── Organizations ─────────────────────────────────────────────────────────────
export const organizationsApi = {
  list:       () => api.get('/organizations'),
  get:        (id: any) => api.get(`/organizations/${id}`),
  create:     (data: unknown) => api.post('/organizations', data),
  update:     (id: any, data: unknown) => api.patch(`/organizations/${id}`, data),
  assignUser: (orgId: any, data: unknown) => api.post(`/organizations/${orgId}/assign-user`, data),
  removeUser: (orgId: any, userId: any) => api.delete(`/organizations/${orgId}/remove-user/${userId}`),
}

// ── Templates ─────────────────────────────────────────────────────────────────
export const templatesApi = {
  list:        () => api.get('/billing-reports/templates'),
  create:      (data: unknown) => api.post('/billing-reports/templates', data),
  instantiate: (tplId: any, data: unknown) => api.post(`/billing-reports/templates/${tplId}/instantiate`, data),
}

// ── Dependencies ──────────────────────────────────────────────────────────────
// El router real es /task-dependencies. Con el prefijo equivocado la consulta
// daba 404 y el Gantt de proyecto se dibujaba SIN dependencias, sin error
// visible: la pagina trata la respuesta fallida como lista vacia. Auditoria
// 2026-08 (#37).
export const dependenciesApi = {
  get: (projectId: any) => api.get(`/task-dependencies/${projectId}`),
}

// ── Jira Integration ─────────────────────────────────────────────────────────
export const jiraApi = {
  config:     () => api.get('/jira/config'),
  saveConfig: (data: unknown) => api.post('/jira/config', data),
  issues:     () => api.get('/jira/issues'),
  linked:     () => api.get('/jira/linked'),
  test:       () => api.get('/jira/test'),
  sync:       (data: unknown) => api.post('/jira/sync', data),
  push:       () => api.post('/jira/push'),
}

// ── SD Workflow Designer ──────────────────────────────────────────────────────
export const sdWorkflowDesignerApi = {
  schema:         () => api.get('/sd/workflow-designer/schema'),
  templates:      () => api.get('/sd/workflow-designer/templates'),
  blueprints:     (params?: any) => api.get('/sd/workflow-designer/blueprints', { params }),
  blueprint:      (id: any) => api.get(`/sd/workflow-designer/blueprints/${id}`),
  createBlueprint:(data: unknown) => api.post('/sd/workflow-designer/blueprints', data),
  createVersion:  (id: any, data: unknown) => api.post(`/sd/workflow-designer/blueprints/${id}/versions`, data),
  publish:        (id: any, version: any) => api.post(`/sd/workflow-designer/blueprints/${id}/publish/${version}`),
  validate:       (data: unknown) => api.post('/sd/workflow-designer/validate', data),
  clone:          (id: any, data: unknown) => api.post(`/sd/workflow-designer/blueprints/${id}/clone`, data),
  archive:        (id: any) => api.delete(`/sd/workflow-designer/blueprints/${id}`),
  // Runtime
  startRun:       (id: any, data: unknown) => api.post(`/sd/workflow-designer/blueprints/${id}/runs`, data),
  runs:           (params?: any) => api.get('/sd/workflow-designer/runs', { params }),
  run:            (rid: any) => api.get(`/sd/workflow-designer/runs/${rid}`),
  resumeRun:      (rid: any, data: unknown) => api.post(`/sd/workflow-designer/runs/${rid}/resume`, data),
  cancelRun:      (rid: any, reason: any) => api.post(`/sd/workflow-designer/runs/${rid}/cancel`, { reason }),
}

// ── Mentions & Comments ───────────────────────────────────────────────────────
export const mentionsApi = {
  comments:           (entityType: any, entityId: any) => api.get('/epics/comments', { params: { entity_type: entityType, entity_id: entityId } }),
  createComment:      (entityType: any, entityId: any, data: unknown) => api.post('/epics/comments', data, { params: { entity_type: entityType, entity_id: entityId } }),
  resolveComment:     (id: any) => api.patch(`/epics/comments/${id}/resolve`),
  deleteComment:      (id: any) => api.delete(`/epics/comments/${id}`),
  mentions:           (onlyUnread: any) => api.get('/activity/mentions/my', { params: { unread_only: onlyUnread } }),
  markMentionRead:    (id: any) => api.post(`/activity/mentions/${id}/read`),
  markAllMentionsRead:() => api.post('/epics/mentions/read-all'),
}

// ── Issue Types ───────────────────────────────────────────────────────────────
export const issueTypesApi = {
  list:   (projectId: any) => api.get(`/issue-types/${projectId}`),
  create: (projectId: any, data: unknown) => api.post(`/issue-types/${projectId}`, data),
  update: (projectId: any, id: any, data: unknown) => api.patch(`/issue-types/${projectId}/${id}`, data),
  init:   (projectId: any) => api.post(`/issue-types/${projectId}/init`),
  delete: (projectId: any, id: any) => api.delete(`/issue-types/${projectId}/${id}`),
}

// ── Project Permissions ───────────────────────────────────────────────────────
export const permissionsApi = {
  list:   (projectId: any) => api.get(`/permissions/${projectId}`),
  create: (projectId: any, data: unknown) => api.post(`/permissions/${projectId}`, data),
  update: (projectId: any, id: any, data: unknown) => api.patch(`/permissions/${projectId}/${id}`, data),
  delete: (projectId: any, id: any) => api.delete(`/permissions/${projectId}/${id}`),
}

// ── eSign ─────────────────────────────────────────────────────────────────────
export const esignApi = {
  list:        () => api.get('/esign'),
  stats:       () => api.get('/esign/summary/stats'),
  create:      (data: unknown) => api.post('/esign', data),
  delete:      (id: any) => api.delete(`/esign/${id}`),
  sign:        (envelopeId: any, signerId: any) => api.patch(`/esign/${envelopeId}/signers/${signerId}/signed`),
  getConfig:   () => api.get('/esign/config'),
  saveConfig:  (data: unknown) => api.patch('/esign/config', data),
}

// ── Public Forms ──────────────────────────────────────────────────────────────
export const formsApi = {
  list:        () => api.get('/forms'),
  create:      (data: unknown) => api.post('/forms', data),
  update:      (id: any, data: unknown) => api.patch(`/forms/${id}`, data),
  submissions: (id: any) => api.get(`/forms/${id}/submissions`),
  delete:      (id: any) => api.delete(`/forms/${id}`),
}

// ── Resource Scheduler ────────────────────────────────────────────────────────
export const resourceForecastApi = {
  weeks: (params?: any) => api.get('/resource-forecast/weeks', { params }),
}

export const bookingsApi = {
  list:   (params?: any) => api.get('/bookings', { params }),
  create: (data: unknown) => api.post('/bookings', data),
  update: (id: any, data: unknown) => api.patch(`/bookings/${id}`, data),
  delete: (id: any) => api.delete(`/bookings/${id}`),
}

// ── Scenarios ─────────────────────────────────────────────────────────────────
export const scenariosApi = {
  list:    () => api.get('/scenarios'),
  get:     (id: any) => api.get(`/scenarios/${id}`),
  create:  (data: unknown) => api.post('/scenarios', data),
  compute: (id: any) => api.post(`/scenarios/${id}/compute`),
  delete:  (id: any) => api.delete(`/scenarios/${id}`),
}

// ── Governance ────────────────────────────────────────────────────────────────
export const governanceApi = {
  config:  () => api.get('/governance/config'),
  stats:   () => api.get('/governance/stats'),
  logs:    () => api.get('/governance/logs?limit=100'),
  update:  (module: any, data: unknown) => api.patch(`/governance/config/${module}`, data),
}

// ── Epic Dependencies ─────────────────────────────────────────────────────────
export const epicDependenciesApi = {
  get:    (projectId: any) => api.get(`/epic-dependencies/${projectId}`),
  create: (data: unknown) => api.post('/epic-dependencies', data),
  delete: (id: any) => api.delete(`/epic-dependencies/${id}`),
}

// ── Developer Apps ────────────────────────────────────────────────────────────
export const developerAppsApi = {
  list:         () => api.get('/developer/apps'),
  create:       (data: unknown) => api.post('/developer/apps', data),
  update:       (id: any, data: unknown) => api.patch(`/developer/apps/${id}`, data),
  rotateSecret: (id: any) => api.post(`/developer/apps/${id}/rotate-secret`),
  delete:       (id: any) => api.delete(`/developer/apps/${id}`),
}

// ── Task Dependencies ─────────────────────────────────────────────────────────
export const taskDependenciesApi = {
  getByProject: (projectId: any) => api.get(`/tasks/dependencies/${projectId}`),
  create:       (data: unknown) => api.post('/tasks/dependencies', data),
  delete:       (id: any) => api.delete(`/tasks/dependencies/${id}`),
  bulkDates:    (updates: unknown) => api.post('/tasks/bulk-dates', { updates }),
}

// ── Budgets ───────────────────────────────────────────────────────────────────
export const budgetsApi = {
  list:        (year: any) => api.get('/budgets', { params: { year } }),
  summary:     (year: any) => api.get('/budgets/summary', { params: { year } }),
  create:      (data: unknown) => api.post('/budgets', data),
  updateEntry: (id: any, month: any, data: unknown) => api.patch(`/budgets/${id}/entry`, { month, ...(data as Record<string, unknown>) }),
  approve:     (id: any) => api.post(`/budgets/${id}/approve`),
}

// ── SD Major Incidents ────────────────────────────────────────────────────────
export const sdMajorIncidentsApi = {
  list:   () => api.get('/sd/major-incidents'),
  create: (data: unknown) => api.post('/sd/major-incidents', data),
}

// ── Risk Scores ───────────────────────────────────────────────────────────────
export const riskScoresApi = {
  list:    (params?: any) => api.get('/risk-scores', { params }),
  get:     (id: any) => api.get(`/risk-scores/${id}`),
  refresh: () => api.get('/risk-scores', { params: { refresh: true } }),
}

// ── M365 ──────────────────────────────────────────────────────────────────────
export const m365Api = {
  status:         () => api.get('/m365/status'),
  syncCalendar:   (upn: any, days: any) => api.post('/m365/calendar/sync', null, { params: { user_upn: upn, days } }),
  syncMilestones: (data: unknown) => api.post('/m365/calendar/sync-milestones', data),
  teamsNotify:    (data: unknown) => api.post('/m365/teams/notify', data),
}

// ── Meetings AI ───────────────────────────────────────────────────────────────
export const meetingsAIApi = {
  list:        () => api.get('/ai-modules/meetings'),
  get:         (id: any) => api.get(`/ai-modules/meetings/${id}`),
  process:     (data: unknown) => api.post('/ai-modules/meetings/process', data),
  createTasks: (id: any) => api.post(`/ai-modules/meetings/${id}/create-tasks`, {}),
}

// ── Contracts AI (H22) ────────────────────────────────────────────────────────
export const contractsAIApi = {
  list:       (params?: any) => api.get('/ai-modules/contracts-ai', { params }),
  get:        (id: any)     => api.get(`/ai-modules/contracts-ai/${id}`),
  analyze:    (data: unknown)   => api.post('/ai-modules/contracts-ai/analyze', data),
  analyzePdf: (formData: unknown) => api.post('/ai-modules/contracts-ai/analyze-pdf', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
}

// ── Voice commands (I25) ──────────────────────────────────────────────────────
// /voice/transcribe → multipart audio, devuelve {whisper_transcript, intent,
//                       entities, action, pending_action?}  (dry-run forzado)
// /voice/command    → JSON {transcript, confirm: true} → ejecuta la acción
export const voiceApi = {
  transcribe: (formData: unknown) => api.post('/ai-modules/voice/transcribe', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  command:    (data: unknown) => api.post('/ai-modules/voice/command', data),
}

// ── Smart Schedule (I27) ──────────────────────────────────────────────────────
// Devuelve sugerencias de planificación; aplicar selectivamente vía
// taskDependenciesApi.bulkDates(updates) o tasksApi.bulkUpdate.
export const smartScheduleApi = {
  suggest: (data: unknown) => api.post('/ai-modules/smart-schedule', data),
}

// ── MFA ───────────────────────────────────────────────────────────────────────
export const mfaApi = {
  status: () => api.get('/mfa/status'),
  setup:  () => api.post('/mfa/setup'),
  verify: (code: any) => api.post('/mfa/verify', { code }),
  disable:(code: any) => api.delete('/mfa/disable', { data: { code } }),
}

// ── Oracle Predictions ────────────────────────────────────────────────────────
export const oracleApi = {
  predictions: (params?: any) => api.get('/oracle/predictions', { params }),
  run:         () => api.post('/oracle/run'),
  acknowledge: (id: any) => api.post(`/oracle/predictions/${id}/acknowledge`),
}

// ── Import ────────────────────────────────────────────────────────────────────
export const importApi = {
  template: (entityType: any) => api.get(`/billing-reports/import/template/${entityType}`),
  jobs:     () => api.get('/billing-reports/import/jobs'),
  validate: (entityType: any, fd: unknown) => api.post('/billing-reports/import/validate', fd, { params: { entity_type: entityType }, headers: { 'Content-Type': 'multipart/form-data' } }),
  execute:  (entityType: any, fd: unknown) => api.post('/billing-reports/import/execute', fd, { params: { entity_type: entityType }, headers: { 'Content-Type': 'multipart/form-data' } }),
}

// ── Report Builder ────────────────────────────────────────────────────────────
export const reportBuilderApi = {
  schema:         () => api.get('/reports/schema'),
  preview:        (data: unknown) => api.post('/reports/preview', data),
  export:         (data: unknown, config: any) => api.post('/reports/export', data, config),
  templates:      () => api.get('/reports/templates'),
  saveTemplate:   (data: unknown) => api.post('/reports/templates', data),
  deleteTemplate: (id: any) => api.delete(`/reports/templates/${id}`),
}

// ── Burnout Risk / Resources ──────────────────────────────────────────────────
export const burnoutRiskApi = {
  get:     (params?: any) => api.get('/resources/burnout-risk', { params }),
  compute: () => api.post('/resources/burnout-risk/compute'),
}

// ── Git ───────────────────────────────────────────────────────────────────────
export const gitApi = {
  pullRequests: () => api.get('/git/pull-requests'),
  deployments:  () => api.get('/git/deployments'),
}

// ── Settings Admin ────────────────────────────────────────────────────────────
export const settingsAdminApi = {
  getLogLevel: () => api.get('/settings/log-level'),
  setLogLevel: (data: unknown) => api.post('/settings/log-level', data),
  getOrgDefaults: () => api.get('/settings/org-defaults'),
}

// ── Billing Smart Match ───────────────────────────────────────────────────────
export const billingSmartMatchApi = {
  match: (data: unknown) => api.post('/billing-reports/smartmatch', data),
}

// ── User Costs (cost-per-hour, salary, employer cost) ────────────────────────
export const userCostsApi = {
  // Country presets
  listCountries:    ()         => api.get('/user-costs/countries'),
  upsertCountry:    (data: unknown)     => api.post('/user-costs/countries', data),
  seedCountries:    (force: any)    => api.post('/user-costs/countries/seed', null, { params: { force: !!force } }),
  updateCountry:    (id: any, d: unknown)    => api.patch(`/user-costs/countries/${id}`, d),
  deleteCountry:    (id: any)       => api.delete(`/user-costs/countries/${id}`),
  // User profiles
  listProfiles:     (uid: any)      => api.get(`/user-costs/users/${uid}/profiles`),
  createProfile:    (uid: any, d: unknown)   => api.post(`/user-costs/users/${uid}/profiles`, d),
  active:           (uid: any, on: any)  => api.get(`/user-costs/users/${uid}/active`, { params: { on } }),
  preview:          (uid: any, d: unknown)   => api.post(`/user-costs/users/${uid}/preview`, d),
  updateProfile:    (id: any, d: unknown)    => api.patch(`/user-costs/profiles/${id}`, d),
  deleteProfile:    (id: any)       => api.delete(`/user-costs/profiles/${id}`),
  // Bulk summary
  summary:          (on: any)       => api.get('/user-costs/summary', { params: { on } }),
}

// ── BPMN Processes ────────────────────────────────────────────────────────────
export const bpmnProcessesApi = {
  list:        (params?: any)        => api.get('/bpmn-processes', { params }),
  catalogue:   ()              => api.get('/bpmn-processes/catalogue'),
  seed:        (force: boolean = false) => api.post('/bpmn-processes/seed', { force }),
  get:         (id: any)            => api.get(`/bpmn-processes/${id}`),
  create:      (data: unknown)          => api.post('/bpmn-processes', data),
  update:      (id: any, data: unknown)      => api.patch(`/bpmn-processes/${id}`, data),
  delete:      (id: any)            => api.delete(`/bpmn-processes/${id}`),
  duplicate:   (id: any, name: any)      => api.post(`/bpmn-processes/${id}/duplicate`, { new_name: name }),
  saveVersion: (id: any, xml: any, n: any)    => api.post(`/bpmn-processes/${id}/versions`, { bpmn_xml: xml, notes: n }),
  versions:    (id: any)            => api.get(`/bpmn-processes/${id}/versions`),
  getVersion:  (id: any, v: any)         => api.get(`/bpmn-processes/${id}/versions/${v}`),
  publish:     (id: any, v: any)         => api.post(`/bpmn-processes/${id}/versions/${v}/publish`),
  start:       (id: any, variables: Record<string, unknown> = {}) => api.post(`/bpmn-processes/${id}/instances`, { variables }),
}

// Auditoría 2026-11: motor BPMN (instancias y bandeja de pasos humanos).
export const bpmnInstancesApi = {
  list:     (params?: any)  => api.get('/bpmn-instances', { params }),
  inbox:    ()              => api.get('/bpmn-instances/inbox'),
  get:      (id: any)       => api.get(`/bpmn-instances/${id}`),
  complete: (id: any, stepId: any, variables: Record<string, unknown> = {}) => api.post(`/bpmn-instances/${id}/steps/${stepId}/complete`, { variables }),
  cancel:   (id: any)       => api.post(`/bpmn-instances/${id}/cancel`),
}

// ── Nexus AI Agent ────────────────────────────────────────────────────────────
export const nexusAgentApi = {
  history:              () => api.get('/ai/agent/history'),
  run:                  (instruction: any, autoApprove: boolean = true) => api.post('/ai/agent', { instruction, auto_approve: autoApprove }),
  chat:                 (data: unknown) => api.post('/ai/chat', data),
  listConversations:    () => api.get('/ai/conversations'),
  getConversation:      (id: any) => api.get(`/ai/conversations/${id}`),
  deleteConversations:  () => api.delete('/ai/conversations'),
}

// ── Resources ─────────────────────────────────────────────────────────────────
export const resourcesApi = {
  loadScoring: (params?: any) => api.get('/resources/load-scoring', { params }),
  teamHealth:  (params?: any) => api.get('/resources/team-health', { params }),
}

// ── Global Search ─────────────────────────────────────────────────────────────
export const searchApi = {
  search: (params?: any) => api.get('/global-search', { params }),
}

// ── Onboarding ────────────────────────────────────────────────────────────────
export const onboardingApi = {
  get:           () => api.get('/onboarding'),
  completeStep:  (data: unknown) => api.post('/onboarding/complete-step', data),
  dismiss:       () => api.post('/onboarding/dismiss'),
}

// ── SLA Schedules ─────────────────────────────────────────────────────────────
// El router real vive bajo /bookings. `update` y `delete` de un calendario no
// existen en el backend —solo alta, listado y las excepciones de festivos— y
// nadie los llamaba, asi que se quitan en vez de dejarlos apuntando a nada.
export const slaSchedulesApi = {
  list:   (params?: any) => api.get('/bookings/sla-schedules', { params }),
  create: (data: unknown)   => api.post('/bookings/sla-schedules', data),
  calculateDeadline: (data: unknown) => api.post('/bookings/sla-schedules/calculate-deadline', data),
}

// ── Auto-Resolution ───────────────────────────────────────────────────────────
export const autoResolutionApi = {
  getConfig:    ()          => api.get('/sd/auto-resolution/config'),
  getStats:     ()          => api.get('/sd/auto-resolution/stats'),
  patchConfig:  (data: unknown)      => api.patch('/sd/auto-resolution/config', data),
  runJob:       (params?: any)    => api.post('/sd/auto-resolution/run-job', null, { params }),
  runCloseJob:  ()          => api.post('/sd/auto-resolution/run-close-job'),
}

// ── Alert Clusters ────────────────────────────────────────────────────────────
export const alertClustersApi = {
  list:     ()      => api.get('/sd/alert-clusters'),
  stats:    ()      => api.get('/sd/alert-clusters/stats'),
  merge:    (data: unknown)  => api.post('/sd/alert-clusters/merge', data),
  runScan:  ()      => api.post('/sd/alert-clusters/run-scan'),
}

// ── Portal Conversation Policies ──────────────────────────────────────────────
export const portalConversationsApi = {
  getPolicies:    ()                      => api.get('/portal/conversations/team/policies'),
  updatePolicy:   (topicType: any, data: unknown)       => api.put(`/portal/conversations/team/policies/${topicType}`, data),
  reviewMessage:  (convId: any, msgId: any, data: unknown)   => api.post(`/portal/conversations/team/${convId}/messages/${msgId}/review`, data),
}

/** Normalise a Pydantic v2 / FastAPI error detail to a plain string.
 *  detail can be an array of {type,loc,msg,input,url} objects or a plain string. */
export function apiErrorMsg(e: any, fallback = 'Error') {
  const raw = e?.response?.data?.detail
  if (Array.isArray(raw)) return raw.map(d => d.msg).join(', ')
  return raw || e?.message || fallback
}
