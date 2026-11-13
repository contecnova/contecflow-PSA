import axios, { type AxiosError, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import type { Client, ClientContact, Contract, Epic, RiesgosDelProyecto, Risk, Sprint } from './tipos'
import { API_BASE_URL } from './urls'
import { ESCALATION_LOGS_LIMIT, GOVERNANCE_LOGS_LIMIT, INBOUND_MESSAGES_LIMIT, MONITORING_ALERTS_LIMIT } from '../../constants/pagination'

const BASE_URL = API_BASE_URL

/** Identificador o segmento que se interpola en la ruta (UUID, código, año...). */
export type PathId = string | number
/** Parámetros de query: axios los serializa tal cual. */
export type QueryParams = Record<string, unknown>
/** Error de una llamada al cliente: axios con el cuerpo de error de FastAPI. */
export type ApiError = AxiosError<{ detail?: string }>

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

/** Refresca la sesión (cookie httpOnly). Comparte la petición en vuelo. */
function refrescarSesion(): Promise<unknown> {
  if (!_refreshPromise) {
    _refreshPromise = axios
      .post(`${BASE_URL}/auth/refresh`, null, { withCredentials: true })
      .finally(() => { _refreshPromise = null })
  }
  return _refreshPromise
}

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
        await refrescarSesion()
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


/**
 * Petición con `fetch` para lo que axios no da en el navegador: leer la
 * respuesta como flujo (SSE sobre POST). Mismo contrato que el cliente: base
 * URL, cookies, cabecera CSRF en métodos que escriben y un reintento tras
 * refrescar la sesión si llega un 401. Devuelve la `Response` sin consumir:
 * quien llama comprueba `ok` y lee `body`.
 */
export async function apiStream(
  path: string,
  init: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<Response> {
  const method = (init.method || 'POST').toUpperCase()
  const pedir = () => {
    const headers: Record<string, string> = {}
    let body: BodyInit | undefined
    if (init.body instanceof FormData) body = init.body
    else if (init.body !== undefined) {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(init.body)
    }
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
      const csrf = _readCookie('csrf_token')
      if (csrf) headers['X-CSRF-Token'] = csrf
    }
    // Única llamada a fetch del cliente: axios no expone el cuerpo como flujo en el navegador.
    return fetch(`${BASE_URL}${path}`, { method, headers, body, credentials: 'include', signal: init.signal })
  }
  const resp = await pedir()
  if (resp.status !== 401) return resp
  try {
    await refrescarSesion()
  } catch {
    window.dispatchEvent(new CustomEvent('auth:session-expired'))
    return resp
  }
  return pedir()
}

// ── Rate Cards ────────────────────────────────────────────────────────────────
export const rateCardsApi = {
  list:            ()         => api.get('/rate-cards'),
  get:             (id: PathId)       => api.get(`/rate-cards/${id}`),
  create:          (d: unknown)        => api.post('/rate-cards', d),
  update:          (id: PathId, d: unknown)    => api.patch(`/rate-cards/${id}`, d),
  delete:          (id: PathId)       => api.delete(`/rate-cards/${id}`),
  duplicate:       (id: PathId, d: unknown)    => api.post(`/rate-cards/${id}/duplicate`, d),
  addEntry:        (id: PathId, d: unknown)    => api.post(`/rate-cards/${id}/entries`, d),
  updateEntry:     (id: PathId,eid: PathId,d: unknown) => api.patch(`/rate-cards/${id}/entries/${eid}`, d),
  deleteEntry:     (id: PathId,eid: PathId)   => api.delete(`/rate-cards/${id}/entries/${eid}`),
  effectiveRate:   (params?: QueryParams)   => api.get('/rate-cards/effective', { params }),
}

// ── Milestones (SOW flow) ─────────────────────────────────────────────────────
export const milestonesApi = {
  list:            (projectId: PathId) => api.get(`/milestones/project/${projectId}`),
  create:          (pid: PathId, d: unknown)    => api.post(`/milestones/project/${pid}`, d),
  update:          (id: PathId, d: unknown)     => api.patch(`/milestones/${id}`, d),
  delete:          (id: PathId)        => api.delete(`/milestones/${id}`),
  complete:        (id: PathId)        => api.post(`/milestones/${id}/complete`),
  uncomplete:      (id: PathId)        => api.post(`/milestones/${id}/uncomplete`),
  requestApproval: (id: PathId, d: unknown)     => api.post(`/milestones/${id}/request-approval`, d || {}),
  approve:         (id: PathId, d: unknown)     => api.post(`/milestones/${id}/approve`, d),
  generateInvoice: (id: PathId)        => api.post(`/milestones/${id}/generate-invoice`),
  dashboard:       ()          => api.get('/milestones/dashboard/pending'),
}

// ── Resource Forecast ─────────────────────────────────────────────────────────
export const forecastApi = {
  heatmap:      (params?: QueryParams) => api.get('/resource-forecast/weeks',        { params }),
  userDetail:   (uid: PathId, p: QueryParams) => api.get(`/resource-forecast/users/${uid}`, { params: p }),
  availability: (params?: QueryParams) => api.get('/resource-forecast/availability',  { params }),
  summary:      (params?: QueryParams) => api.get('/resource-forecast/summary',       { params }),
}

// ── Approvals ─────────────────────────────────────────────────────────────────
export const approvalsApi = {
  listWorkflows:     (params?: QueryParams)      => api.get('/approvals/workflows', { params }),
  listTemplates:     ()            => api.get('/approvals/workflow-templates'),
  getWorkflow:       (id: PathId)          => api.get(`/approvals/workflows/${id}`),
  createWorkflow:    (d: unknown)           => api.post('/approvals/workflows', d),
  createFromTemplate:(d: unknown)           => api.post('/approvals/workflows/from-template', d),
  updateWorkflow:    (id: PathId, d: unknown)       => api.patch(`/approvals/workflows/${id}`, d),
  validateWorkflow:  (id: PathId)          => api.get(`/approvals/workflows/${id}/validate`),
  publishWorkflow:   (id: PathId)          => api.post(`/approvals/workflows/${id}/publish`),
  cloneVersion:      (id: PathId, d: unknown)       => api.post(`/approvals/workflows/${id}/clone-version`, d || {}),
  deleteWorkflow:    (id: PathId)          => api.delete(`/approvals/workflows/${id}`),
  addStep:           (wid: PathId, d: unknown)      => api.post(`/approvals/workflows/${wid}/steps`, d),
  updateStep:        (wid: PathId, sid: PathId, d: unknown) => api.patch(`/approvals/workflows/${wid}/steps/${sid}`, d),
  deleteStep:        (wid: PathId, sid: PathId)    => api.delete(`/approvals/workflows/${wid}/steps/${sid}`),
  simulate:          (d: unknown)           => api.post('/approvals/simulate', d),
  bottlenecks:       (params?: QueryParams)      => api.get('/approvals/analytics/bottlenecks', { params }),
  approverLoad:      (params?: QueryParams)      => api.get('/approvals/analytics/approver-load', { params }),
  listRequests:      (params?: QueryParams)      => api.get('/approvals/requests', { params }),
  pendingMyAction:   ()            => api.get('/approvals/requests/pending-my-action'),
  // Revisión 2026-11: fuera de la oficina (a quién pasan mis aprobaciones).
  getOutOfOffice:    ()            => api.get('/approvals/out-of-office'),
  setOutOfOffice:    (d: unknown)  => api.put('/approvals/out-of-office', d),
  createRequest:     (d: unknown)           => api.post('/approvals/requests', d),
  decide:            (id: PathId, d: unknown)       => api.post(`/approvals/requests/${id}/decide`, d),
  cancel:            (id: PathId)          => api.post(`/approvals/requests/${id}/cancel`),
  stats:             ()            => api.get('/approvals/stats'),
  // Groups
  listGroups:        ()            => api.get('/approvals/groups'),
  createGroup:       (d: unknown)           => api.post('/approvals/groups', d),
  updateGroup:       (id: PathId, d: unknown)       => api.patch(`/approvals/groups/${id}`, d),
  deleteGroup:       (id: PathId)          => api.delete(`/approvals/groups/${id}`),
}

export const uatApi = {
  list:   (projectId: PathId, params?: QueryParams) => api.get(`/projects/${projectId}/uat`, { params }),
  create: (projectId: PathId, data: unknown)   => api.post(`/projects/${projectId}/uat`, data),
  update: (projectId: PathId, id: PathId, d: unknown)  => api.patch(`/projects/${projectId}/uat/${id}`, d),
  remove: (projectId: PathId, id: PathId)     => api.delete(`/projects/${projectId}/uat/${id}`),
  export: (projectId: PathId)         => api.get(`/projects/${projectId}/uat/export`),
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

export const aiCopilotApi = {
  ganttSuggestions:     (projectId: PathId) => api.get(`/ai/suggestions/gantt/${projectId}`),
  timesheetSuggestions: (userId: PathId)    => api.get(`/ai/suggestions/timesheets/${userId}`),
}

export const imputationsApi = {
  list:           (params?: QueryParams) => api.get('/imputations', { params }),
  myWeek:         (params?: QueryParams) => api.get('/imputations/my/week', { params }),
  create:         (data: unknown) => api.post('/imputations', data),
  update:         (id: PathId, data: unknown) => api.patch(`/imputations/${id}`, data),
  delete:         (id: PathId) => api.delete(`/imputations/${id}`),
  approve:        (id: PathId) => api.post(`/imputations/${id}/approve`),
  reject:         (id: PathId) => api.post(`/imputations/${id}/reject`),
  timerCurrent:   () => api.get('/imputations/timer/current'),
  timerStart:     (data: unknown) => api.post('/imputations/timer/start', data),
  timerPause:     () => api.post('/imputations/timer/pause'),
  timerResume:    () => api.post('/imputations/timer/resume'),
  timerCancel:    () => api.post('/imputations/timer/cancel'),
  timerStop:      (data: unknown) => api.post('/imputations/timer/stop', data),
}

export const analyticsApi = {
  query:        (metricId: PathId, params?: QueryParams) => api.get(`/analytics/query/${metricId}`, { params }),
  filterOptions: ()                => api.get('/analytics/filters/options'),
  hoursWeek:    (params?: QueryParams)           => api.get('/analytics/hours_by_week', { params }),
  utilization:  (params?: QueryParams)           => api.get('/analytics/utilization/advanced', { params }),
  metricBreaches: (params?: QueryParams)         => api.get('/analytics/alerts/metric-breaches', { params }),
  // BI / OLAP
  narrative:       (params?: QueryParams)        => api.get('/analytics/narrative', { params }),
  ask:             (question: string)      => api.post('/analytics/ask', { question }),
  // Revisión 2026-11: estado y carga del almacén analítico.
  olapStatus:      ()                   => api.get('/analytics/olap/status'),
  olapRefresh:     ()                   => api.post('/analytics/olap/refresh'),
  saveAskExample:  (question: string, sql: string) => api.post('/analytics/ask/examples', { question, sql }),
  olapKpis:        (params?: QueryParams)        => api.get('/analytics/olap/kpis', { params }),
  olapFunnel:      ()              => api.get('/analytics/olap/pipeline-funnel'),
  olapPortfolio:   ()              => api.get('/analytics/olap/portfolio-health'),
  olapMargin:      (months?: number | string)        => api.get('/analytics/olap/margin-evolution', { params: { months } }),
  olapUtilization: ()              => api.get('/analytics/olap/utilization'),
  catalogue:       ()              => api.get('/analytics/catalogue'),
}

export const biCollaborationApi = {
  listComments:   (params?: QueryParams)             => api.get('/bi/collaboration/comments', { params }),
  createComment:  (payload: unknown)            => api.post('/bi/collaboration/comments', payload),
  resolveComment: (commentId: PathId)          => api.patch(`/bi/collaboration/comments/${commentId}/resolve`),
  listSharedViews: (params?: QueryParams)            => api.get('/bi/collaboration/shared-views', { params }),
  createSharedView: (payload: unknown)          => api.post('/bi/collaboration/shared-views', payload),
  patchSharedView: (viewId: PathId, payload: unknown)   => api.patch(`/bi/collaboration/shared-views/${viewId}`, payload),
  governanceOverview: ()               => api.get('/bi/governance/overview'),
  governanceRules: ()                  => api.get('/bi/governance/rules'),
  updateGovernanceRules: (payload: unknown)     => api.patch('/bi/governance/rules', payload),
  runGovernanceChecks: ()              => api.post('/bi/governance/run-checks'),
  lastGovernanceRun: ()                => api.get('/bi/governance/last-run'),
  // Dashboard shares
  listDashboardShares:    (key: PathId)              => api.get(`/bi/collaboration/dashboards/${key}/shares`),
  shareDashboard:         (key: PathId, data: unknown)        => api.post(`/bi/collaboration/dashboards/${key}/shares`, data),
  revokeShare:            (key: PathId, shareId: PathId)     => api.delete(`/bi/collaboration/dashboards/${key}/shares/${shareId}`),
  // Dashboard versions
  listDashboardVersions:  (key: PathId)              => api.get(`/bi/collaboration/dashboards/${key}/versions`),
  restoreDashboardVersion:(key: PathId, versionId: PathId)   => api.post(`/bi/collaboration/dashboards/${key}/versions/${versionId}/restore`),
  // Notifications
  listNotifications:      (params?: QueryParams)           => api.get('/bi/collaboration/notifications', { params }),
  patchNotification:      (id: PathId, data: unknown)         => api.patch(`/bi/collaboration/notifications/${id}`, data),
}

export const biIntelligenceApi = {
  reportPresets: ()                    => api.get('/bi/intelligence/reports/presets'),
  previewPreset: (payload: unknown)             => api.post('/bi/intelligence/reports/preview', payload),
  queryBuilderSchema: ()               => api.get('/bi/intelligence/query-builder/schema'),
  queryBuilderPreview: (payload: unknown)       => api.post('/bi/intelligence/query-builder/preview', payload),
  queryBuilderTemplates: ()            => api.get('/bi/intelligence/query-builder/templates'),
  saveQueryBuilderTemplate: (payload: unknown)  => api.post('/bi/intelligence/query-builder/templates', payload),
  deleteQueryBuilderTemplate: (id: PathId)     => api.delete(`/bi/intelligence/query-builder/templates/${id}`),
  deliveryOverview: ()                 => api.get('/bi/intelligence/delivery/overview'),
}

export const biPlatformApi = {
  lineage: ()                          => api.get('/bi/platform/governance/lineage'),
  createSnapshot: (datasetKey: PathId, p: unknown)      => api.post(`/bi/platform/versioning/${datasetKey}/snapshots`, p),
  listSnapshots: (datasetKey: PathId)          => api.get(`/bi/platform/versioning/${datasetKey}/snapshots`),
  diffSnapshots: (datasetKey: PathId, fromId: PathId, toId: PathId) => api.get(`/bi/platform/versioning/${datasetKey}/diff`, { params: { from_id: fromId, to_id: toId } }),
}

export const biSmartAlertsApi = {
  supportedMetrics: ()                 => api.get('/bi/alerts/supported-metrics'),
  listRules: ()                        => api.get('/bi/alerts/rules'),
  createRule: (payload: unknown)                => api.post('/bi/alerts/rules', payload),
  updateRule: (ruleId: PathId, payload: unknown)        => api.patch(`/bi/alerts/rules/${ruleId}`, payload),
  deleteRule: (ruleId: PathId)                 => api.delete(`/bi/alerts/rules/${ruleId}`),
  evaluate: ()                         => api.post('/bi/alerts/evaluate'),
  getHistory: (limit: number = 100)            => api.get('/bi/alerts/history', { params: { limit } }),
  acknowledge: (alertId: PathId)               => api.post(`/bi/alerts/history/${alertId}/acknowledge`),
  seedDefaults: ()                     => api.post('/bi/alerts/seed-defaults'),
  listCustomMetrics: ()                => api.get('/bi/alerts/custom-metrics'),
  createCustomMetric: (payload: unknown)        => api.post('/bi/alerts/custom-metrics', payload),
  deleteCustomMetric: (key: PathId)            => api.delete(`/bi/alerts/custom-metrics/${key}`),
}

export const biBookmarksApi = {
  list: ()                             => api.get('/bi/bookmarks'),
  create: (payload: unknown)                    => api.post('/bi/bookmarks', payload),
  delete: (id: PathId)                         => api.delete(`/bi/bookmarks/${id}`),
}

export const biGovernanceAuditApi = {
  // BI Governance — audit trail, data lineage, field sensitivity
  getAccessHistory: (params?: QueryParams)           => api.get('/bi/governance/audit/access', { params }),
  listLineage: (target_table?: string)          => api.get('/bi/governance/lineage', { params: target_table ? { target_table } : undefined }),
  trackLineage: (payload: unknown)              => api.post('/bi/governance/lineage', payload),
  listFieldSensitivity: (dataset_id?: string)   => api.get('/bi/governance/field-sensitivity', { params: dataset_id ? { dataset_id } : undefined }),
  upsertFieldSensitivity: (payload: unknown)    => api.put('/bi/governance/field-sensitivity', payload),
}

export const biReportBuilderV2Api = {
  listPresets: (params?: QueryParams)                => api.get('/bi/reports/v2/presets', { params }),
  preview: (presetId: PathId, limit: number = 50)      => api.get(`/bi/reports/v2/presets/${presetId}/preview`, { params: { limit } }),
  export: (presetId: PathId, format: string = 'json')  => api.get(`/bi/reports/v2/presets/${presetId}/export`, { params: { format } }),
}

export const dashboardApi = {
  kpis:           () => api.get('/dashboard/kpis'),
  projectsHealth: (params?: QueryParams) => api.get('/dashboard/projects-health', { params }),
  resourceLoad:   (params?: QueryParams) => api.get('/dashboard/resource-load', { params }),
  profitability:  (params?: QueryParams) => api.get('/dashboard/profitability', { params }),
  teamProductivity: (params?: QueryParams) => api.get('/dashboard/productivity/team', { params }),
}

export const alertsApi = {
  list:     (params?: QueryParams) => api.get('/alerts', { params }),
  run:      () => api.post('/alerts/run'),
  read:     (id: PathId) => api.patch(`/alerts/${id}/read`),
  resolve:  (id: PathId) => api.patch(`/alerts/${id}/resolve`),
}

export const integrationsApi = {
  // Auditoria 2026-08 (hallazgo 37): estas dos apuntaban a
  // `POST /integrations/export/...`, rutas que no existen en ningun router, asi
  // que los dos botones de la pantalla de exportaciones devolvian 404. El
  // export de imputaciones si existia con otro verbo y otra ruta; el de
  // proyectos hubo que anadirlo (`/analytics/exports/projects-csv`).
  exportImputations: (params: unknown) => api.get('/analytics/exports/imputations-csv', { params, responseType: 'blob' }),
  exportProjects:    (params: unknown) => api.get('/analytics/exports/projects-csv', { params, responseType: 'blob' }),
  // Importa issues de Jira como tareas del proyecto (revisión 2026-11: llamaba a
  // una ruta que espera el id de una configuración y siempre daba 404).
}

export const clientsApi = {
  list:         (params?: QueryParams): Promise<AxiosResponse<Client[]>>     => api.get('/clients', { params }),
  get:          (id: PathId): Promise<AxiosResponse<Client>>         => api.get(`/clients/${id}`),
  create:       (data: unknown)       => api.post('/clients', data),
  update:       (id: PathId, data: unknown)   => api.patch(`/clients/${id}`, data),
  delete:       (id: PathId)         => api.delete(`/clients/${id}`),
  contacts:     (id: PathId): Promise<AxiosResponse<ClientContact[]>>         => api.get(`/clients/${id}/contacts`),
}

// ── Sprints ───────────────────────────────────────────────────────────────────
export const sprintsApi = {
  list:    (projectId: PathId, params?: QueryParams): Promise<AxiosResponse<Sprint[]>> => api.get('/sprints', { params: { project_id: projectId, ...params } }),
}

// ── Epics ─────────────────────────────────────────────────────────────────────
export const epicsApi = {
  list:            (projectId: PathId): Promise<AxiosResponse<Epic[]>> => api.get('/epics', { params: { project_id: projectId } }),
  get:             (id: PathId): Promise<AxiosResponse<Epic>>        => api.get(`/epics/${id}`),
  create:          (data: unknown)      => api.post('/epics', data),
  createForProject:(projectId: PathId, data: unknown) => api.post('/epics', data, { params: { project_id: projectId } }),
  update:          (id: PathId, data: unknown)  => api.patch(`/epics/${id}`, data),
  delete:          (id: PathId)        => api.delete(`/epics/${id}`),
  linkTask:        (id: PathId, taskId: PathId) => api.post(`/epics/${id}/tasks/${taskId}`),
  unlinkTask:      (id: PathId, taskId: PathId) => api.delete(`/epics/${id}/tasks/${taskId}`),
  // Auditoria 2026-11 (#45): `roadmapByProject` era la misma llamada; se quita.
  roadmap:         (projectId: PathId) => api.get('/epics/roadmap', { params: { project_id: projectId } }),
  cfd:             (params?: QueryParams)    => api.get('/epics/cfd', { params }),
  cfdSnapshot:     (projectId: PathId) => api.post('/epics/cfd/snapshot', null, { params: { project_id: projectId } }),
  nqlSearch:       (data: unknown)      => api.post('/epics/nql/search', data),
}

// ── Contracts ─────────────────────────────────────────────────────────────────
export const contractsApi = {
  list:                (params?: QueryParams): Promise<AxiosResponse<Contract[]>>           => api.get('/contracts', { params }),
  get:                 (id: PathId): Promise<AxiosResponse<Contract>>               => api.get(`/contracts/${id}`),
  create:              (data: unknown)             => api.post('/contracts', data),
  update:              (id: PathId, data: unknown)         => api.patch(`/contracts/${id}`, data),
  delete:              (id: PathId)               => api.delete(`/contracts/${id}`),
  createWorkOrder:     (id: PathId, data: unknown)         => api.post(`/contracts/${id}/work-orders`, data),
  updateWorkOrderStatus:(id: PathId, woId: PathId, status: string)=> api.patch(`/contracts/${id}/work-orders/${woId}/status`, null, { params: { status } }),
}

// ── Expenses ──────────────────────────────────────────────────────────────────
export const expensesApi = {
  list:      (params?: QueryParams)    => api.get('/expenses', { params }),
  my:        (params?: QueryParams)    => api.get('/expenses/my', { params }),
  pending:   ()          => api.get('/expenses/pending'),
  team:      (params?: QueryParams)    => api.get('/expenses/team', { params }),
  create:    (data: unknown)      => api.post('/expenses', data),
  update:    (id: PathId, data: unknown)  => api.patch(`/expenses/${id}`, data),
  updateMy:  (id: PathId, data: unknown)  => api.patch(`/expenses/my/${id}`, data),
  review:    (id: PathId, data: unknown)  => api.post(`/expenses/${id}/review`, data),
  submitMy:  (id: PathId)        => api.post(`/expenses/my/${id}/submit`),
  recall:    (id: PathId)        => api.post(`/expenses/my/${id}/recall`),
  reimburse: (id: PathId)        => api.post(`/expenses/${id}/reimburse`),
  deleteMy:  (id: PathId)        => api.delete(`/expenses/my/${id}`),
  ocr:       (fd: unknown)        => api.post('/expenses/ocr', fd),
  exportExcel: ()                 => api.get('/expenses/export', { responseType: 'blob' }),
}

// ── Risks ─────────────────────────────────────────────────────────────────────
export const risksApi = {
  list:         <R = Risk>(projectId: PathId, params?: QueryParams): Promise<AxiosResponse<RiesgosDelProyecto<R>>> => api.get(`/risks/${projectId}`, { params }),
  get:          (projectId: PathId, riskId: PathId): Promise<AxiosResponse<Risk>> => api.get(`/risks/${projectId}/${riskId}`),
  create:       (projectId: PathId, data: unknown)   => api.post(`/risks/${projectId}`, data),
  update:       (projectId: PathId, riskId: PathId, data: unknown) => api.patch(`/risks/${projectId}/${riskId}`, data),
  delete:       (projectId: PathId, riskId: PathId) => api.delete(`/risks/${projectId}/${riskId}`),
  portfolioAll: ()                  => api.get('/risks/all/portfolio'),
}

// ── OKRs ─────────────────────────────────────────────────────────────────────
export const okrsApi = {
  list:     (params?: QueryParams)      => api.get('/okrs', { params }),
  create:   (data: unknown)        => api.post('/okrs', data),
  update:   (id: PathId, data: unknown)    => api.patch(`/okrs/${id}`, data),
  delete:   (id: PathId)          => api.delete(`/okrs/${id}`),
  createKR: (data: unknown)        => api.post('/okrs/key-results', data),
  deleteKR: (id: PathId)          => api.delete(`/okrs/key-results/${id}`),
  checkin:  (krId: PathId, data: unknown)  => api.post(`/okrs/key-results/${krId}/checkin`, data),
}

// ── Pipeline (opportunities) ──────────────────────────────────────────────────
export const pipelineApi = {
  list:       (params?: QueryParams)    => api.get('/pipeline', { params }),
  get:        (id: PathId)        => api.get(`/pipeline/${id}`),
  create:     (data: unknown)      => api.post('/pipeline', data),
  update:     (id: PathId, data: unknown)  => api.patch(`/pipeline/${id}`, data),
  delete:     (id: PathId)        => api.delete(`/pipeline/${id}`),
  generateProposal: (id: PathId, payload: unknown) => api.post(`/pipeline/${id}/generate-proposal`, payload || {}),
  markProposalSent: (id: PathId)          => api.post(`/pipeline/${id}/mark-proposal-sent`),
  convertToProject: (id: PathId)          => api.post(`/pipeline/${id}/convert`),
  getProposal:      (id: PathId)          => api.get(`/pipeline/${id}/proposal`),
}

// ── Deliverables ──────────────────────────────────────────────────────────────
export const deliverablesApi = {
  listByProject:   (projectId: PathId) => api.get(`/deliverables/${projectId}`),
  overviewAll:     ()          => api.get('/deliverables/all/overview'),
  createForProject:(projectId: PathId, data: unknown) => api.post(`/deliverables/${projectId}`, data),
  updateInProject: (projectId: PathId, id: PathId, data: unknown) => api.patch(`/deliverables/${projectId}/${id}`, data),
  deleteFromProject:(projectId: PathId, id: PathId) => api.delete(`/deliverables/${projectId}/${id}`),
  accept:          (projectId: PathId, id: PathId) => api.post(`/deliverables/${projectId}/${id}/accept`),
  reject:          (projectId: PathId, id: PathId, reason: string) => api.post(`/deliverables/${projectId}/${id}/reject`, {}, { params: { reason } }),
}

// ── Subcontractors ────────────────────────────────────────────────────────────
export const subcontractorsApi = {
  // Auditoria 2026-08: el prefijo real es `/enterprise/`. Sin el, el selector
  // de entidades no cargaba ningun subcontratista. Hay otro cliente en este
  // mismo fichero que ya apuntaba bien — dos clientes para lo mismo, uno
  // roto y otro correcto.
  list:        (params?: QueryParams)    => api.get('/enterprise/subcontractors', { params }),
  create:      (data: unknown)      => api.post('/enterprise/subcontractors', data),
  update:      (id: PathId, data: unknown)  => api.patch(`/enterprise/subcontractors/${id}`, data),
  delete:      (id: PathId)        => api.delete(`/enterprise/subcontractors/${id}`),
}

// ── Training ──────────────────────────────────────────────────────────────────
export const trainingApi = {
  courses:     (params?: QueryParams)    => api.get('/training/courses', { params }),
  createCourse:(data: unknown)      => api.post('/training/courses', data),
  updateCourse:(id: PathId, data: unknown)  => api.patch(`/training/courses/${id}`, data),
  deleteCourse:(id: PathId)        => api.delete(`/training/courses/${id}`),
  certs:       (params?: QueryParams)    => api.get('/training/certifications', { params }),
  createCert:  (data: unknown)      => api.post('/training/certifications', data),
  updateCert:  (id: PathId, data: unknown)  => api.patch(`/training/certifications/${id}`, data),
  deleteCert:  (id: PathId)        => api.delete(`/training/certifications/${id}`),
  enroll:      (data: unknown)      => api.post('/training/enrollments', data),
  enrollments: (params?: QueryParams)    => api.get('/training/enrollments', { params }),
}

/** Ausencia tal como la serializa `serialize_absence` (app/services/absence_service.py). */
export interface Absence {
  id: string
  user_id: string
  user_name: string
  type: string
  type_label: string
  status: string
  status_label: string
  status_color: string
  start_date: string
  end_date: string
  working_days: number | null
  reason: string | null
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
  created_at: string | null
}

// ── Absences ──────────────────────────────────────────────────────────────────
export const absencesApi = {
  list:           (params?: QueryParams)    => import('./todasLasPaginas').then(m => m.todasLasPaginas<Absence>('/absences', params)),
  my:             (params?: QueryParams)    => api.get('/absences/my', { params }),
  pending:        ()          => api.get('/absences/pending'),
  team:           (params?: QueryParams)    => api.get('/absences/team', { params }),
  calendar:       (params?: QueryParams)    => api.get('/absences/calendar', { params }),
  createMy:       (data: unknown)      => api.post('/absences/my', data),
  updateMy:       (id: PathId, data: unknown)  => api.patch(`/absences/my/${id}`, data),
  review:         (id: PathId, data: unknown)  => api.post(`/absences/${id}/review`, data),
  deleteMy:       (id: PathId)        => api.delete(`/absences/my/${id}`),
  vacationBalance:()          => api.get('/absences/my/vacation-balance'),
}

// ── ALM — Assets, Licenses, Vendors ──────────────────────────────────────────
export const assetsApi = {
  list:    (params?: QueryParams)   => api.get('/alm/assets', { params }),
  get:     (id: PathId)       => api.get(`/alm/assets/${id}`),
  create:  (data: unknown)     => api.post('/alm/assets', data),
  update:  (id: PathId, data: unknown) => api.patch(`/alm/assets/${id}`, data),
  delete:  (id: PathId)       => api.delete(`/alm/assets/${id}`),
  history: (id: PathId)       => api.get(`/alm/assets/${id}/history`),
  expiring: (days: number) => api.get('/alm/assets/expiring', { params: { days } }),
  refreshTicket: (id: PathId) => api.post(`/alm/assets/${id}/refresh-ticket`),
}

export const licensesApi = {
  list:    (params?: QueryParams)   => api.get('/alm/licenses', { params }),
  get:     (id: PathId)       => api.get(`/alm/licenses/${id}`),
  create:  (data: unknown)     => api.post('/alm/licenses', data),
  update:  (id: PathId, data: unknown) => api.patch(`/alm/licenses/${id}`, data),
  delete:  (id: PathId)       => api.delete(`/alm/licenses/${id}`),
  assign:  (id: PathId, data: unknown) => api.post(`/alm/licenses/${id}/assign`, data),
}

export const vendorsApi = {
  list:   (params?: QueryParams)   => api.get('/alm/vendors', { params }),
  create: (data: unknown)     => api.post('/alm/vendors', data),
  update: (id: PathId, data: unknown) => api.patch(`/alm/vendors/${id}`, data),
  delete: (id: PathId)       => api.delete(`/alm/vendors/${id}`),
}

// ── Service Desk ──────────────────────────────────────────────────────────────
export const ticketsApi = {
  watchers:  (id: PathId)      => api.get(`/sd/tickets/${id}/watchers`),
  watch:     (id: PathId)      => api.post(`/sd/tickets/${id}/watch`),
  unwatch:   (id: PathId)      => api.delete(`/sd/tickets/${id}/watch`),
  mergeInto: (id: PathId, data: unknown) => api.post(`/sd/tickets/${id}/merge`, data),
  list:    (params?: QueryParams)   => api.get('/sd/tickets', { params }),
  myQueue: (params?: QueryParams) => api.get('/sd/tickets/my-queue', { params }),
  get:     (id: PathId)       => api.get(`/sd/tickets/${id}`),
  create:  (data: unknown)     => api.post('/sd/tickets', data),
  update:  (id: PathId, data: unknown) => api.patch(`/sd/tickets/${id}`, data),
  comment: (id: PathId, data: unknown) => api.post(`/sd/tickets/${id}/comments`, data),
  aiSuggest: (id: PathId, data: unknown) => api.post(`/sd/tickets/${id}/ai-suggest`, data),
  split:   (id: PathId, data: unknown) => api.post(`/sd/tickets/${id}/split`, data),
  links:   (id: PathId)       => api.get(`/sd/tickets/${id}/links`),
  timelog:    (id: PathId, data: unknown)         => api.post(`/sd/tickets/${id}/time-log`, data),
  restorePending: (id: PathId)           => api.post(`/sd/tickets/${id}/restore-pending`, {}),
  escalate:   (id: PathId, level: string = 'l2') => api.post(`/sd/tickets/${id}/escalate?to_level=${level}`, {}),
  slaPause:   (id: PathId, data: unknown) => api.post(`/sd/tickets/${id}/sla/pause`, data),
  slaResume:  (id: PathId)       => api.post(`/sd/tickets/${id}/sla/resume`),
  recommendAssignment:   (id: PathId, data: unknown)   => api.post(`/sd/tickets/${id}/recommend-assignment`, data),
  autoResolutionFeedback:(id: PathId, data: unknown)   => api.post(`/sd/tickets/${id}/auto-resolution/feedback`, data),
}

export const problemsApi = {
  list:   (params?: QueryParams)   => api.get('/sd/problems', { params }),
  create: (data: unknown)     => api.post('/sd/problems', data),
  update: (id: PathId, data: unknown) => api.patch(`/sd/problems/${id}`, data),
  delete:             (id: PathId)       => api.delete(`/sd/problems/${id}`),
  // Auditoria 2026-08: la ruta real acaba en `promote-kedb`, no en
  // `promote-known-error`. La pestaña de conocimiento de ITSM daba 404.
  promoteKnownError:  (id: PathId)       => api.post(`/sd/problems/${id}/promote-kedb`),
  // RCA Wizard
  rcaWizardGet:      (id: PathId)        => api.get(`/sd/problems/${id}/rca-wizard`),
  rcaWizardStart:    (id: PathId, data: unknown)  => api.post(`/sd/problems/${id}/rca-wizard/start`, data),
  rcaWizardStep:     (id: PathId, data: unknown)  => api.post(`/sd/problems/${id}/rca-wizard/step`, data),
  rcaWizardComplete: (id: PathId)        => api.post(`/sd/problems/${id}/rca-wizard/complete`),
  rcaWizardAiAssist: (id: PathId, data: unknown)  => api.post(`/sd/problems/${id}/rca-wizard/ai-assist`, data),
}

export const changesApi = {
  list:    (params?: QueryParams)   => api.get('/sd/changes', { params }),
  get:     (id: PathId)       => api.get(`/sd/changes/${id}`),
  create:  (data: unknown)     => api.post('/sd/changes', data),
  update:  (id: PathId, data: unknown) => api.patch(`/sd/changes/${id}`, data),
  delete:  (id: PathId)       => api.delete(`/sd/changes/${id}`),
  approve: (id: PathId, data: unknown) => api.post(`/sd/changes/${id}/approve`, data),
}

export const sdDynamicFormsApi = {
  get:           () => api.get('/sd/dynamic-forms'),
  history:       () => api.get('/sd/dynamic-forms/history'),
  contextOptions:(params?: QueryParams) => api.get('/sd/dynamic-forms/context-options', { params }),
  rollback:      (snapshot_id: PathId) => api.post('/sd/dynamic-forms/rollback', { snapshot_id }),
  importPreview: (data: unknown) => api.post('/sd/dynamic-forms/import/preview', data),
  importApply:   (data: unknown) => api.post('/sd/dynamic-forms/import/apply', data),
}

// ── Invoices ──────────────────────────────────────────────────────────────────
export const invoicesApi = {
  list:          (params?: QueryParams)          => api.get('/invoices', { params }),
  summary:       ()                => api.get('/invoices/summary'),
  create:        (data: unknown)            => api.post('/invoices', data),
  updateStatus:  (id: PathId, status: string)      => api.patch(`/billing-reports/invoices/${id}/status`, { status }),
  pdf:           (id: PathId)              => api.get(`/invoices/${id}/pdf`, { responseType: 'blob' }),
  // Revisión 2026-11: ficha, edición de borradores y borrado.
  get:           (id: PathId)              => api.get(`/invoices/${id}`),
  update:        (id: PathId, data: unknown) => api.patch(`/invoices/${id}`, data),
  remove:        (id: PathId)              => api.delete(`/invoices/${id}`),
  fromTimesheets:(data: unknown)            => api.post('/invoices/from-timesheets', data),
}

// ── Accounting Hub (Xero / QuickBooks) ────────────────────────────────────────
export const accountingApi = {
  syncStatus:    ()                => api.get('/accounting/sync-status'),
  pushBulk:      (data: unknown)            => api.post('/accounting/push-invoices-bulk', data),
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
  rates:   (params?: QueryParams)        => getWithFallback(['/currency/rates', '/currency-rates/currency/rates', '/bookings/currency/rates'], { params }),
  upsert:  (data: unknown)          => postWithFallback(['/currency/rates', '/currency-rates/currency/rates', '/bookings/currency/rates'], data),
}

// ── Predictive Observability ──────────────────────────────────────────────────
export const predictiveObservabilityApi = {
  health:        (params?: QueryParams)  => api.get('/bi/predictive/observability/health', { params }),
  triggerRetrain:()        => api.post('/bi/predictive/observability/trigger-retrain'),
}

// ── ML Predictions ────────────────────────────────────────────────────────────
export const predictionsApi = {
  overrunRisk:    (projectId: PathId)  => api.post('/predictions/overrun-risk', { project_id: projectId }),
  portfolioRisk:  ()           => api.get('/predictions/portfolio-risk'),
  train:          ()           => api.post('/predictions/train'),
  models:         ()           => api.get('/predictions/models'),
  logs:           (params?: QueryParams)     => api.get('/predictions/logs', { params }),
}

// ── Revenue Recognition (ASC 606) ─────────────────────────────────────────────
export const revenueRecognitionApi = {
  dashboard:           (year: PathId, months: number) => api.get('/revenue-recognition/dashboard', { params: { year, months } }),
  contracts:           (params?: QueryParams)       => api.get('/revenue-recognition/contracts', { params }),
  createContract:      (data: unknown)         => api.post('/revenue-recognition/contracts', data),
  obligations:         (contractId: PathId)   => api.get(`/revenue-recognition/contracts/${contractId}/obligations`),
  createObligation:    (contractId: PathId, d: unknown)=> api.post(`/revenue-recognition/contracts/${contractId}/obligations`, d),
  updateObligation:    (id: PathId, data: unknown)     => api.patch(`/revenue-recognition/obligations/${id}`, data),
  deleteObligation:    (id: PathId)           => api.delete(`/revenue-recognition/obligations/${id}`),
  entries:             (params?: QueryParams)       => api.get('/revenue-recognition/entries', { params }),
  reverseEntry:        (id: PathId)           => api.post(`/revenue-recognition/entries/${id}/reverse`),
  periodCloses:        ()             => api.get('/revenue-recognition/period-closes'),
  closePeriod:         (data: unknown)         => api.post('/revenue-recognition/period-closes', data),
  reopenPeriod:        (year: PathId, month: PathId)  => api.delete(`/revenue-recognition/period-closes/${year}/${month}`),
  runMonthly:          (data: unknown)         => api.post('/revenue-recognition/run-monthly', data),
}

// ── CMDB ──────────────────────────────────────────────────────────────────────
export const cmdbApi = {
  // Revisión 2026-11: configuración del tablero por proyecto (carriles y límites WIP).
  kanbanConfig:     (projectId: string) => api.get(`/cmdb/kanban/${projectId}`),
  saveKanbanConfig: (projectId: string, data: { swimlane_by: string }) => api.post(`/cmdb/kanban/${projectId}`, data),
  addKanbanColumn:  (projectId: string, data: { status: string; wip_limit: number | null }) => api.post(`/cmdb/kanban/${projectId}/columns`, data),
  updateKanbanColumn: (columnId: string, data: { status: string; wip_limit: number | null }) => api.patch(`/cmdb/kanban/columns/${columnId}`, data),
  // Una sola CMDB (auditoría 2026-11): la del service desk, `/sd/cmdb`.
  sdList:         (params?: QueryParams)   => api.get('/sd/cmdb', { params }),
  sdCreate:       (data: unknown)     => api.post('/sd/cmdb', data),
  sdUpdate:       (id: PathId, data: unknown) => api.patch(`/sd/cmdb/${id}`, data),
  sdDelete:       (id: PathId)       => api.delete(`/sd/cmdb/${id}`),
  sdChangelog:    (id: PathId)       => api.get(`/sd/cmdb/${id}/changelog`),
  sdRelations:    (id: PathId)       => api.get(`/sd/cmdb/${id}/relations`),
  sdCreateRelation: (data: unknown)   => api.post('/sd/cmdb/relations', data),
  sdDeleteRelation: (id: PathId)     => api.delete(`/sd/cmdb/relations/${id}`),
  classFields:    ()              => api.get('/sd/cmdb/class-fields'),
  saveClassFields: (ciType: string, fields: unknown) => api.put(`/sd/cmdb/class-fields/${ciType}`, fields),
  topology:       (id: PathId, r: number)    => api.get(`/sd/cmdb/${id}/topology`, { params: { radius: r } }),
  // Agents
  agents:         ()         => api.get('/sd/cmdb/agents'),
  registerAgent:  (data: unknown)     => api.post('/sd/cmdb/agents/register', data),
  deleteAgent:    (id: PathId)       => api.delete(`/sd/cmdb/agents/${id}`),
  agentDashboard: (agentId: PathId, days: number) => api.get(`/cmdb/agent-dashboard/${agentId}?days=${days}`),
  assetsByCI:     (ciId: PathId)     => api.get(`/alm/assets/by-ci/${ciId}`),
}

// ── Timesheets ────────────────────────────────────────────────────────────────
export const timesheetsApi = {
  my:          ()              => api.get('/timesheets/my'),
  pending:     ()              => api.get('/timesheets/pending'),
  team:        ()              => api.get('/timesheets/team'),
  weekLines:   (weekStart: PathId)     => api.get(`/timesheets/my/${weekStart}/lines`),
  submit:      (weekStart: PathId)     => api.post(`/timesheets/my/${weekStart}/submit`),
  review:      (id: PathId, data: unknown)      => api.post(`/timesheets/${id}/review`, data),
}

// ── Documents ─────────────────────────────────────────────────────────────────
export const documentsApi = {
  list:      (params?: QueryParams)   => api.get('/documents', { params }),
  get:       (id: PathId)       => api.get(`/documents/${id}`),
  upload:    (fd: unknown)       => api.post('/documents/upload', fd),
  update:    (id: PathId, data: unknown) => api.patch(`/documents/${id}`, data),
  delete:    (id: PathId)       => api.delete(`/documents/${id}`),
  approve:   (id: PathId, data: unknown) => api.post(`/documents/${id}/approve`, data),
  submitApproval: (id: PathId)  => api.post(`/documents/${id}/submit-approval`),
  aiSummary: (id: PathId)       => api.post(`/documents/${id}/ai-summary`),
  addVersion:(id: PathId, fd: unknown)   => api.post(`/documents/${id}/versions`, fd),
  // Revisión 2026-11: reservar para editar (check-out / check-in).
  checkout:  (id: PathId)       => api.post(`/documents/${id}/checkout`),
  checkin:   (id: PathId, force = false) => api.post(`/documents/${id}/checkin`, null, { params: force ? { force: true } : undefined }),
  // Permisos
  listPermissions:   (id: PathId)              => api.get(`/documents/${id}/permissions`),
  grantPermission:   (id: PathId, data: unknown)        => api.post(`/documents/${id}/permissions`, data),
  revokePermission:  (id: PathId, permId: PathId)      => api.delete(`/documents/${id}/permissions/${permId}`),
  // By context
  byTask:    (taskId: PathId, params?: QueryParams)    => api.get(`/documents/by-task/${taskId}`, { params }),
  byTicket:  (ticketId: PathId, params?: QueryParams)  => api.get(`/documents/by-ticket/${ticketId}`, { params }),
  byProject: (projectId: PathId, params?: QueryParams) => api.get(`/documents/by-project/${projectId}`, { params }),
}

// ── Custom Fields ─────────────────────────────────────────────────────────────
export const customFieldsApi = {
  list:   (projectId: PathId)          => api.get(`/custom-fields/${projectId}`),
  create: (projectId: PathId, data: unknown)    => api.post(`/custom-fields/${projectId}`, data),
  update: (projectId: PathId, id: PathId, data: unknown)=> api.patch(`/custom-fields/${projectId}/${id}`, data),
  delete:    (projectId: PathId, id: PathId)           => api.delete(`/custom-fields/${projectId}/${id}`),
  getValues: (projectId: PathId, taskId: PathId)       => api.get(`/custom-fields/${projectId}/values/${taskId}`),
  setValues: (projectId: PathId, taskId: PathId, data: unknown) => api.post(`/custom-fields/${projectId}/values/${taskId}`, data),
}

// ── Wiki ──────────────────────────────────────────────────────────────────────
export const wikiApi = {
  spaces:       ()              => api.get('epics/wiki/spaces'),
  createSpace:  (data: unknown)          => api.post('epics/wiki/spaces', data),
  pages:        (spaceId: PathId)       => api.get(`epics/wiki/spaces/${spaceId}/pages`),
  getPage:      (id: PathId)            => api.get(`epics/wiki/pages/${id}`),
  createPage:   (spaceId: PathId, data: unknown) => api.post(`epics/wiki/spaces/${spaceId}/pages`, data),
  updatePage:   (id: PathId, data: unknown)      => api.patch(`epics/wiki/pages/${id}`, data),
  deletePage:   (id: PathId)            => api.delete(`epics/wiki/pages/${id}`),
  versions:     (id: PathId)            => api.get(`epics/wiki/pages/${id}/versions`),
  restorePage:  (id: PathId, vn: PathId)        => api.post(`epics/wiki/pages/${id}/restore/${vn}`),
  search:       (q: string, spaceId: PathId)    => api.get(`epics/wiki/search`, { params: { q, space_id: spaceId } }),
  // Auditoria 2026-08: las cuatro rutas de etiquetas viven bajo `/cmdb/`.
  // Sin el prefijo, toda la gestion de etiquetas del wiki devolvia 404.
  tags:             (space: PathId)         => api.get(`/cmdb/wiki-tags/${space}`),
  createTag:        (space: PathId, data: unknown)   => api.post(`/cmdb/wiki-tags/${space}`, data),
  updateTag:        (id: PathId, data: unknown)      => api.patch(`/cmdb/wiki-tags/${id}`, data),
  deleteTag:        (id: PathId)            => api.delete(`/cmdb/wiki-tags/${id}`),
  // portal-scoped wiki (different URL prefix)
  portalSpaces:     ()              => api.get('wiki/spaces'),
  portalPages:      (spaceId: PathId)       => api.get(`wiki/spaces/${spaceId}/pages`),
  portalUpdatePage: (id: PathId, data: unknown)      => api.patch(`wiki/pages/${id}`, data),
}

// ── Skills ────────────────────────────────────────────────────────────────────
export const skillsApi = {
  catalog:        ()               => api.get('/skills/catalog'),
  createCatalog:  (data: unknown)           => api.post('/skills/catalog', data),
  deleteCatalog:  (id: PathId)             => api.delete(`/skills/catalog/${id}`),
  userSkills:     (userId: PathId)         => api.get(`/skills/users/${userId}`),
  userHistory:    (userId: PathId)         => api.get(`/skills/users/${userId}/history`),
  addUserSkill:   (userId: PathId, data: unknown)   => api.post(`/skills/users/${userId}`, data),
  removeUserSkill:(userId: PathId, skillId: PathId)=> api.delete(`/skills/users/${userId}/${skillId}`),
  matrix:         ()               => api.get('/skills/matrix'),
  search:         (params?: QueryParams)         => api.get('/skills/search', { params }),
}

// ── Enterprise Subcontractors ─────────────────────────────────────────────────
export const enterpriseSubsApi = {
  dashboard:        ()                     => api.get('/enterprise/subcontractors-dashboard'),
  // CRUD de subcontratistas: `subcontractorsApi` (auditoria 2026-11, #45: estaba duplicado aqui).
  workers:          (subId: PathId)                => api.get(`/enterprise/subcontractors/${subId}/workers`),
  createWorker:     (subId: PathId, data: unknown)          => api.post(`/enterprise/subcontractors/${subId}/workers`, data),
  updateWorker:     (id: PathId, data: unknown)             => api.patch(`/enterprise/subcontractors/workers/${id}`, data),
  deleteWorker:     (id: PathId)                   => api.delete(`/enterprise/subcontractors/workers/${id}`),
  addWorkerSkill:   (id: PathId, data: unknown)             => api.post(`/enterprise/subcontractors/workers/${id}/skills`, data),
  removeWorkerSkill:(id: PathId, skillId: PathId)          => api.delete(`/enterprise/subcontractors/workers/${id}/skills/${skillId}`),
  assignments:      (subId: PathId)                => api.get(`/enterprise/subcontractors/${subId}/assignments`),
  createAssignment: (subId: PathId, data: unknown)          => api.post(`/enterprise/subcontractors/${subId}/assignments`, data),
  timelogs:         (subId: PathId)                => api.get(`/enterprise/subcontractors/${subId}/timelogs`),
  createTimelog:    (subId: PathId, data: unknown)          => api.post(`/enterprise/subcontractors/${subId}/timelogs`, data),
  invoices:         (subId: PathId)                => api.get(`/enterprise/subcontractors/${subId}/invoices`),
  createInvoice:    (subId: PathId, data: unknown)          => api.post(`/enterprise/subcontractors/${subId}/invoices`, data),
  updateInvoice:    (subId: PathId, id: PathId, data: unknown)      => api.patch(`/enterprise/subcontractors/${subId}/invoices/${id}`, data),
}

// ── ALM Extended (contracts, cost-centers, compliance) ────────────────────────
export const almExtApi = {
  dashboard:       ()              => api.get('/alm/dashboard'),
  contracts:       ()              => api.get('/alm/contracts'),
  createContract:  (data: unknown)          => api.post('/alm/contracts', data),
  updateContract:  (id: PathId, data: unknown)      => api.patch(`/alm/contracts/${id}`, data),
  deleteContract:  (id: PathId)            => api.delete(`/alm/contracts/${id}`),
  costCenters:     ()              => api.get('/alm/cost-centers'),
  createCostCenter:(data: unknown)          => api.post('/alm/cost-centers', data),
  updateCostCenter:(id: PathId, data: unknown)      => api.patch(`/alm/cost-centers/${id}`, data),
  deleteCostCenter:(id: PathId)            => api.delete(`/alm/cost-centers/${id}`),
  compliance:      ()              => api.get('/alm/compliance'),
}

// ── CAB (Change Advisory Board) ───────────────────────────────────────────────
export const cabApi = {
  changes: ()             => api.get('/cab/changes'),
  windows: ()             => api.get('/cab/windows'),
  vote:    (id: PathId, data: unknown)     => api.post(`/cab/changes/${id}/vote`, data),
  close:   (id: PathId, data: unknown)     => api.post(`/cab/changes/${id}/close`, data),
}

// ── Project Change Requests ───────────────────────────────────────────────────
export const projectChangesApi = {
  list:       (projectId: PathId)           => api.get(`/changes/${projectId}`),
  allPending: ()                    => api.get('/changes/all/pending'),
  create:     (projectId: PathId, data: unknown)     => api.post(`/changes/${projectId}`, data),
  update:     (projectId: PathId, id: PathId, data: unknown) => api.patch(`/changes/${projectId}/${id}`, data),
  review:     (projectId: PathId, id: PathId, data: unknown) => api.post(`/changes/${projectId}/${id}/review`, data),
  submit:     (projectId: PathId, id: PathId)       => api.post(`/changes/${projectId}/${id}/submit`),
  implement:  (projectId: PathId, id: PathId)       => api.post(`/changes/${projectId}/${id}/implement`),
  delete:     (projectId: PathId, id: PathId)       => api.delete(`/changes/${projectId}/${id}`),
}

// ── NPS ───────────────────────────────────────────────────────────────────────
export const npsApi = {
  leaderboard:    ()            => api.get('/nps/leaderboard'),
  summary:        (id: PathId, days: number)    => api.get(`/nps/${id}/summary`, { params: { days } }),
  health:         (id: PathId, limit: number)   => api.get(`/nps/${id}/health`, { params: { limit } }),
  healthCompute:  (id: PathId)          => api.post(`/nps/${id}/health-compute`),
  respond:        (id: PathId, data: unknown)    => api.post(`/nps/${id}/responses`, data),
}

// ── Portfolios ────────────────────────────────────────────────────────────────
export const portfolioApi = {
  list:          ()             => api.get('/portfolios'),
  dashboard:     (id: PathId)           => api.get(`/portfolios/${id}/dashboard`),
  create:        (data: unknown)         => api.post('/portfolios', data),
  update:        (id: PathId, data: unknown)     => api.patch(`/portfolios/${id}`, data),
  delete:        (id: PathId)           => api.delete(`/portfolios/${id}`),
  addProject:    (id: PathId, pid: PathId)      => api.post(`/portfolios/${id}/projects`, { project_id: pid }),
  removeProject: (id: PathId, pid: PathId)      => api.delete(`/portfolios/${id}/projects/${pid}`),
}

// ── Performance Reviews ───────────────────────────────────────────────────────
export const performanceApi = {
  cycles:        ()             => api.get('/performance/cycles'),
  myReviews:     ()             => api.get('/performance/my-reviews'),
  cycleReviews:  (id: PathId)           => api.get(`/performance/cycles/${id}/reviews`),
  createCycle:   (data: unknown)         => api.post('/performance/cycles', data),
  activateCycle: (id: PathId)           => api.post(`/performance/cycles/${id}/activate`),
  closeCycle:    (id: PathId)           => api.post(`/performance/cycles/${id}/close`),
  // Asignar evaluación (qué evaluador evalúa a qué evaluado dentro de un ciclo)
  createReview:  (cycleId: PathId, data: unknown) => api.post(`/performance/cycles/${cycleId}/reviews`, data),
  updateReview:  (id: PathId, data: unknown)     => api.patch(`/performance/reviews/${id}`, data),
  submitReview:  (id: PathId)           => api.post(`/performance/reviews/${id}/submit`),
  // Plantilla de preguntas por ciclo
  listQuestions:    (cycleId: PathId)            => api.get(`/performance/cycles/${cycleId}/questions`),
  addQuestion:      (cycleId: PathId, data: unknown)      => api.post(`/performance/cycles/${cycleId}/questions`, data),
  updateQuestion:   (qId: PathId, data: unknown)          => api.patch(`/performance/questions/${qId}`, data),
  deleteQuestion:   (qId: PathId)                => api.delete(`/performance/questions/${qId}`),
  // Smart 360°: pool de evaluadores elegibles según tipo de revisión
  eligibleReviewers: (cycleId: PathId, revieweeId: PathId, type: string) =>
    api.get(`/performance/cycles/${cycleId}/eligible-reviewers/${revieweeId}/${type}`),
  // Campañas 360° (subject + multi-evaluator + dashboard agregado anonimizado)
  listCampaigns:    (cycleId: PathId)        => api.get(`/performance/cycles/${cycleId}/campaigns`),
  createCampaign:   (cycleId: PathId, data: unknown)  => api.post(`/performance/cycles/${cycleId}/campaigns`, data),
  campaignDashboard:(id: PathId)             => api.get(`/performance/campaigns/${id}/dashboard`),
  campaignDashboardPdf:(id: PathId)          => api.get(`/performance/campaigns/${id}/dashboard.pdf`,
                                                { responseType: 'blob' }),
  history360:       (userId: PathId)         => api.get(`/performance/users/${userId}/360-history`),
  // KPIs operativos (HR)
  orgKpis:          ()               => api.get('/performance/kpis'),
  cycleKpis:        (id: PathId)             => api.get(`/performance/cycles/${id}/kpis`),
  runReminders:     ()               => api.post('/performance/admin/run-reminders'),
  // Development plans
  listUserPlans:    (userId: PathId)         => api.get(`/performance/users/${userId}/dev-plans`),
  getPlan:          (id: PathId)             => api.get(`/performance/dev-plans/${id}`),
  createPlan:       (data: unknown)           => api.post('/performance/dev-plans', data),
  updatePlan:       (id: PathId, data: unknown)       => api.patch(`/performance/dev-plans/${id}`, data),
  addGoal:          (planId: PathId, data: unknown)   => api.post(`/performance/dev-plans/${planId}/goals`, data),
  updateGoal:       (id: PathId, data: unknown)       => api.patch(`/performance/dev-goals/${id}`, data),
  deleteGoal:       (id: PathId)             => api.delete(`/performance/dev-goals/${id}`),
}

// ── Capacity Planning ─────────────────────────────────────────────────────────
export const capacityApi = {
  board:       (params?: QueryParams)         => api.get('/capacity/board', { params }),
  createPlan:  (data: unknown)           => api.post('/capacity/plans', data),
  updatePlan:  (id: PathId, data: unknown)       => api.patch(`/capacity/plans/${id}`, data),
  deletePlan:  (id: PathId)             => api.delete(`/capacity/plans/${id}`),
}

// ── Profitability ─────────────────────────────────────────────────────────────
export const profitabilityApi = {
  get:             (projectId: PathId)          => api.get(`/profitability/${projectId}`),
  summary:         (params?: QueryParams)             => api.get('/profitability/summary', { params }),
  createMilestone: (projectId: PathId, data: unknown)    => api.post(`/profitability/${projectId}/milestones`, data),
  updateMilestone: (projectId: PathId, id: PathId, data: unknown)=> api.patch(`/profitability/${projectId}/milestones/${id}`, data),
  deleteMilestone: (projectId: PathId, id: PathId)      => api.delete(`/profitability/${projectId}/milestones/${id}`),
}

// ── BI Forecasting ────────────────────────────────────────────────────────────
export const biForecastingApi = {
  getMetrics:     ()                   => api.get('/bi/forecast/metrics'),
  // The backend forecasts a single metric via POST /bi/forecast {metric, ...}.
  forecast:       (metric: string, params?: QueryParams)     => api.post('/bi/forecast', { metric, ...(params || {}) }),
  multiForecast:  (data: unknown)               => api.post('/bi/forecast/multi', data),
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
  listConsents:        ()              => api.get('/bi/gdpr/consents'),
  getConsentHistory:   (userId: PathId)        => api.get(`/bi/gdpr/consent/${userId}/history`),
  createDsr:           (data: unknown)          => api.post('/bi/gdpr/dsr', data),
  listDsr:             (params?: QueryParams)        => api.get('/bi/gdpr/dsr', { params }),
  resolveDsr:          (id: PathId, data: unknown)      => api.patch(`/bi/gdpr/dsr/${id}/resolve`, data),
  executeDsrErasure:   (id: PathId)            => api.post(`/bi/gdpr/dsr/${id}/erasure-execute`),
  executeDsrPortability: (id: PathId)          => api.post(`/bi/gdpr/dsr/${id}/portability-export`),
  setFieldMask:        (data: unknown)          => api.post('/bi/gdpr/field-masks', data),
  getFieldMasks:       ()              => api.get('/bi/gdpr/field-masks'),
  getStats:            ()              => api.get('/bi/gdpr/stats'),
}

// ── BI Query Builder ──────────────────────────────────────────────────────────
export const biQueryBuilderApi = {
  getSchema:      (params?: QueryParams)             => api.get('/bi/query-builder/schema', { params }),
  previewQuery:   (data: unknown)               => api.post('/bi/query-builder/preview', data),
  saveQuery:      (data: unknown)               => api.post('/bi/query-builder/queries', data),
  listQueries:    ()                   => api.get('/bi/query-builder/queries'),
  executeQuery:   (id: PathId)                 => api.post(`/bi/query-builder/queries/${id}/execute`),
  deleteQuery:    (id: PathId)                 => api.delete(`/bi/query-builder/queries/${id}`),
}

// ── BI Conditional Delivery ───────────────────────────────────────────────────
export const biConditionalDeliveryApi = {
  createRule:     (data: unknown)               => api.post('/bi/delivery/rules', data),
  listRules:      ()                   => api.get('/bi/delivery/rules'),
  updateRule:     (id: PathId, data: unknown)           => api.patch(`/bi/delivery/rules/${id}`, data),
  evaluate:       (id: PathId, data: unknown = {})      => api.post(`/bi/delivery/rules/${id}/evaluate`, data),
}

// ── BI ETL Connectors ─────────────────────────────────────────────────────────
export const biEtlApi = {
  listConnectors: ()                   => api.get('/bi/etl/connectors'),
  configure:      (id: string, body: { enabled?: boolean; entity?: string; config?: Record<string, string> }) =>
    api.patch(`/bi/etl/connectors/${encodeURIComponent(id)}`, body),
  test:           (id: string)              => api.post(`/bi/etl/connectors/${encodeURIComponent(id)}/test`),
  sync:           (id: string)              => api.post(`/bi/etl/connectors/${encodeURIComponent(id)}/sync`),
  getLog:         (id: string)              => api.get(`/bi/etl/connectors/${encodeURIComponent(id)}/log`),
  crearFuente:    (body: { nombre: string; config: Record<string, string> }) => api.post('/bi/etl/sources', body),
  borrarFuente:   (id: string)              => api.delete(`/bi/etl/sources/${encodeURIComponent(id)}`),
}

// ── BI Office 365 ─────────────────────────────────────────────────────────────
export const biO365Api = {
  getConfig:      ()                   => api.get('/bi/o365/config'),
  saveConfig:     (data: unknown)               => api.put('/bi/o365/config', data),
  triggerSync:    (data: unknown)               => api.post('/bi/o365/sync', data),
  getReport:      (name: PathId, params?: QueryParams)       => api.get(`/bi/o365/reports/${name}`, { params }),
  getAdoption:    ()                   => api.get('/bi/o365/adoption'),
}

// ── Voice Agent (IVR) ─────────────────────────────────────────────────────────
export const voiceAgentApi = {
  getConfig:      ()                   => api.get('/sd/voice/config'),
  updateConfig:   (data: unknown)               => api.put('/sd/voice/config', data),
  createSession:  (data: unknown)               => api.post('/sd/voice/sessions', data),
  listSessions:   (params?: QueryParams)             => api.get('/sd/voice/sessions', { params }),
  addTurn:        (id: PathId, data: unknown)           => api.post(`/sd/voice/sessions/${id}/turn`, data),
  closeSession:   (id: PathId, data: unknown)           => api.post(`/sd/voice/sessions/${id}/close`, data),
  createTicket:   (id: PathId)                 => api.post(`/sd/voice/sessions/${id}/ticket`),
}

// ── Incident Assignment ML ────────────────────────────────────────────────────
export const incidentAssignmentApi = {
  stats:          ()                   => api.get('/sd/assignment/stats'),
}

// ── Change Rollout ────────────────────────────────────────────────────────────
export const changeRolloutApi = {
  listPlans:      (changeId: PathId)           => api.get(`/sd/changes/${changeId}/rollout-plans`),
  createPlan:     (changeId: PathId, data: unknown)     => api.post(`/sd/changes/${changeId}/rollout-plans`, data),
  approvePlan:    (id: PathId)                 => api.post(`/sd/changes/rollout-plans/${id}/approve`),
  advancePhase:   (id: PathId, data: unknown)           => api.post(`/sd/changes/rollout-plans/${id}/advance-phase`, data),
  simulatePlan:   (changeId: PathId, planId: PathId)   => api.post(`/sd/changes/${changeId}/rollout-plans/${planId}/simulate`, {}),
  rollback:       (changeId: PathId, data: unknown)     => api.post(`/sd/changes/${changeId}/rollback`, data),
}

// ── CMDB 3D Graph ─────────────────────────────────────────────────────────────
export const cmdb3dApi = {
  getGraph:       (params?: QueryParams)             => api.get('/sd/cmdb/3d-graph', { params }),
  blastRadius:    (ciId: PathId)               => api.get(`/sd/cmdb/blast-radius/${ciId}`),
}

// ── WebSocket Ticket ──────────────────────────────────────────────────────────
export const wsApi = {
  ticket: () => api.get('/ws/ticket'),
}

// ── Sprint (project-scoped) ───────────────────────────────────────────────────
export const projectSprintsApi = {
  list:          (projectId: PathId)                    => api.get(`/sprints/${projectId}/sprints`),
  create:        (projectId: PathId, data: unknown)              => api.post(`/sprints/${projectId}/sprints`, data),
  update:        (projectId: PathId, id: PathId, data: unknown)          => api.patch(`/sprints/${projectId}/sprints/${id}`, data),
  start:         (projectId: PathId, id: PathId)                => api.post(`/sprints/${projectId}/sprints/${id}/start`),
  close:         (projectId: PathId, id: PathId)                => api.post(`/sprints/${projectId}/sprints/${id}/close`),
  burndown:      (projectId: PathId, id: PathId)                => api.get(`/sprints/${projectId}/sprints/${id}/burndown`),
  backlog:       (projectId: PathId)                    => api.get(`/sprints/${projectId}/backlog`),
  velocity:      (projectId: PathId)                    => api.get(`/sprints/${projectId}/velocity`),
  addTasks:      (projectId: PathId, sprintId: PathId, taskIds: PathId[]) => api.post(`/sprints/${projectId}/sprints/${sprintId}/tasks`, { task_ids: taskIds }),
  removeTask:    (projectId: PathId, sprintId: PathId, taskId: PathId)  => api.delete(`/sprints/${projectId}/sprints/${sprintId}/tasks/${taskId}`),
  retrospective:      (projectId: PathId, sprintId: PathId)       => api.get(`/projects/${projectId}/sprints/${sprintId}/retrospective`),
  saveRetrospective:  (projectId: PathId, sprintId: PathId, data: unknown) => api.put(`/projects/${projectId}/sprints/${sprintId}/retrospective`, data),
  burnup:             (projectId: PathId, sprintId: PathId)       => api.get(`/sprints/${projectId}/sprints/${sprintId}/burnup`),
}

// ── Portal Clients ────────────────────────────────────────────────────────────
export const portalClientsApi = {
  list:         (params?: QueryParams)   => api.get('/portal/clients', { params }),
  create:       (data: unknown)     => api.post('/portal/clients', data),
  update:       (id: PathId, data: unknown) => api.patch(`/portal/clients/${id}`, data),
  translations: ()         => api.get('/portal/translations'),
  saveTranslations: (data: unknown) => api.post('/portal/translations', data),
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
  updatePermission: (role: PathId, module: PathId, action: PathId, data: unknown) => api.patch(`/grc/permissions/${role}/${module}/${action}`, data),
  sodRules:         ()                           => api.get('/grc/sod-rules'),
  createSodRule:    (data: unknown)                       => api.post('/grc/sod-rules', data),
  updateSodRule:    (id: PathId, data: unknown)                   => api.patch(`/grc/sod-rules/${id}`, data),
  deleteSodRule:    (id: PathId)                         => api.delete(`/grc/sod-rules/${id}`),
  sodCheck:         ()                           => api.get('/grc/sod-check'),
  violations:       (params?: QueryParams)                     => api.get('/grc/violations', { params }),
  resolveViolation: (id: PathId, data: unknown)                   => api.patch(`/grc/violations/${id}/resolve`, data),
  auditLog:         (params?: QueryParams)                     => api.get('/grc/audit-log', { params }),
  // Revisión 2026-11: explicador de accesos.
  explainAccess:    (params: { user_id: string; method: string; path: string }) => api.get('/grc/access-explainer', { params }),
  explainerRoutes:  ()                           => api.get('/grc/access-explainer/routes'),
  complianceReport: ()                           => api.get('/grc/compliance-report'),
  complianceReportSigned: ()                     => api.get('/grc/compliance-report', { params: { signed: true }, responseType: 'blob' }),
}

// ── Automations ───────────────────────────────────────────────────────────────
export const automationsApi = {
  list:       ()         => api.get('/automations'),
  templates:  ()         => api.get('/automations/templates/list'),
  create:     (data: unknown)     => api.post('/automations', data),
  update:     (id: PathId, data: unknown) => api.patch(`/automations/${id}`, data),
  delete:     (id: PathId)       => api.delete(`/automations/${id}`),
  test:       (id: PathId)       => api.post(`/automations/${id}/test`),
  executions: (id: PathId)       => api.get(`/automations/${id}/executions`),
  catalog:    ()         => api.get('/automations/catalog'),
}

export const autoWorkflowsApi = {
  list:   ()             => api.get('/automation-workflows'),
}

// ── Scheduled Reports ─────────────────────────────────────────────────────────
export const scheduledReportsApi = {
  list:   ()         => api.get('/billing-reports/scheduled-reports'),
  create: (data: unknown)     => api.post('/billing-reports/scheduled-reports', data),
  delete: (id: PathId)       => api.delete(`/billing-reports/scheduled-reports/${id}`),
  run:    (id: PathId)       => api.post(`/billing-reports/scheduled-reports/${id}/run`),
  toggle: (id: PathId, data: unknown) => api.patch(`/billing-reports/scheduled-reports/${id}`, data),
}

// ── AI Providers ──────────────────────────────────────────────────────────────
export const aiProvidersApi = {
  spendToday: () => api.get('/ai-providers/spend-today'),
  list:        ()         => api.get('/ai-providers'),
  catalog:     ()         => api.get('/ai-providers/catalog'),
  stats:       ()         => api.get('/ai-providers/stats'),
  diagnostics: ()         => api.get('/ai-providers/diagnostics'),
  create:      (data: unknown)     => api.post('/ai-providers', data),
  update:      (id: PathId, data: unknown) => api.patch(`/ai-providers/${id}`, data),
  delete:      (id: PathId)       => api.delete(`/ai-providers/${id}`),
  test:        (id: PathId)       => api.post(`/ai-providers/${id}/test`),
  syncModels:  (id: PathId)       => api.post(`/ai-providers/${id}/sync-models`),
  setDefault:  (id: PathId)       => api.post(`/ai-providers/${id}/set-default`),
  syncAll:     ()         => api.post('/ai-providers/sync-models/all'),
  // Revisión 2026-11 (de contecmind): probar y descubrir sin guardar, y por función.
  testConfig:     (data: unknown) => api.post('/ai-providers/test-config', data),
  discoverModels: (data: unknown) => api.post('/ai-providers/discover-models', data),
  getRouting:     ()              => api.get('/ai-providers/routing'),
  saveRouting:    (routes: unknown) => api.put('/ai-providers/routing', { routes }),
  // El proveedor configurado en .env: se ve, se prueba y se puede importar.
  testEnv:        ()              => api.post('/ai-providers/env/test'),
  importEnv:      ()              => api.post('/ai-providers/env/import'),
}

// ── Service Desk Config ───────────────────────────────────────────────────────
export const sdMetricsApi = {
  itil:             (params?: QueryParams) => api.get('/sd/metrics/itil', { params }),
  agentPerformance: (params?: QueryParams) => api.get('/sd/metrics/agent-performance', { params }),
}

export const sdCatalogApi = {
  list:           ()         => api.get('/sd/catalog'),
  createCategory: (data: unknown)     => api.post('/sd/catalog/categories', data),
  updateCategory: (id: PathId, data: unknown) => api.patch(`/sd/catalog/categories/${id}`, data),
  deleteCategory: (id: PathId)       => api.delete(`/sd/catalog/categories/${id}`),
  createService:  (data: unknown)     => api.post('/sd/catalog/services', data),
  updateService:  (id: PathId, data: unknown) => api.patch(`/sd/catalog/services/${id}`, data),
  deleteService:  (id: PathId)       => api.delete(`/sd/catalog/services/${id}`),
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
  update: (id: PathId, data: unknown) => api.patch(`/sd/sla-policies/${id}`, data),
  delete: (id: PathId)       => api.delete(`/sd/sla-policies/${id}`),
}

export const sdEscalationApi = {
  list:   ()         => api.get('/sd/escalation-rules'),
  create: (data: unknown)     => api.post('/sd/escalation-rules', data),
  update: (id: string, data: unknown) => api.patch(`/sd/escalation-rules/${id}`, data),
  delete: (id: string)       => api.delete(`/sd/escalation-rules/${id}`),
  logs:   (limit = ESCALATION_LOGS_LIMIT) => api.get('/sd/escalation-rules/logs', { params: { limit } }),
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
  alerts: (limit = MONITORING_ALERTS_LIMIT) => api.get('/sd/events/alerts', { params: { limit } }),
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
  messages: (limit = INBOUND_MESSAGES_LIMIT) => api.get('/sd/inbound/messages', { params: { limit } }),
  test:     ()           => api.post('/sd/inbound/test'),
  run:      ()           => api.post('/sd/inbound/run'),
}

export const sdGroupsApi = {
  list:         ()         => api.get('/sd/groups'),
  create:       (data: unknown)     => api.post('/sd/groups', data),
  update:       (id: PathId, data: unknown) => api.patch(`/sd/groups/${id}`, data),
  delete:       (id: PathId)       => api.delete(`/sd/groups/${id}`),
  addMember:    (gid: PathId, uid: PathId) => api.post(`/sd/groups/${gid}/members/${uid}`),
  removeMember: (gid: PathId, uid: PathId) => api.delete(`/sd/groups/${gid}/members/${uid}`),
}

export const sdTemplatesApi = {
  list:   ()         => api.get('/sd/ticket-templates'),
  create: (data: unknown)     => api.post('/sd/ticket-templates', data),
  update: (id: PathId, data: unknown) => api.patch(`/sd/ticket-templates/${id}`, data),
  delete: (id: PathId)       => api.delete(`/sd/ticket-templates/${id}`),
}

export const sdCannedApi = {
  list:   (params?: QueryParams)   => api.get('/sd/canned-responses', { params }),
  create: (data: unknown)     => api.post('/sd/canned-responses', data),
  update: (id: PathId, data: unknown) => api.patch(`/sd/canned-responses/${id}`, data),
  delete: (id: PathId)       => api.delete(`/sd/canned-responses/${id}`),
}

export const sdAnnouncementsApi = {
  list:   ()     => api.get('/sd/announcements'),
  create: (data: unknown) => api.post('/sd/announcements', data),
  delete: (id: PathId)   => api.delete(`/sd/announcements/${id}`),
}

export const sdRoutingApi = {
  list:                ()         => api.get('/sd/routing-rules'),
  create:              (data: unknown)     => api.post('/sd/routing-rules', data),
  update:              (id: PathId, data: unknown) => api.patch(`/sd/routing-rules/${id}`, data),
  delete:              (id: PathId)       => api.delete(`/sd/routing-rules/${id}`),
  majorIncidents:      ()         => api.get('/sd/major-incidents'),
  createMajorIncident: (data: unknown)     => api.post('/sd/major-incidents', data),
}

export const sdKbApi = {
  list:        (params?: QueryParams)   => api.get('/sd/kb', { params }),
  get:         (id: PathId)        => api.get(`/sd/kb/${id}`),
  create:      (data: unknown)     => api.post('/sd/kb', data),
  update:      (id: PathId, data: unknown) => api.patch(`/sd/kb/${id}`, data),
  delete:      (id: PathId)       => api.delete(`/sd/kb/${id}`),
  submit:      (id: PathId)       => api.post(`/sd/kb/${id}/submit`),
  review:      (id: PathId, data: unknown) => api.post(`/sd/kb/${id}/review`, data),
  knownErrors:        ()     => api.get('/sd/known-errors'),
  knownErrorTickets:  (id: PathId)   => api.get(`/sd/known-errors/${id}/tickets`),
  // Calidad de la base (revisión 2026-11)
  quality:            ()     => api.get('/sd/kb/quality'),
  runQuality:         ()     => api.post('/sd/kb/quality/run'),
  createCorrection:   (data: { question: string; answer: string; is_public?: boolean; gap_id?: string }) => api.post('/sd/kb/corrections', data),
  setCorrectionStatus: (id: string, status: string) => api.patch(`/sd/kb/corrections/${id}`, { status }),
  setGapStatus:       (id: string, status: string) => api.patch(`/sd/kb/gaps/${id}`, { status }),
  setFindingStatus:   (id: string, status: string) => api.patch(`/sd/kb/findings/${id}`, { status }),
}

// ── Enterprise ────────────────────────────────────────────────────────────────
export const webhooksApi = {
  list:   ()         => api.get('/webhooks'),
  create: (data: unknown)     => api.post('/webhooks', data),
  delete: (id: PathId)       => api.delete(`/webhooks/${id}`),
  logs:   (id: PathId)       => api.get(`/webhooks/${id}/logs`),
}

export const gdprApi = {
  list:    ()     => api.get('/gdpr/requests'),
  create:  (data: unknown) => api.post('/gdpr/requests', data),
  process: (id: PathId)   => api.post(`/gdpr/requests/${id}/process`),
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
  delete: (id: PathId)           => api.delete(`/oauth-integrations/${id}`),
  sync:   (id: PathId, data: unknown)     => api.post(`/oauth-integrations/${id}/sync`, data),
}

export const enterpriseApi = {
  auditLog:                (params?: QueryParams) => api.get('/enterprise/audit-log', { params }),
  // Revisión 2026-11: cadena a prueba de manipulación.
  verifyAuditChain:        (params?: { expected_seq?: number; expected_hash?: string }) => api.get('/enterprise/audit-log/chain/verify', { params }),
  exportAuditChain:        () => api.get('/enterprise/audit-log/chain/export', { responseType: 'blob' }),
  ssoList:                 ()       => api.get('/enterprise/sso'),
  ssoCreate:               (data: unknown)   => api.post('/enterprise/sso', data),
  ssoUpdate:               (id: PathId, data: unknown) => api.patch(`/enterprise/sso/${id}`, data),
  ssoDelete:               (id: PathId)     => api.delete(`/enterprise/sso/${id}`),
  ssoTest:                 (id: PathId)     => api.post(`/enterprise/sso/${id}/test`),
}

export const integrationsHubApi = {
  testSlack:  (data: unknown) => api.post('/integrations-hub/slack/test', data),
  testTeams:  (data: unknown) => api.post('/integrations-hub/teams/test', data),
  testJira:   (data: unknown) => api.post('/integrations-hub/jira/test', data),
}

export const apiKeysApi = {
  list:   ()         => api.get('/bookings/api-keys'),
  create: (data: unknown)     => api.post('/bookings/api-keys', data),
  delete: (id: PathId)       => api.delete(`/bookings/api-keys/${id}`),
}

// ── Client Portal ─────────────────────────────────────────────────────────────
export const portalApi = {
  // Listar/crear/editar usuarios del portal: `portalClientsApi` (auditoria 2026-11, #45).
  deleteClient:         (id: PathId)              => api.delete(`/portal/clients/${id}`),
  uat:                  (params?: QueryParams)          => api.get('/portal/uat/team', { params }),
  createUat:            (projectId: PathId, data: unknown) => api.post(`/portal/uat/${projectId}`, data),
  addTestCase:          (id: PathId, data: unknown)        => api.post(`/portal/uat/${id}/test-cases`, data),
  updateUatStatus:      (id: PathId, params?: QueryParams)      => api.patch(`/portal/uat/issues/${id}`, null, { params }),
  featureRequests:      (params?: QueryParams)          => api.get('/portal/feature-requests/team', { params }),
  respondFeatureRequest:(id: PathId, data: unknown)        => api.post(`/portal/feature-requests/${id}/respond`, data),
  documents:            (params?: QueryParams)          => api.get('/portal/documents/team', { params }),
  createDocument:       (projectId: PathId, data: unknown) => api.post('/portal/documents', data, { params: { project_id: projectId } }),
  stats:                (projectId: PathId)       => api.get(`/portal/stats/${projectId}`),
}

// ── Client Extensions ─────────────────────────────────────────────────────────
export const clientExtApi = {
  projects:           (cid: PathId)       => api.get(`/clients/${cid}/projects`),
  availableProjects:  (cid: PathId)       => api.get(`/clients/${cid}/projects/available`),
  linkProject:        (cid: PathId, pid: PathId)  => api.post(`/clients/${cid}/projects/${pid}/link`),
  unlinkProject:      (cid: PathId, pid: PathId)  => api.delete(`/clients/${cid}/projects/${pid}/link`),
  createContact:      (cid: PathId, data: unknown) => api.post(`/clients/${cid}/contacts`, data),
  deleteContact:      (cid: PathId, id: PathId)   => api.delete(`/clients/${cid}/contacts/${id}`),
  licenses:           (cid: PathId)       => api.get(`/clients/${cid}/licenses`),
  linkLicense:        (cid: PathId, data: unknown) => api.post(`/clients/${cid}/licenses`, data),
  unlinkLicense:      (cid: PathId, id: PathId)   => api.delete(`/clients/${cid}/licenses/${id}`),
  contracts:          (cid: PathId)       => api.get(`/clients/${cid}/contracts`),
  linkContract:       (cid: PathId, data: unknown) => api.post(`/clients/${cid}/contracts`, data),
  unlinkContract:     (cid: PathId, id: PathId)   => api.delete(`/clients/${cid}/contracts/${id}`),
  portalConfig:       (cid: PathId)       => api.get(`/clients/${cid}/portal-config`),
  updatePortalConfig: (cid: PathId, data: unknown) => api.patch(`/clients/${cid}/portal-config`, data),
}

// ── SLA Calendars ─────────────────────────────────────────────────────────────
export const slaCalendarsApi = {
  list:          () => api.get('/cmdb/sla-calendars'),
  create:        (data: unknown) => api.post('/cmdb/sla-calendars', data),
  update:        (id: PathId, data: unknown) => api.patch(`/cmdb/sla-calendars/${id}`, data),
  delete:        (id: PathId) => api.delete(`/cmdb/sla-calendars/${id}`),
  holidays:      (calId: PathId) => api.get(`/cmdb/sla-calendars/${calId}/holidays`),
  createHoliday: (calId: PathId, data: unknown) => api.post(`/cmdb/sla-calendars/${calId}/holidays`, data),
  updateHoliday: (calId: PathId, id: PathId, data: unknown) => api.patch(`/cmdb/sla-calendars/${calId}/holidays/${id}`, data),
  deleteHoliday: (calId: PathId, id: PathId) => api.delete(`/cmdb/sla-calendars/${calId}/holidays/${id}`),
  checkDate:     (calId: PathId, date: string) => api.get(`/cmdb/sla-calendars/${calId}/check-date?check_date=${date}`),
}

// ── Project Workflows ─────────────────────────────────────────────────────────
export const projectWorkflowsApi = {
  get:              (projectId: PathId) => api.get(`/project-workflows/${projectId}`),
  init:             (projectId: PathId) => api.post(`/project-workflows/${projectId}/init`),
  createState:      (projectId: PathId, data: unknown) => api.post(`/project-workflows/${projectId}/states`, data),
  updateState:      (projectId: PathId, stateId: PathId, data: unknown) => api.patch(`/project-workflows/${projectId}/states/${stateId}`, data),
  deleteState:      (projectId: PathId, stateId: PathId) => api.delete(`/project-workflows/${projectId}/states/${stateId}`),
  createTransition: (projectId: PathId, data: unknown) => api.post(`/project-workflows/${projectId}/transitions`, data),
  deleteTransition: (projectId: PathId, transId: PathId) => api.delete(`/project-workflows/${projectId}/transitions/${transId}`),
  resetWorkflow:    (projectId: PathId) => api.delete(`/project-workflows/${projectId}/reset`),
}

// ── Sprint Plans ──────────────────────────────────────────────────────────────
export const sprintPlansApi = {
  generate:     (data: unknown) => api.post('/cmdb/sprint-plans/generate', data),
  get:          (projectId: PathId) => api.get(`/cmdb/sprint-plans/${projectId}`),
  updateStatus: (id: PathId, status: string) => api.patch(`/cmdb/sprint-plans/${id}/status?status=${status}`),
  delete:       (id: PathId) => api.delete(`/cmdb/sprint-plans/${id}`),
}

// ── Organizations ─────────────────────────────────────────────────────────────
export const organizationsApi = {
  list:       () => api.get('/organizations'),
  get:        (id: PathId) => api.get(`/organizations/${id}`),
  create:     (data: unknown) => api.post('/organizations', data),
  update:     (id: PathId, data: unknown) => api.patch(`/organizations/${id}`, data),
  assignUser: (orgId: PathId, data: unknown) => api.post(`/organizations/${orgId}/assign-user`, data),
  removeUser: (orgId: PathId, userId: PathId) => api.delete(`/organizations/${orgId}/remove-user/${userId}`),
  // Revisión multitenant 2026-11: baja con cuarentena, exportación y «entrar como».
  requestDeletion: (orgId: PathId, reason: string) => api.post(`/organizations/${orgId}/deletion`, { reason }),
  cancelDeletion:  (orgId: PathId) => api.delete(`/organizations/${orgId}/deletion`),
  exportData:      (orgId: PathId) => api.get(`/organizations/${orgId}/export`, { responseType: 'blob' }),
  impersonate:     (orgId: PathId, user_id: string, reason: string) => api.post(`/organizations/${orgId}/impersonate`, { user_id, reason }),
}

// ── Templates ─────────────────────────────────────────────────────────────────
export const templatesApi = {
  list:        () => api.get('/billing-reports/templates'),
  create:      (data: unknown) => api.post('/billing-reports/templates', data),
  instantiate: (tplId: PathId, data: unknown) => api.post(`/billing-reports/templates/${tplId}/instantiate`, data),
}

// ── Dependencies ──────────────────────────────────────────────────────────────
// El router real es /task-dependencies. Con el prefijo equivocado la consulta
// daba 404 y el Gantt de proyecto se dibujaba SIN dependencias, sin error
// visible: la pagina trata la respuesta fallida como lista vacia. Auditoria
// 2026-08 (#37).
export const dependenciesApi = {
  get: (projectId: PathId) => api.get(`/task-dependencies/${projectId}`),
}

// ── Jira Integration ─────────────────────────────────────────────────────────
export const jiraApi = {
  config:     () => api.get('/jira/config'),
  saveConfig: (data: unknown) => api.post('/jira/config', data),
  issues:     () => api.get('/jira/issues'),
  linked:     () => api.get('/jira/linked'),
  test:       () => api.get('/jira/test'),
  sync:       (data: unknown) => api.post('/jira/sync', data),
  // JiraPushIn exige project_id (sin cuerpo daba 422). Con cola responde 202
  // `{status: 'queued'}`; sin cola `{created, skipped, errors}`.
  push:       (data: { project_id: string; jira_project_key?: string; dry_run?: boolean }): Promise<AxiosResponse<{ status?: string; created?: number; skipped?: number; errors?: number }>> =>
    api.post('/jira/push', data),
  // Auditoria 2026-11 (#14, backend): secreto del webhook POR ORGANIZACION; solo
  // admin; el servidor lo devuelve una unica vez (rotarlo invalida el anterior).
  rotarSecretoWebhook: (): Promise<AxiosResponse<{ secret: string; header: string; webhook_paths: string[] }>> =>
    api.post('/jira/webhook-secret'),
}

// ── SD Workflow Designer ──────────────────────────────────────────────────────
export const sdWorkflowDesignerApi = {
  templates:      () => api.get('/sd/workflow-designer/templates'),
  blueprints:     (params?: QueryParams) => api.get('/sd/workflow-designer/blueprints', { params }),
  blueprint:      (id: PathId) => api.get(`/sd/workflow-designer/blueprints/${id}`),
  createBlueprint:(data: unknown) => api.post('/sd/workflow-designer/blueprints', data),
  createVersion:  (id: PathId, data: unknown) => api.post(`/sd/workflow-designer/blueprints/${id}/versions`, data),
  publish:        (id: PathId, version: PathId) => api.post(`/sd/workflow-designer/blueprints/${id}/publish/${version}`),
  validate:       (data: unknown) => api.post('/sd/workflow-designer/validate', data),
  clone:          (id: PathId, data: unknown) => api.post(`/sd/workflow-designer/blueprints/${id}/clone`, data),
  archive:        (id: PathId) => api.delete(`/sd/workflow-designer/blueprints/${id}`),
  // Runtime
  startRun:       (id: PathId, data: unknown) => api.post(`/sd/workflow-designer/blueprints/${id}/runs`, data),
  runs:           (params?: QueryParams) => api.get('/sd/workflow-designer/runs', { params }),
  run:            (rid: PathId) => api.get(`/sd/workflow-designer/runs/${rid}`),
  resumeRun:      (rid: PathId, data: unknown) => api.post(`/sd/workflow-designer/runs/${rid}/resume`, data),
  cancelRun:      (rid: PathId, reason: string) => api.post(`/sd/workflow-designer/runs/${rid}/cancel`, { reason }),
}

// ── Mentions & Comments ───────────────────────────────────────────────────────
export const mentionsApi = {
  comments:           (entityType: PathId, entityId: PathId) => api.get('/epics/comments', { params: { entity_type: entityType, entity_id: entityId } }),
  createComment:      (entityType: PathId, entityId: PathId, data: unknown) => api.post('/epics/comments', data, { params: { entity_type: entityType, entity_id: entityId } }),
  resolveComment:     (id: PathId) => api.patch(`/epics/comments/${id}/resolve`),
  deleteComment:      (id: PathId) => api.delete(`/epics/comments/${id}`),
  mentions:           (onlyUnread: boolean) => api.get('/activity/mentions/my', { params: { unread_only: onlyUnread } }),
  markMentionRead:    (id: PathId) => api.post(`/activity/mentions/${id}/read`),
  markAllMentionsRead:() => api.post('/epics/mentions/read-all'),
}

// ── Issue Types ───────────────────────────────────────────────────────────────
export const issueTypesApi = {
  list:   (projectId: PathId) => api.get(`/issue-types/${projectId}`),
  create: (projectId: PathId, data: unknown) => api.post(`/issue-types/${projectId}`, data),
  update: (projectId: PathId, id: PathId, data: unknown) => api.patch(`/issue-types/${projectId}/${id}`, data),
  init:   (projectId: PathId) => api.post(`/issue-types/${projectId}/init`),
  delete: (projectId: PathId, id: PathId) => api.delete(`/issue-types/${projectId}/${id}`),
}

// ── Project Permissions ───────────────────────────────────────────────────────
export const permissionsApi = {
  list:   (projectId: PathId) => api.get(`/permissions/${projectId}`),
  create: (projectId: PathId, data: unknown) => api.post(`/permissions/${projectId}`, data),
  update: (projectId: PathId, id: PathId, data: unknown) => api.patch(`/permissions/${projectId}/${id}`, data),
  delete: (projectId: PathId, id: PathId) => api.delete(`/permissions/${projectId}/${id}`),
}

// ── eSign ─────────────────────────────────────────────────────────────────────
export const esignApi = {
  getConfig:   () => api.get('/esign/config'),
  saveConfig:  (data: unknown) => api.patch('/esign/config', data),
}

// ── Public Forms ──────────────────────────────────────────────────────────────
export const formsApi = {
  list:        () => api.get('/forms'),
  create:      (data: unknown) => api.post('/forms', data),
  update:      (id: PathId, data: unknown) => api.patch(`/forms/${id}`, data),
  submissions: (id: PathId) => api.get(`/forms/${id}/submissions`),
  delete:      (id: PathId) => api.delete(`/forms/${id}`),
}

// ── Scenarios ─────────────────────────────────────────────────────────────────
export const scenariosApi = {
  list:    () => api.get('/scenarios'),
  get:     (id: PathId) => api.get(`/scenarios/${id}`),
  create:  (data: unknown) => api.post('/scenarios', data),
  compute: (id: PathId) => api.post(`/scenarios/${id}/compute`),
  delete:  (id: PathId) => api.delete(`/scenarios/${id}`),
}

// ── Governance ────────────────────────────────────────────────────────────────
export const governanceApi = {
  config:  () => api.get('/governance/config'),
  stats:   () => api.get('/governance/stats'),
  logs:    () => api.get(`/governance/logs?limit=${GOVERNANCE_LOGS_LIMIT}`),
  update:  (module: PathId, data: unknown) => api.patch(`/governance/config/${module}`, data),
  // Revisión 2026-11: retención y bloqueo legal.
  retentionPolicies: () => api.get('/governance/retention/policies'),
  saveRetention:     (entity: string, data: { keep_days: number; is_active: boolean }) => api.put(`/governance/retention/policies/${entity}`, data),
  retentionPreview:  (entity: string, keep_days: number) => api.get('/governance/retention/preview', { params: { entity, keep_days } }),
  retentionRun:      () => api.post('/governance/retention/run'),
  legalHolds:        () => api.get('/governance/legal-holds'),
  createLegalHold:   (data: { case_reference: string; reason?: string; entity: string; field: string; value: string }) => api.post('/governance/legal-holds', data),
  releaseLegalHold:  (id: string) => api.post(`/governance/legal-holds/${id}/release`),
}

// ── Epic Dependencies ─────────────────────────────────────────────────────────
export const epicDependenciesApi = {
  get:    (projectId: PathId) => api.get(`/epic-dependencies/${projectId}`),
  create: (data: unknown) => api.post('/epic-dependencies', data),
  delete: (id: PathId) => api.delete(`/epic-dependencies/${id}`),
}

// ── Developer Apps ────────────────────────────────────────────────────────────
export const developerAppsApi = {
  list:         () => api.get('/developer/apps'),
  create:       (data: unknown) => api.post('/developer/apps', data),
  update:       (id: PathId, data: unknown) => api.patch(`/developer/apps/${id}`, data),
  rotateSecret: (id: PathId) => api.post(`/developer/apps/${id}/rotate-secret`),
  delete:       (id: PathId) => api.delete(`/developer/apps/${id}`),
}

// ── Task Dependencies ─────────────────────────────────────────────────────────
export const taskDependenciesApi = {
  getByProject: (projectId: PathId) => api.get(`/tasks/dependencies/${projectId}`),
  create:       (data: unknown) => api.post('/tasks/dependencies', data),
  delete:       (id: PathId) => api.delete(`/tasks/dependencies/${id}`),
  bulkDates:    (updates: unknown) => api.post('/tasks/bulk-dates', { updates }),
}

// ── M365 ──────────────────────────────────────────────────────────────────────
export const m365Api = {
  status:         () => api.get('/m365/status'),
  syncCalendar:   (upn: PathId, days: number) => api.post('/m365/calendar/sync', null, { params: { user_upn: upn, days } }),
  syncMilestones: (data: unknown) => api.post('/m365/calendar/sync-milestones', data),
  teamsNotify:    (data: unknown) => api.post('/m365/teams/notify', data),
}

// ── Meetings AI ───────────────────────────────────────────────────────────────
export const meetingsAIApi = {
  list:        () => api.get('/ai-modules/meetings'),
  get:         (id: PathId) => api.get(`/ai-modules/meetings/${id}`),
  process:     (data: unknown) => api.post('/ai-modules/meetings/process', data),
  createTasks: (id: PathId) => api.post(`/ai-modules/meetings/${id}/create-tasks`, {}),
}

// ── Contracts AI (H22) ────────────────────────────────────────────────────────
export const contractsAIApi = {
  list:       (params?: QueryParams) => api.get('/ai-modules/contracts-ai', { params }),
  get:        (id: PathId)     => api.get(`/ai-modules/contracts-ai/${id}`),
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
// Auditoria 2026-11: el unico TOTP es el que exige el login (/auth/mfa/*). Las
// rutas /mfa/* escribian otra tabla que el login no miraba y se retiraron.
export const mfaApi = {
  status: () => api.get('/auth/mfa/status'),
  // Con un segundo factor ya activo (TOTP o passkey), pide contrasena o codigo (ReautenticacionIn).
  setup:  (reauth?: { password?: string; code?: string }) => api.post('/auth/mfa/setup', reauth ?? {}),
  verify: (code: string) => api.post('/auth/mfa/verify-setup', { code }),
  disable:(code: string) => api.post('/auth/mfa/disable', { code }),
}

// ── Oracle Predictions ────────────────────────────────────────────────────────
export const oracleApi = {
  predictions: (params?: QueryParams) => api.get('/oracle/predictions', { params }),
  run:         () => api.post('/oracle/run'),
  acknowledge: (id: PathId) => api.post(`/oracle/predictions/${id}/acknowledge`),
}

// ── Import ────────────────────────────────────────────────────────────────────
export const importApi = {
  template: (entityType: PathId) => api.get(`/billing-reports/import/template/${entityType}`),
  jobs:     () => api.get('/billing-reports/import/jobs'),
  validate: (entityType: PathId, fd: unknown) => api.post('/billing-reports/import/validate', fd, { params: { entity_type: entityType }, headers: { 'Content-Type': 'multipart/form-data' } }),
  execute:  (entityType: PathId, fd: unknown) => api.post('/billing-reports/import/execute', fd, { params: { entity_type: entityType }, headers: { 'Content-Type': 'multipart/form-data' } }),
}

// ── Report Builder ────────────────────────────────────────────────────────────
export const reportBuilderApi = {
  schema:         () => api.get('/reports/schema'),
  preview:        (data: unknown) => api.post('/reports/preview', data),
  export:         (data: unknown, config: AxiosRequestConfig) => api.post('/reports/export', data, config),
  templates:      () => api.get('/reports/templates'),
  saveTemplate:   (data: unknown) => api.post('/reports/templates', data),
  deleteTemplate: (id: PathId) => api.delete(`/reports/templates/${id}`),
}

// ── Burnout Risk / Resources ──────────────────────────────────────────────────
export const burnoutRiskApi = {
  get:     (params?: QueryParams) => api.get('/resources/burnout-risk', { params }),
  compute: () => api.post('/resources/burnout-risk/compute'),
}

// ── Git ───────────────────────────────────────────────────────────────────────
export const gitApi = {
  pullRequests: () => api.get('/git/pull-requests'),
  deployments:  () => api.get('/git/deployments'),
  webhooks:     () => api.get('/git/webhooks'),
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
  seedCountries:    (force: boolean)    => api.post('/user-costs/countries/seed', null, { params: { force: !!force } }),
  updateCountry:    (id: PathId, d: unknown)    => api.patch(`/user-costs/countries/${id}`, d),
  deleteCountry:    (id: PathId)       => api.delete(`/user-costs/countries/${id}`),
  // User profiles
  listProfiles:     (uid: PathId)      => api.get(`/user-costs/users/${uid}/profiles`),
  createProfile:    (uid: PathId, d: unknown)   => api.post(`/user-costs/users/${uid}/profiles`, d),
  // Bulk summary
  summary:          (on: string)       => api.get('/user-costs/summary', { params: { on } }),
}

// ── BPMN Processes ────────────────────────────────────────────────────────────
export const bpmnProcessesApi = {
  list:        (params?: QueryParams)        => api.get('/bpmn-processes', { params }),
  get:         (id: PathId)            => api.get(`/bpmn-processes/${id}`),
  create:      (data: unknown)          => api.post('/bpmn-processes', data),
  saveVersion: (id: PathId, xml: string, n: string)    => api.post(`/bpmn-processes/${id}/versions`, { bpmn_xml: xml, notes: n }),
  start:       (id: PathId, variables: Record<string, unknown> = {}) => api.post(`/bpmn-processes/${id}/instances`, { variables }),
}

// Auditoría 2026-11: motor BPMN (instancias y bandeja de pasos humanos).
export const bpmnInstancesApi = {
  list:     (params?: QueryParams)  => api.get('/bpmn-instances', { params }),
  inbox:    ()              => api.get('/bpmn-instances/inbox'),
  get:      (id: PathId)       => api.get(`/bpmn-instances/${id}`),
  complete: (id: PathId, stepId: PathId, variables: Record<string, unknown> = {}) => api.post(`/bpmn-instances/${id}/steps/${stepId}/complete`, { variables }),
  cancel:   (id: PathId)       => api.post(`/bpmn-instances/${id}/cancel`),
}

// ── Nexus AI Agent ────────────────────────────────────────────────────────────
export const nexusAgentApi = {
  history:              () => api.get('/ai/agent/history'),
  run:                  (instruction: string, autoApprove: boolean = false) => api.post('/ai/agent', { instruction, auto_approve: autoApprove }),
  status:               (id: string) => api.get(`/ai/agent/${id}/status`),
  detail:               (id: string) => api.get(`/ai/agent/${id}`),
  chat:                 (data: unknown) => api.post('/ai/chat', data),
  texto:                (mensaje: string) => api.post('/ai/texto', { mensaje }),
  listConversations:    () => api.get('/ai/conversations'),
  getConversation:      (id: PathId) => api.get(`/ai/conversations/${id}`),
  deleteConversations:  () => api.delete('/ai/conversations'),
  feedback: (messageId: string, data: { helpful: boolean; comment?: string }) => api.post(`/ai/messages/${messageId}/feedback`, data),
}

// ── Global Search ─────────────────────────────────────────────────────────────
export const searchApi = {
  search: (params?: QueryParams) => api.get('/global-search', { params }),
}

// ── Auto-Resolution ───────────────────────────────────────────────────────────
export const autoResolutionApi = {
  getConfig:    ()          => api.get('/sd/auto-resolution/config'),
  getStats:     ()          => api.get('/sd/auto-resolution/stats'),
  patchConfig:  (data: unknown)      => api.patch('/sd/auto-resolution/config', data),
  runJob:       (params?: QueryParams)    => api.post('/sd/auto-resolution/run-job', null, { params }),
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
  updatePolicy:   (topicType: PathId, data: unknown)       => api.put(`/portal/conversations/team/policies/${topicType}`, data),
  reviewMessage:  (convId: PathId, msgId: PathId, data: unknown)   => api.post(`/portal/conversations/team/${convId}/messages/${msgId}/review`, data),
}

/** Normalise a Pydantic v2 / FastAPI error detail to a plain string.
 *  detail can be an array of {type,loc,msg,input,url} objects or a plain string. */
export function apiErrorMsg(e: unknown, fallback = 'Error'): string {
  const err = e as { response?: { data?: { detail?: unknown } }; message?: string } | null | undefined
  const raw = err?.response?.data?.detail
  if (Array.isArray(raw)) return raw.map((d: { msg?: string }) => d.msg).join(', ')
  return (raw as string) || err?.message || fallback
}
