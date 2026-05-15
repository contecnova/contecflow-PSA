/**
 * Integrations — Jira, M365, OAuth, hub tests, API keys, webhooks, currency,
 * email templates, import (CSV/Excel) jobs, integrations export.
 */
import { api, type AxiosRequestConfig } from './client'
import type { Id, JsonBody, Params, Response } from './types'

export const integrationsApi = {
  exportImputations: (data: JsonBody): Promise<Response<Blob>> =>
    api.post('/integrations/export/imputations', data, { responseType: 'blob' }),
  exportProjects:    (data: JsonBody): Promise<Response<Blob>> =>
    api.post('/integrations/export/projects', data, { responseType: 'blob' }),
  jiraSync:          (projectId: Id): Promise<Response<unknown>> => api.post(`/integrations/jira/sync/${projectId}`),
  jiraStatus:        (projectId: Id): Promise<Response<unknown>> => api.get(`/integrations/jira/status/${projectId}`),
}

export const jiraApi = {
  config:     (): Promise<Response<unknown>> => api.get('/jira/config'),
  saveConfig: (data: JsonBody): Promise<Response<unknown>> => api.post('/jira/config', data),
  issues:     (): Promise<Response<unknown>> => api.get('/jira/issues'),
  linked:     (): Promise<Response<unknown>> => api.get('/jira/linked'),
  test:       (): Promise<Response<unknown>> => api.get('/jira/test'),
  sync:       (data: JsonBody): Promise<Response<unknown>> => api.post('/jira/sync', data),
  push:       (): Promise<Response<unknown>> => api.post('/jira/push'),
}

export const m365Api = {
  status:         (): Promise<Response<unknown>> => api.get('/m365/status'),
  syncCalendar:   (upn: string, days?: number): Promise<Response<unknown>> =>
    api.post('/m365/calendar/sync', null, { params: { user_upn: upn, days } }),
  syncMilestones: (data: JsonBody): Promise<Response<unknown>> => api.post('/m365/calendar/sync-milestones', data),
  teamsNotify:    (data: JsonBody): Promise<Response<unknown>> => api.post('/m365/teams/notify', data),
}

export const oauthIntegrationsApi = {
  list:   (): Promise<Response<unknown>> => api.get('/oauth-integrations'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/oauth-integrations', data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/oauth-integrations/${id}`),
  sync:   (id: Id, data: JsonBody): Promise<Response<unknown>> => api.post(`/oauth-integrations/${id}/sync`, data),
}

export const integrationsHubApi = {
  testSlack: (data: JsonBody): Promise<Response<unknown>> => api.post('/integrations-hub/slack/test', data),
  testTeams: (data: JsonBody): Promise<Response<unknown>> => api.post('/integrations-hub/teams/test', data),
  testJira:  (data: JsonBody): Promise<Response<unknown>> => api.post('/integrations-hub/jira/test', data),
}

export const apiKeysApi = {
  list:   (): Promise<Response<unknown>> => api.get('/api-keys'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/api-keys', data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/api-keys/${id}`),
}

export const webhooksApi = {
  list:   (): Promise<Response<unknown>> => api.get('/webhooks'),
  create: (data: JsonBody): Promise<Response<unknown>> => api.post('/webhooks', data),
  delete: (id: Id): Promise<Response<unknown>> => api.delete(`/webhooks/${id}`),
  logs:   (id: Id): Promise<Response<unknown>> => api.get(`/webhooks/${id}/logs`),
}

export const emailApi = {
  catalog:        (): Promise<Response<unknown>> => api.get('/email/templates'),
  logs:           (): Promise<Response<unknown>> => api.get('/email/logs'),
  send:           (data: JsonBody): Promise<Response<unknown>> => api.post('/email/send', data),
  createTemplate: (data: JsonBody): Promise<Response<unknown>> => api.post('/email/templates', data),
}

// Currency Rates — tries multiple canonical paths and falls back on 404.
const getWithFallback = async (paths: string[], config?: AxiosRequestConfig): Promise<Response<unknown>> => {
  let lastErr: unknown
  for (const path of paths) {
    try {
      return await api.get(path, config)
    } catch (err) {
      lastErr = err
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status !== 404) throw err
    }
  }
  throw lastErr
}

const postWithFallback = async (paths: string[], data: unknown, config?: AxiosRequestConfig): Promise<Response<unknown>> => {
  let lastErr: unknown
  for (const path of paths) {
    try {
      return await api.post(path, data, config)
    } catch (err) {
      lastErr = err
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status !== 404) throw err
    }
  }
  throw lastErr
}

export const currencyApi = {
  rates:   (params?: Params): Promise<Response<unknown>> =>
    getWithFallback(['/currency/rates', '/currency-rates/currency/rates', '/bookings/currency/rates'], { params }),
  upsert:  (data: JsonBody): Promise<Response<unknown>> =>
    postWithFallback(['/currency/rates', '/currency-rates/currency/rates', '/bookings/currency/rates'], data),
  convert: (params?: Params): Promise<Response<unknown>> =>
    getWithFallback(['/currency/convert', '/currency-rates/currency/convert'], { params }),
  report:  (params?: Params): Promise<Response<unknown>> =>
    getWithFallback(['/currency/report', '/currency-rates/currency/report'], { params }),
}

export const importApi = {
  template: (entityType: string): Promise<Response<unknown>> => api.get(`/billing-reports/import/template/${entityType}`),
  jobs:     (): Promise<Response<unknown>> => api.get('/billing-reports/import/jobs'),
  validate: (entityType: string, fd: FormData): Promise<Response<unknown>> =>
    api.post('/billing-reports/import/validate', fd, {
      params: { entity_type: entityType },
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  execute:  (entityType: string, fd: FormData): Promise<Response<unknown>> =>
    api.post('/billing-reports/import/execute', fd, {
      params: { entity_type: entityType },
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}
