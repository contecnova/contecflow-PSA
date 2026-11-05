/**
 * services/api/settings.ts — Audit #C10 typed slice.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'

export interface GeneralSettings {
  organization_name?: string
  default_currency?: string
  default_timezone?: string
  default_language?: string
  working_hours_per_day?: number
  weekly_capacity_hours?: number
  vacation_days_per_year?: number
  default_tax_rate?: number
  [k: string]: unknown
}

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

export interface LogLevelResponse {
  level: LogLevel
}

export interface RuntimeFlagsResponse {
  [key: string]: { value: string; updated_at?: string; updated_by?: string }
}

export type IntegrationProvider =
  | 'jira'
  | 'github'
  | 'gitlab'
  | 'salesforce'
  | 'stripe'
  | 'docusign'
  | 'adobe_sign'
  | 'm365'
  | 'slack'
  | 'twilio'
  | 'aws_s3'
  | 'aws_kms'

export interface IntegrationStatus {
  provider: IntegrationProvider
  configured: boolean
  keys: string[]
}

export interface IntegrationProviderConfig {
  provider: IntegrationProvider
  values: Record<string, string>
}

export interface IntegrationTestResult {
  ok: boolean
  detail?: string
  status_code?: number
}

export interface AuditLogParams {
  module?: string
  actor?: string
  days?: number
  page?: number
  page_size?: number
}

export interface AuditLogEntry {
  id: string
  action: string
  module: string
  actor_id?: string
  actor_name?: string
  detail?: string
  at: string
}

export const settingsApi = {
  general: (): Promise<AxiosResponse<GeneralSettings>> =>
    api.get('/settings/general'),

  logLevel: (): Promise<AxiosResponse<LogLevelResponse>> =>
    api.get('/settings/log-level'),

  setLogLevel: (data: { level: LogLevel }): Promise<AxiosResponse<LogLevelResponse>> =>
    api.post('/settings/log-level', data),

  runtimeGroup: (group: string): Promise<AxiosResponse<RuntimeFlagsResponse>> =>
    api.get(`/settings/runtime/${group}`),

  setRuntime: (group: string, key: string, value: string | number | boolean | null): Promise<AxiosResponse<RuntimeFlagsResponse>> =>
    api.put(`/settings/runtime/${group}/${key}`, { value: String(value) }),

  /** Qué falta por configurar en la empresa, medido (revisión 2026-11). */
  setupChecklist: (): Promise<AxiosResponse<unknown>> => api.get('/settings/setup-checklist'),
  // Revisión 2026-11: marca de la empresa (la usan los PDF).
  branding: (orgId: string): Promise<AxiosResponse<unknown>> => api.get(`/orgs/${orgId}/branding`),
  saveBranding: (orgId: string, data: Record<string, string>): Promise<AxiosResponse<unknown>> => api.put(`/orgs/${orgId}/branding`, data),
  resetBranding: (orgId: string): Promise<AxiosResponse<unknown>> => api.delete(`/orgs/${orgId}/branding`),

  /** ¿Está armado el aislamiento entre empresas en la base (RLS)? */
  dbIsolation: (): Promise<AxiosResponse<{ armed: boolean; role?: string; tables_with_rls?: number; tables_expected?: number; reason?: string | null }>> =>
    api.get('/settings/db-isolation'),

  /** Traducciones del back-office de la empresa: `{idioma: {módulo: {clave: texto}}}`. */
  appTranslations: (): Promise<AxiosResponse<Record<string, Record<string, Record<string, string>>>>> =>
    api.get('/settings/app-translations'),

  /** Fusiona por clave; un texto vacío quita la personalización. Devuelve todas. */
  saveAppTranslations: (translations: Record<string, unknown>): Promise<AxiosResponse<Record<string, Record<string, Record<string, string>>>>> =>
    api.put('/settings/app-translations', { translations }),

  integrations: (): Promise<AxiosResponse<IntegrationStatus[]>> =>
    api.get('/settings/integrations'),

  integrationProvider: (provider: IntegrationProvider): Promise<AxiosResponse<IntegrationProviderConfig>> =>
    api.get(`/settings/integrations/${provider}`),

  setIntegration: (
    provider: IntegrationProvider,
    key: string,
    value: string | number | boolean | null | undefined,
  ): Promise<AxiosResponse<IntegrationProviderConfig>> =>
    api.put(`/settings/integrations/${provider}/${key}`, { value: value == null ? '' : String(value) }),

  testIntegration: (provider: IntegrationProvider): Promise<AxiosResponse<IntegrationTestResult>> =>
    api.post(`/settings/integrations/${provider}/test`),

  auditLog: (params: AuditLogParams = {}): Promise<AxiosResponse<AuditLogEntry[]>> =>
    api.get('/settings/audit-log', { params }),
} as const
