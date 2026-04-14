/**
 * NexusPM JavaScript / TypeScript SDK
 * ====================================
 * ES6 client for the NexusPM REST API.
 *
 * @example
 * import { NexusPMClient } from './nexuspm_sdk.js'
 *
 * const client = new NexusPMClient({ baseUrl: 'https://nexuspm.example.com', token: 'jwt-token' })
 *
 * const projects = await client.projects.list()
 * const task     = await client.tasks.create({ projectId: 'proj-1', title: 'New task' })
 * const predict  = await client.ai.overrunPrediction('proj-1')
 */

// ── Errors ────────────────────────────────────────────────────────────────────

export class NexusPMError extends Error {
  constructor(message, statusCode = 0, response = null) {
    super(message)
    this.name = 'NexusPMError'
    this.statusCode = statusCode
    this.response = response
  }
}

export class AuthError extends NexusPMError {
  constructor(message, statusCode, response) {
    super(message, statusCode, response)
    this.name = 'AuthError'
  }
}

export class NotFoundError extends NexusPMError {
  constructor(message, statusCode, response) {
    super(message, statusCode, response)
    this.name = 'NotFoundError'
  }
}

// ── Base resource ─────────────────────────────────────────────────────────────

class BaseResource {
  constructor(client) {
    this._client = client
  }

  _get(path, params) {
    return this._client._request('GET', path, { params })
  }

  _post(path, body) {
    return this._client._request('POST', path, { body })
  }

  _patch(path, body) {
    return this._client._request('PATCH', path, { body })
  }

  _delete(path) {
    return this._client._request('DELETE', path)
  }
}

// ── Resource namespaces ───────────────────────────────────────────────────────

class ProjectsResource extends BaseResource {
  /** List all accessible projects. @param {{status?: string, search?: string}} opts */
  list(opts = {}) {
    return this._get('/projects', opts)
  }
  /** Get a single project. */
  get(projectId) {
    return this._get(`/projects/${projectId}`)
  }
  /** Create a project. */
  create(data) {
    return this._post('/projects', data)
  }
  /** Update project fields. */
  update(projectId, data) {
    return this._patch(`/projects/${projectId}`, data)
  }
  /** Delete a project. */
  delete(projectId) {
    return this._delete(`/projects/${projectId}`)
  }
}

class TasksResource extends BaseResource {
  /**
   * List tasks.
   * @param {{projectId?: string, assigneeId?: string, status?: string, skip?: number, limit?: number}} opts
   */
  list(opts = {}) {
    const params = {}
    if (opts.projectId)  params.project_id  = opts.projectId
    if (opts.assigneeId) params.assignee_id = opts.assigneeId
    if (opts.status)     params.status      = opts.status
    if (opts.skip != null) params.skip = opts.skip
    if (opts.limit != null) params.limit = opts.limit
    return this._get('/tasks', params)
  }
  get(taskId) {
    return this._get(`/tasks/${taskId}`)
  }
  /** Create a task. data must include { projectId, title, ...rest } */
  create(data) {
    const { projectId, ...rest } = data
    return this._post('/tasks', { project_id: projectId, ...rest })
  }
  update(taskId, data) {
    return this._patch(`/tasks/${taskId}`, data)
  }
  /** Bulk update task dates. updates = [{id, start_date, due_date}] */
  bulkUpdateDates(updates) {
    return this._patch('/tasks/bulk-dates', { updates })
  }
}

class ImputationsResource extends BaseResource {
  list(opts = {}) {
    const params = {}
    if (opts.projectId) params.project_id = opts.projectId
    if (opts.userId)    params.user_id    = opts.userId
    if (opts.startDate) params.start_date = opts.startDate
    if (opts.endDate)   params.end_date   = opts.endDate
    return this._get('/imputations', params)
  }
  /** Log hours. data = { taskId, userId, hours, date, ...rest } */
  create(data) {
    const { taskId, userId, ...rest } = data
    return this._post('/imputations', { task_id: taskId, user_id: userId, ...rest })
  }
  update(imputationId, data) {
    return this._patch(`/imputations/${imputationId}`, data)
  }
  delete(imputationId) {
    return this._delete(`/imputations/${imputationId}`)
  }
}

class UsersResource extends BaseResource {
  list(opts = {}) {
    return this._get('/users', opts)
  }
  get(userId) {
    return this._get(`/users/${userId}`)
  }
  me() {
    return this._get('/users/me')
  }
}

class ResourcesResource extends BaseResource {
  list() {
    return this._get('/resources')
  }
  get(resourceId) {
    return this._get(`/resources/${resourceId}`)
  }
  capacity(resourceId, startDate, endDate) {
    return this._get(`/resources/${resourceId}/capacity`, { start_date: startDate, end_date: endDate })
  }
  utilizationTrend() {
    return this._get('/resources/utilization-trend')
  }
}

class FinancialsResource extends BaseResource {
  profitability(projectId) {
    return this._get(`/projects/${projectId}/profitability`)
  }
  evm(projectId) {
    return this._get(`/evm/${projectId}`)
  }
  /** GAAP double-entry journal entries (ASC 606 / IFRS 15). */
  revenueJournal(projectId) {
    return this._get(`/revenue/journal/${projectId}`)
  }
  /** Export journal entries as CSV string. */
  async revenueJournalCsv(projectId) {
    const resp = await this._get(`/revenue/journal/${projectId}/export`)
    return resp.csv
  }
  milestoneBilling(projectId) {
    return this._get(`/milestone-billing/${projectId}`)
  }
  invoices(opts = {}) {
    return this._get('/invoices', opts.projectId ? { project_id: opts.projectId } : {})
  }
}

class AIResource extends BaseResource {
  /** AI cost & schedule overrun prediction. */
  overrunPrediction(projectId) {
    return this._post('/ai/overrun-prediction', { project_id: projectId })
  }
  chat(message, context = null) {
    const body = { message }
    if (context) body.context = context
    return this._post('/ai/chat', body)
  }
  summarizeProject(projectId) {
    return this._post('/ai/summarize', { project_id: projectId })
  }
  detectBurnout() {
    return this._get('/ai/burnout-detection')
  }
}

class JiraResource extends BaseResource {
  config() {
    return this._get('/jira/config')
  }
  saveConfig(data) {
    return this._post('/jira/config', data)
  }
  testConnection() {
    return this._get('/jira/test')
  }
  issues(jql) {
    return this._get('/jira/issues', jql ? { jql } : {})
  }
  syncFromJira(projectId) {
    return this._post('/jira/sync', projectId ? { project_id: projectId } : {})
  }
  pushToJira() {
    return this._post('/jira/push')
  }
  linkedTasks() {
    return this._get('/jira/linked')
  }
}

// ── Main client ───────────────────────────────────────────────────────────────

export class NexusPMClient {
  /**
   * @param {object}  opts
   * @param {string}  opts.baseUrl   NexusPM instance URL
   * @param {string}  [opts.token]   JWT access token (falls back to NEXUSPM_TOKEN env var)
   * @param {number}  [opts.timeout] Fetch timeout ms (default: 30000)
   * @param {boolean} [opts.verify]  TLS verification (default: true, Node.js only)
   */
  constructor({ baseUrl, token, timeout = 30_000 } = {}) {
    if (!baseUrl) throw new Error('baseUrl is required')
    this._baseUrl = baseUrl.replace(/\/$/, '') + '/api/v1'
    this._token   = token ?? (typeof process !== 'undefined' ? process.env.NEXUSPM_TOKEN : '') ?? ''
    this._timeout = timeout

    // Resource namespaces
    this.projects    = new ProjectsResource(this)
    this.tasks       = new TasksResource(this)
    this.imputations = new ImputationsResource(this)
    this.users       = new UsersResource(this)
    this.resources   = new ResourcesResource(this)
    this.financials  = new FinancialsResource(this)
    this.ai          = new AIResource(this)
    this.jira        = new JiraResource(this)
  }

  /** Authenticate and store JWT token. Returns the token string. */
  async login(email, password) {
    const resp = await fetch(`${this._baseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      signal: AbortSignal.timeout(this._timeout),
    })
    await this._raiseForStatus(resp)
    const data = await resp.json()
    this._token = data.access_token
    return this._token
  }

  async _request(method, path, { params, body } = {}) {
    let url = `${this._baseUrl}/${path.replace(/^\//, '')}`
    if (params && Object.keys(params).length) {
      const qs = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v != null))
      )
      url += `?${qs}`
    }

    const headers = { 'Content-Type': 'application/json' }
    if (this._token) headers['Authorization'] = `Bearer ${this._token}`

    const init = {
      method,
      headers,
      signal: AbortSignal.timeout(this._timeout),
    }
    if (body !== undefined) {
      init.body = JSON.stringify(body)
    }

    const response = await fetch(url, init)
    await this._raiseForStatus(response)
    if (response.status === 204) return {}
    return response.json()
  }

  async _raiseForStatus(response) {
    if (response.ok) return
    let detail
    try {
      const json = await response.clone().json()
      detail = json.detail ?? response.statusText
    } catch {
      detail = response.statusText
    }
    const msg = `HTTP ${response.status}: ${detail}`
    if (response.status === 401 || response.status === 403) throw new AuthError(msg, response.status, response)
    if (response.status === 404) throw new NotFoundError(msg, response.status, response)
    throw new NexusPMError(msg, response.status, response)
  }
}

export default NexusPMClient
