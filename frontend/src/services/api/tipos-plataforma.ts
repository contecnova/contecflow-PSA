/**
 * Respuestas de la plataforma: organizaciones, Jira (`/jira/**`), automatizaciones,
 * Microsoft 365, MFA, permisos de proyecto, importacion masiva, webhooks salientes,
 * gobierno de modulos de IA y aplicaciones OAuth del portal de desarrolladores.
 * Comprobadas contra app/api/v1/endpoints/{organizations,jira,automations,m365,
 * custom_fields,billing_reports,enterprise,governance,developer_portal}.py,
 * app/api/v1/routers/auth_mfa.py y sus servicios.
 *
 * Son `type` y no `interface` (como en tipos-sd.ts): un alias de objeto se puede
 * asignar a los tipos con indice que aun usan algunos componentes.
 *
 * Las listas llegan ya desenvueltas por el interceptor de _core.ts y los
 * `APIResponse {data, meta}` tambien: `res.data` es el payload.
 */

/** `meta` de un APIListResponse (app/core/responses.ResponseMeta); el interceptor la deja en `res.meta`. */
export type MetaDeLista = {
  total: number | null
  page: number | null
  page_size: number | null
  has_more: boolean | null
}

/** Respuesta de las escrituras que solo confirman, con mensaje. */
export type OkConMensaje = { ok: boolean; message: string }

/** 202 de `respuesta_en_cola` (app/core/segundo_plano.py): el trabajo va al worker. */
export type TrabajoEnCola = { ok: boolean; status: 'queued'; dry_run?: boolean }

// ── Organizaciones (`/organizations`, superadmin) ──────────────────────────

/** organizations_service.serialize_organization (lista, baja y deshacer la baja). */
export type Organizacion = {
  id: string
  name: string
  slug: string
  plan: string
  is_active: boolean
  max_users: number
  max_projects: number
  admin_email: string | null
  domain: string | null
  suspension_reason: string | null
  deletion_purge_after: string | null
  /** `YYYY-MM-DD`. */
  created_at: string | null
  user_count: number
  project_count: number
}

/** Usuario de la organizacion en el detalle. */
export type UsuarioDeOrganizacion = { id: string; full_name: string; email: string; role: string }

/** organizations_service.get_organization: sin recuentos ni `created_at`; con usuarios y ajustes. */
export type DetalleDeOrganizacion = Omit<Organizacion, 'created_at' | 'user_count' | 'project_count'> & {
  timezone: string | null
  locale: string | null
  primary_color: string | null
  require_mfa: boolean
  users: UsuarioDeOrganizacion[]
}

/** create_organization: la contrasena inicial solo llega si se creo el primer admin. */
export type OrganizacionCreada = {
  ok: boolean
  id: string
  slug: string
  admin_email: string | null
  initial_password: string | null
}

/** assign_user_to_org / remove_user_from_org. */
export type CambioDeMiembro = { ok: boolean; user: string; org: string }

/**
 * POST /organizations/{id}/impersonate. El endpoint responde `JSONResponse({"data": ...})`
 * sin `meta`, asi que el interceptor NO lo desenvuelve: `res.data.data`.
 */
export type EntradaComo = { data: { ok: boolean; user: string } }

// ── Jira (`/jira`, conexion de tareas de la organizacion) ──────────────────

/** GET /jira/config: credenciales sin el token. */
export type ConfigJira = {
  jira_url: string | null
  jira_email: string | null
  jira_project_key: string | null
  configured: boolean
  /** `••••` + los 4 ultimos caracteres; solo si hay token guardado. */
  jira_api_token_hint?: string
}

/** GET /jira/test (jira_service.probar_conexion); si falla, error HTTP. */
export type PruebaDeConexionJira = {
  jira_url: string | null
  ok: boolean
  account_id: string | null
  display_name: string | null
  email: string | null
}

/** Issue de GET /jira/issues. */
export type IssueDeJira = {
  key: string
  id: string
  summary: string | null
  status: string | null
  priority: string | null
  assignee: string | null
  due_date: string | null
  issue_type: string | null
  labels: string[]
  updated: string | null
}

/** GET /jira/issues: no es una lista, es `{total, issues}`. */
export type IssuesDeJira = { total: number; issues: IssueDeJira[] }

/** GET /jira/linked (paginado). */
export type TareaVinculadaAJira = {
  id: string
  title: string
  status: string
  jira_issue_key: string | null
  jira_issue_url: string | null
  jira_synced_at: string | null
}

/** POST /jira/sync (jira_service.sync_jira_issues + recuento). */
export type SincronizacionDesdeJira = {
  ok: boolean
  dry_run: boolean
  issues_fetched: number
  created: number
  updated: number
  skipped: number
}

/** jira_service.empujar_tareas_a_jira. */
export type EnvioAJira = {
  ok: boolean
  dry_run: boolean
  tasks_evaluated: number
  created: number
  skipped: number
  errors: number
  error_details: Array<{ task_id: string; error: string }>
}

/** POST /jira/webhook-secret: el secreto se ve una sola vez. */
export type SecretoDeWebhookJira = { secret: string; header: string; webhook_paths: string[] }

// ── Automatizaciones (`/automations`) ──────────────────────────────────────

/**
 * Condicion de una regla: hoja `{field, operator, value}` o grupo `{match, conditions}`
 * (catalogo._validar_condicion).
 */
export type CondicionDeRegla = {
  field?: string
  operator?: string
  value?: string
  match?: string
  conditions?: CondicionDeRegla[]
}

/** Accion de una regla: `params` segun el catalogo de acciones. */
export type AccionDeRegla = { type: string; params?: Record<string, string> }

/** automations_service.catalogo.serialize_rule. */
export type ReglaDeAutomatizacion = {
  id: string
  name: string
  description: string | null
  project_id: string | null
  project_name: string | null
  is_active: boolean
  is_global: boolean
  trigger_type: string
  trigger_conditions: CondicionDeRegla | null
  schedule_cron: string | null
  next_run_at: string | null
  actions: AccionDeRegla[]
  run_count: number
  last_run_at: string | null
  last_error: string | null
  created_at: string | null
}

/** reglas.get_automation_templates. */
export type PlantillaDeRegla = {
  id: string
  name: string
  description?: string
  trigger_type: string
  trigger_conditions: CondicionDeRegla | null
  actions: AccionDeRegla[]
}

/** Resultado de una accion ejecutada (acciones.py); los campos extra dependen de la accion. */
export type AccionEjecutada = { action: string; ok?: boolean; error?: string }

/** reglas.get_executions_db. */
export type EjecucionDeRegla = {
  id: string
  trigger_context: Record<string, unknown> | null
  actions_taken: AccionEjecutada[] | null
  success: boolean
  error: string | null
  executed_at: string
}

/** reglas.simular (POST /automations/{id}/test): no ejecuta nada. */
export type SimulacionDeRegla = {
  simulated: boolean
  enabled: boolean
  trigger_type: string
  scan: boolean
  results: Array<{ action: string; ok: boolean; would?: string; error: string | null }>
}

/** Parametro de una accion del catalogo (catalogo._p). */
export type ParametroDeAccion = { key: string; type: string; options: string[] | null; required: boolean }

/** catalogo.catalogo (GET /automations/catalog). */
export type CatalogoDeAutomatizaciones = {
  triggers: Array<{ type: string; category: string; fields: string[]; scan?: boolean; schedule?: boolean }>
  actions: Array<{ type: string; category: string; params: ParametroDeAccion[] }>
  operators: string[]
}

// ── Microsoft 365 (`/m365`) ────────────────────────────────────────────────

/** GET /m365/status. Los `*_enabled` son ajustes en vivo: `null` si no estan fijados. */
export type EstadoM365 = {
  graph_configured: boolean
  calendar_sync_enabled: boolean | null
  teams_notifications_enabled: boolean | null
  teams_webhook_configured: boolean
  required_env_vars: Record<string, boolean>
}

/** Evento de Graph `calendarView` con el `$select` de sync_calendar_events. */
export type EventoDeCalendarioM365 = {
  id: string
  subject?: string
  start?: { dateTime?: string; timeZone?: string }
  end?: { dateTime?: string; timeZone?: string }
  location?: { displayName?: string }
  webLink?: string
  attendees?: Array<{ emailAddress?: { address?: string; name?: string }; type?: string }>
}

/** POST /m365/calendar/sync. */
export type CalendarioM365Leido = { pulled: number; events: EventoDeCalendarioM365[] }

/** POST /m365/calendar/sync-milestones. */
export type HitosEnCalendarioM365 = {
  created: number
  errors: Array<{ milestone_id: string; error: string }>
  details: Array<{ milestone_id: string; event_id: string | null }>
}

/** POST /m365/teams/notify: `status` es el codigo HTTP de Teams. */
export type AvisoDeTeams = { ok: boolean; status: number }

// ── MFA (`/auth/mfa`) ──────────────────────────────────────────────────────

/** auth_service.mfa.estado_de_mfa. */
export type EstadoMfa = {
  enabled: boolean
  passkeys: number
  second_factor: boolean
  reauth_required: boolean
  verified_at: string | null
  backup_codes_remaining: number
}

/** POST /auth/mfa/setup. */
export type AltaMfa = {
  secret: string
  provisioning_uri: string
  /** Imagen PNG en `data:` URI. */
  qr_url: string
  issuer: string
  email: string
}

/** POST /auth/mfa/verify-setup: los codigos de respaldo se ven una sola vez. */
export type MfaActivado = { ok: boolean; message: string; backup_codes: string[]; warning: string }

// ── Permisos de proyecto (`/permissions/{project_id}`) ─────────────────────

/** custom_fields_service.serialize_perm. */
export type PermisoDeProyecto = {
  id: string
  project_id: string
  user_id: string
  level: 'none' | 'viewer' | 'member' | 'manager' | 'owner'
  can_see_financials: boolean
  can_see_rates: boolean
  can_export: boolean
  granted_at: string | null
  user: {
    id: string
    full_name: string
    role: string
    job_title: string | null
    department: string | null
  } | null
}

// ── Importacion masiva (`/billing-reports/import`) ─────────────────────────

/** schemas.billing_reports.ImportTemplateOut. */
export type PlantillaDeImportacion = {
  entity_type: string
  columns: string[]
  example: string[][]
  instructions: string
}

/** ImportValidationErrorOut. */
export type ErrorDeFilaImportada = { row: number; field?: string; error: string }

/** ImportValidateOut. */
export type ValidacionDeImportacion = {
  valid: boolean
  total_rows: number
  errors: ErrorDeFilaImportada[]
  warnings: string[]
  preview: Array<Record<string, unknown>>
}

/** ImportExecuteOut (`errors`: las 10 primeras). */
export type ResultadoDeImportacion = {
  job_id: string
  status: string
  total: number
  succeeded: number
  failed: number
  errors: ErrorDeFilaImportada[]
}

/** ImportJobHistoryOut. */
export type TrabajoDeImportacion = {
  id: string
  entity_type: string
  filename: string | null
  status: string
  total_rows: number
  succeeded: number
  failed_rows: number
  started_at: string | null
  completed_at: string | null
}

// ── Webhooks salientes (`/enterprise/webhooks`) ────────────────────────────

/** enterprise_service.webhooks.serialize_webhook. */
export type WebhookSaliente = {
  id: string
  name: string
  url: string
  has_secret: boolean
  events: string[]
  is_active: boolean
  project_id: string | null
  project_name: string | null
  total_deliveries: number
  failed_deliveries: number
  last_triggered_at: string | null
  created_at: string | null
}

/** GET /enterprise/webhooks/events. */
export type EventoDeWebhook = { value: string; label: string }

/** list_all_webhook_deliveries (paginado: total en `res.meta`). */
export type EntregaDeWebhook = {
  id: string
  webhook_id: string
  webhook_name: string
  webhook_url: string
  event: string
  status_code: number | null
  success: boolean
  error: string | null
  duration_ms: number | null
  attempt: number | null
  payload: string | null
  /** Primeros 500 caracteres. */
  response: string | null
  created_at: string | null
}

// ── Gobierno de modulos de IA (`/governance`) ──────────────────────────────

/** GET /governance/config. */
export type ModuloDeIaGobernado = { module: string; is_enabled: boolean }

/** PATCH /governance/config/{module}. */
export type ModuloDeIaActualizado = { ok: boolean; module: string; is_enabled: boolean }

/** governance_service.get_ai_usage_stats. */
export type UsoDeModulosDeIa = {
  total_calls: number
  total_tokens: number
  by_module: Record<string, { calls: number; tokens: number }>
}

/** governance_service.list_ai_governance_logs. */
export type LlamadaDeModuloDeIa = {
  id: string
  module: string
  action_type: string | null
  status: string | null
  tokens_used: number | null
  created_at: string | null
  user_id: string | null
}

// ── Portal de desarrolladores (`/developer/apps`) ──────────────────────────

/** developer_portal_service.serialize_app; `client_secret` solo al crear. */
export type AplicacionOAuth = {
  id: string
  name: string
  description: string | null
  homepage_url: string | null
  client_id: string
  redirect_uris: string[]
  scopes: string[]
  is_active: boolean
  is_first_party: boolean
  owner_id: string
  created_at: string | null
  client_secret?: string
}

/** POST /developer/apps/{id}/rotate-secret: el secreto nuevo se ve una sola vez. */
export type SecretoRotado = { client_id: string; client_secret: string }
