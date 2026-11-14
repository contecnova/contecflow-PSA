/**
 * Tipos de respuesta de los endpoints mas usados del cliente (_core.ts).
 *
 * Auditoria 2026-11 (#39): _core.ts tenia ~980 llamadas que devolvian
 * AxiosResponse<any>. El backend responde estos recursos con `dict` (no hay
 * esquema de salida en app/schemas: alli solo estan los de entrada, RiskIn,
 * ContractIn, EpicIn, SprintCreate...), asi que los campos de aqui son los que
 * leen las pantallas y los que confirman esos esquemas de entrada; el indice
 * `[extra: string]: unknown` deja leer el resto sin `any`.
 *
 * Las listas llegan ya desenvueltas por el interceptor de _core.ts
 * (APIListResponse `{items, meta}` -> `res.data = items`).
 */

export interface Client {
  id: string
  name?: string
  status?: string
  industry?: string | null
  /** Solo en el detalle (client_service.get_client_detail). */
  projects?: Array<{ id: string; code?: string; name?: string; status?: string }>
  [extra: string]: unknown
}

/** client_service.list_contacts. */
export interface ClientContact {
  id: string
  full_name: string
  email?: string | null
  phone?: string | null
  job_title?: string | null
  role: string
  is_primary?: boolean
  notes?: string | null
  is_active?: boolean
}

/** RiskIn: probability e impact son cualitativos (low/medium/high...). Algunas
 *  vistas calculan con la puntuacion numerica: se aceptan los dos. */
export interface Risk {
  id: string
  title?: string
  description?: string | null
  category?: string | null
  probability?: string | number
  impact?: string | number
  status?: string
  owner_id?: string | null
  cost_impact_min?: number | null
  cost_impact_max?: number | null
  [extra: string]: unknown
}

/** GET /risks/{project_id}: no es una lista, es `{risks, summary}`. */
export interface RiesgosDelProyecto<R = Risk> {
  risks: R[]
  summary: { total: number; open: number; by_level: Record<string, number>; critical_count: number; high_count: number }
}

/** ContractIn / ContractUpdate. */
export interface Contract {
  id: string
  name?: string
  project_id?: string
  client_id?: string
  client_name?: string
  contract_type?: string
  status?: string
  total_amount?: number | null
  hourly_rate?: number | null
  [extra: string]: unknown
}

/** EpicIn / epics_service: la epica tiene `title`, no `name`. */
export interface Epic {
  id: string
  title?: string
  description?: string | null
  color?: string
  status?: string
  priority?: string
  start_date?: string | null
  end_date?: string | null
  [extra: string]: unknown
}

/** SprintCreate / SprintUpdate. */
export interface Sprint {
  id: string
  project_id?: string
  name?: string
  goal?: string | null
  status?: string
  start_date?: string | null
  end_date?: string | null
  [extra: string]: unknown
}

/** cmdb_service.list_sla_calendars (`GET /cmdb/sla-calendars`, lista desenvuelta).
 *  Columnas con valor por defecto (09:00, 18:00, "1,2,3,4,5"): llegan siempre. */
export interface SlaCalendar {
  id: string
  name: string
  timezone: string
  work_start: string
  work_end: string
  /** CSV: 1=lunes ... 7=domingo. */
  work_days: string
  holiday_count?: number
}

/** cmdb_service.create_sla_calendar. */
export interface SlaCalendarCreado { id: string; name: string }

// ── Enterprise (EnterprisePage) ──────────────────────────────────────────────

/** cab_service.webhooks_entrantes.trigger_out (`GET /webhooks`, lista desenvuelta). */
export interface WebhookEntrante {
  id: string
  name: string
  slug: string
  workflow_id: string | null
  is_active: boolean
  fire_count: number
  last_fired_at: string | null
  slug_rotated_at: string | null
  slug_expires_at: string | null
  /** Ruta relativa al origen: `/api/v1/webhooks/fire/{slug}`. */
  endpoint: string
}

/** create_webhook_trigger: el secreto solo se ve aqui. */
export interface WebhookEntranteCreado { ok: boolean; id: string; secret: string; endpoint: string }

/** get_webhook_logs (ultimas 50). */
export interface LlamadaDeWebhook {
  id: string
  status: string
  error: string | null
  received_at: string
  payload_preview: string
}

/** schemas.billing_reports.AutomationWorkflowOut (`GET /automation-workflows`). */
export interface FlujoDeAutomatizacion {
  id: string
  name: string
  description?: string | null
  project_id?: string | null
  project_name?: string | null
  is_global: boolean
  status: string
  trigger_type: string
  run_count: number
  success_count: number
  error_count: number
  last_run_at?: string | null
}

/** cab_service.gdpr.list_gdpr_requests. */
export interface SolicitudRgpd {
  id: string
  request_type: string
  status: string
  subject_email: string | null
  subject_name: string
  deadline: string | null
  completed_at: string | null
  processor: string | null
  created_at: string | null
  notes: string | null
}

/** create_gdpr_request. */
export interface SolicitudRgpdCreada { ok: boolean; id: string; deadline: string }
/** process_gdpr_request: `data` es la exportacion (portabilidad/acceso) o el detalle del borrado. */
export interface SolicitudRgpdProcesada { ok: boolean; status: string; data: Record<string, unknown> | null }

/** cab_service.correo: plantilla del sistema (SYSTEM_EMAIL_TEMPLATES) o propia. */
export interface PlantillaDeCorreo {
  id: string
  name: string
  subject: string
  category: string
  variables: string[]
  is_system: boolean
  created_by?: string | null
}
/** list_email_templates. */
export interface CatalogoDeCorreo { system: PlantillaDeCorreo[]; custom: PlantillaDeCorreo[] }
/** get_email_logs. */
export interface EnvioDeCorreo {
  id: string
  to: string
  subject: string
  status: string
  source: string | null
  sent_at: string | null
  created_at: string | null
}
/** send_email_action. */
export interface CorreoEnviado { ok: boolean; sent: boolean; to: string[]; subject: string }

/** cab_service.integraciones.list_integrations (`config` ya descifrado). */
export interface IntegracionOAuth {
  id: string
  integration_type: string
  name: string | null
  is_active: boolean
  last_sync_at: string | null
  sync_errors: number
  last_error: string | null
  config: Record<string, string>
  has_token: boolean
  created_by: string | null
}
/** create_integration (`jira_config` si se guardo como la conexion Jira de la empresa). */
export interface IntegracionGuardada { ok: boolean; id: string; updated: boolean; jira_config?: boolean }
/** desactivar_integracion / DELETE /integrations-hub/jira/config. */
export interface IntegracionDesactivada { ok: boolean; id?: string; deactivated: boolean }
/** run_integration_sync y POST /integrations-hub/jira/sync. */
export interface SincronizacionDeIntegracion { ok: boolean; synced: number; errors: string[] }
/** POST /integrations-hub/slack|teams/test. */
export interface PruebaDeMensajeria { ok: boolean; message: string }
/** POST /integrations-hub/jira/test. */
export interface PruebaDeJira { ok: boolean; projects: Array<{ key: string; name: string }>; total: number }
/** jira_service.config_del_hub: sin token; `configured: false` y nada mas si no hay conexion. */
export interface ConfigJiraDelHub {
  configured: boolean
  id?: string
  name?: string
  base_url?: string
  email?: string
  project_key?: string
  has_token?: boolean
  is_active?: boolean
  last_sync_at?: string | null
}

/** enterprise_service.auditoria_y_permisos.get_audit_log: fila. */
export interface EventoDeAuditoria {
  id: string
  user_name: string | null
  ip_address: string | null
  action: string
  resource: string | null
  resource_id: string | null
  resource_name: string | null
  old_values: Record<string, unknown> | null
  new_values: Record<string, unknown> | null
  created_at: string
}
/** get_audit_log: pagina (no es APIListResponse: `logs` + total/page/pages). */
export interface PaginaDeAuditoria { total: number; page: number; pages: number; logs: EventoDeAuditoria[] }

/** db.cadena_auditoria.verificar. */
export interface VerificacionDeCadena {
  organization_id: string | null
  ok: boolean
  rows_checked: number
  breaks: Array<{ id: string; seq: number | null; reason: string; expected_seq?: number }>
  breaks_total: number
  head: { seq: number; entry_hash: string | null }
  checked_at: string
  expected_head?: { seq: number; found: boolean }
}

/** enterprise_service.sso.serialize_sso. */
export interface ConfigSso {
  id: string
  provider: string
  name: string | null
  groups_claim: string | null
  is_active: boolean
  is_default: boolean
  saml_entity_id: string | null
  saml_sso_url: string | null
  saml_slo_url: string | null
  has_certificate: boolean
  saml_attribute_email: string | null
  saml_attribute_name: string | null
  saml_attribute_role: string | null
  oidc_client_id: string | null
  has_oidc_secret: boolean
  oidc_discovery_url: string | null
  oidc_scopes: string | null
  role_mapping: Record<string, string>
  organization_id: string | null
  auto_create_users: boolean
  default_role: string | null
  allowed_domains: string | null
  created_at: string | null
}
/** validate_sso_config. */
export interface ValidacionSso { valid: boolean; issues: string[]; provider: string; redirect_uri_hint?: string }

/** bookings: list_api_keys_records. */
export interface ClaveDeApi {
  id: string
  name: string
  key_prefix: string
  scopes: string[]
  is_active: boolean
  rate_limit_per_hour: number
  rate_limit_per_day: number
  requests_today: number
  last_used_at: string | null
  expires_at: string | null
  created_at: string | null
}
/** create_api_key_record: la clave completa solo se ve aqui. */
export interface ClaveDeApiCreada { id: string; name: string; key: string; key_prefix: string; warning: string }
