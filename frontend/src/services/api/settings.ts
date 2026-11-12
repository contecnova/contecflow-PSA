/**
 * services/api/settings.ts — Audit #C10 typed slice.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'

/** `SettingOut` (app/schemas/settings.py): `GET /settings/general` devuelve una lista. */
export interface GeneralSetting {
  key: string
  value: string | null
  description: string | null
}

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

/** `GET /settings/log-level` (get_log_level en app/api/v1/endpoints/settings.py). */
export interface LogLevelResponse {
  root: string
  contecflow: string
  uvicorn: string
  uvicorn_error: string
  uvicorn_access: string
  valid_levels: string[]
}

/** `LogLevelPayload` (app/schemas/settings.py). */
export interface LogLevelPayload {
  level: LogLevel
  logger?: string | null
}

/** `POST /settings/log-level` (set_log_level). */
export interface LogLevelChange {
  ok: boolean
  logger: string
  level: string
  affected: string[]
}

/** Un ajuste de `get_runtime_group` (app/services/settings_service/runtime.py). */
export interface RuntimeSetting {
  key: string
  type: 'int' | 'float' | 'bool' | 'str'
  label: string
  value: string | number | boolean | null
  plataforma: boolean
}

/** `GET /settings/runtime/{group}`. */
export interface RuntimeFlagsResponse {
  group: string
  items: RuntimeSetting[]
}

/** Claves de `PROVIDER_REGISTRY` (app/services/integration_credentials_service.py).
 *  Auditoría 2026-11 (#25): la lista anterior (jira, github, gitlab, salesforce, m365,
 *  aws_kms...) no coincidía con el registro del servidor. */
export type IntegrationProvider =
  | 'smtp'
  | 'sd_mailbox'
  | 'contecmind'
  | 'contecintelligence'
  | 'monitoring'
  | 'aws_s3'
  | 'ms_graph'
  | 'slack'
  | 'twilio'
  | 'stripe'
  | 'docusign'
  | 'adobe_sign'
  | 'ai_providers'
  | 'webhooks'
  | 'open_exchange_rates'

/** Elemento de `list_providers` (app/services/integration_credentials_service.py). */
export interface IntegrationStatus {
  provider: IntegrationProvider
  label: string
}

/** Un campo de `describe_provider` (app/services/integration_credentials_service.py). */
export interface IntegrationField {
  key: string
  type: string
  label: string
  is_secret: boolean
  value: string | number | boolean | null
  configured: boolean
  source: 'db' | 'env' | 'unset'
}

/** `GET /settings/integrations/{provider}` (describe_provider). */
export interface IntegrationProviderConfig {
  provider: IntegrationProvider
  label: string
  items: IntegrationField[]
}

/** `PUT /settings/integrations/{provider}/{key}` (set_credential). */
export interface IntegrationFieldUpdate {
  provider: IntegrationProvider
  key: string
  configured: boolean
  source: 'db' | 'unset'
  is_secret?: boolean
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
  general: (): Promise<AxiosResponse<GeneralSetting[]>> =>
    api.get('/settings/general'),

  logLevel: (): Promise<AxiosResponse<LogLevelResponse>> =>
    api.get('/settings/log-level'),

  setLogLevel: (data: LogLevelPayload): Promise<AxiosResponse<LogLevelChange>> =>
    api.post('/settings/log-level', data),

  runtimeGroup: (group: string): Promise<AxiosResponse<RuntimeFlagsResponse>> =>
    api.get(`/settings/runtime/${group}`),

  // Devuelve la fila `AppSetting` guardada (set_runtime_value); nadie la lee.
  setRuntime: (group: string, key: string, value: string | number | boolean | null): Promise<AxiosResponse<unknown>> =>
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

  /** Fusiona por clave; un texto vacío quita la personalización. Devuelve todas. */
  saveAppTranslations: (translations: Record<string, unknown>): Promise<AxiosResponse<Record<string, Record<string, Record<string, string>>>>> =>
    api.put('/settings/app-translations', { translations }),

  integrations: (): Promise<AxiosResponse<{ providers: IntegrationStatus[] }>> =>
    api.get('/settings/integrations'),

  integrationProvider: (provider: IntegrationProvider): Promise<AxiosResponse<IntegrationProviderConfig>> =>
    api.get(`/settings/integrations/${provider}`),

  setIntegration: (
    provider: IntegrationProvider,
    key: string,
    value: string | number | boolean | null | undefined,
  ): Promise<AxiosResponse<IntegrationFieldUpdate>> =>
    api.put(`/settings/integrations/${provider}/${key}`, { value: value == null ? '' : String(value) }),

  testIntegration: (provider: IntegrationProvider): Promise<AxiosResponse<IntegrationTestResult>> =>
    api.post(`/settings/integrations/${provider}/test`),
} as const
