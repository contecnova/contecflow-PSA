/**
 * Respuestas del service desk y de la CMDB (`/sd/**`), comprobadas contra los
 * serializadores del backend (app/services/service_desk/**, app/services/sla_service.py).
 *
 * Son `type` y no `interface` a proposito: un alias de objeto se puede asignar a
 * los tipos con indice `[k: string]: unknown` que aun usan algunas pantallas y
 * componentes (RawNode del grafo de topologia, por ejemplo).
 *
 * Las listas llegan ya desenvueltas por el interceptor de _core.ts y los
 * `APIResponse {data, meta}` tambien: `res.data` es el payload.
 */

/** Respuesta comun de las escrituras que no devuelven la entidad. */
export type SdOk = { ok: boolean }

// ── Tickets ────────────────────────────────────────────────────────────────

/** sla_service.ticket_out (lista y base del detalle). */
export type SdTicket = {
  id: string
  number: string
  csat_requested_at: string | null
  ticket_type: string
  type_label: string
  type_icon: string
  title: string
  description: string
  status: string
  status_label: string
  status_color: string
  priority: string
  priority_label: string
  priority_color: string
  urgency: string | null
  impact: string | null
  support_level: string | null
  source: string | null
  tags: string | null
  requester_name: string | null
  requester_email: string | null
  requester_type: 'internal' | 'client' | 'phone'
  assigned_to_id: string | null
  assigned_to_name: string | null
  assigned_group_id: string | null
  assigned_group_name: string | null
  project_id: string | null
  project_name: string | null
  client_id: string | null
  client_name: string | null
  ci_id: string | null
  ci_name: string | null
  service_item_id: string | null
  service_item_name: string | null
  problem_id: string | null
  sla_response_due: string | null
  sla_resolution_due: string | null
  /** `paused` mientras el SLA esta en pausa (no hay `sla_paused_at` en la respuesta). */
  sla_response_status: 'ok' | 'at_risk' | 'breached' | 'paused'
  sla_resolution_status: 'ok' | 'at_risk' | 'breached' | 'paused'
  sla_response_breached: boolean
  sla_resolution_breached: boolean
  group_assigned_at: string | null
  ola_due: string | null
  ola_breached: boolean
  uc_contract_id: string | null
  uc_contract_name: string | null
  uc_started_at: string | null
  uc_due: string | null
  uc_breached: boolean
  uc_vendor_responded_at: string | null
  uc_response_due: string | null
  uc_response_breached: boolean
  time_spent_minutes: number | null
  time_to_response_hours: number | null
  time_to_resolution_hours: number | null
  age_hours: number
  resolution: string | null
  resolution_code: string | null
  kb_article_id: string | null
  csat_score: number | null
  csat_comment: string | null
  created_at: string | null
  updated_at: string | null
  first_response_at: string | null
  resolved_at: string | null
  approval_status: string | null
  /** ticket_read_service: la lista y el detalle lo anaden. */
  dynamic_fields?: Record<string, unknown>
}

/** ticket_out(include_comments=True): comentarios. */
export type SdTicketComentario = {
  id: string
  body: string
  is_public: boolean
  is_solution: boolean
  author_name: string | null
  author_type: 'agent' | 'client'
  created_at: string
  /** Traducción en tiempo real (16-11-2026): idioma del cuerpo (null si no se sabe). */
  language?: string | null
}

/** ticket_out(include_comments=True): historial (`field`, no `field_name`). */
export type SdTicketHistorial = {
  field: string | null
  old_value: string | null
  new_value: string | null
  changed_by: string
  changed_at: string
}

/** catalog_approval_service.serializar. */
export type SdAprobacionDeTicket = {
  id: string
  status: string
  comment: string | null
  approver_user_id: string | null
  approver_name: string | null
  decided_by_name: string | null
  decided_at: string | null
  created_at: string | null
}

/** ticket_read_service.ticket_detail_payload. */
export type SdTicketDetalle = SdTicket & {
  comments: SdTicketComentario[]
  history: SdTicketHistorial[]
  dynamic_fields: Record<string, unknown>
  approval: SdAprobacionDeTicket | null
  fulfillment_tasks: { id: string; number: string; title: string; status: string; group_name: string | null; assignee_name: string | null; sla_resolution_due?: string | null; sla_breached?: boolean }[]
  /** Mejoras de mercado 16-11-2026: todas las tareas del servicio por etapa (`planned` las que aún no han nacido). */
  fulfillment_plan?: { task_id: string; title: string; stage: number; status: string; ticket_id: string | null; ticket_number: string | null; sla_resolution_due: string | null; sla_breached: boolean }[]
  parent: { id: string; number: string | null } | null
  /** Traducción en tiempo real (16-11-2026): idioma del ticket y, si lo creó el sistema, su plantilla. */
  language?: string | null
  system_template?: string | null
  system_params?: Record<string, unknown> | null
}

/** link_service.serialize_ticket_link. */
export type SdTicketEnlace = {
  link_id: string
  link_type: string
  direction: 'outbound' | 'inbound'
  ticket_id: string
  ticket_number: string
  ticket_title: string
  ticket_status: string
  ticket_priority: string
}

/** watcher_service.serialize_ticket_watcher. */
export type SdTicketSeguidor = { id: string; user_id: string; user_name: string | null; user_email: string | null; since: string | null }

/** POST /sd/tickets/{id}/comments. */
export type SdComentarioCreado = { id: string; body: string; is_public: boolean; author_name: string; created_at: string }

/** ticket_ops_service.add_ticket_time (+ el resultado de pasarlo a los partes). */
export type SdTiempoRegistrado = {
  ok: boolean
  total_minutes: number
  logged_minutes: number
  timesheet: 'off' | 'skipped' | 'created'
  reason?: string
  imputation_id?: string
  hours?: number
}

/** ticket_ops_service.restore_pending_snapshot. */
export type SdRestauracion = { ok: boolean; restored: boolean; status?: string; detail?: string }

/** ticket_ops_service.escalate_ticket_level. */
export type SdEscalado = { ok: boolean; from: string; to: string }

/** sla_service.pause_ticket_sla (`paused_at`) / sla_event_service.resume_ticket_sla (`paused_minutes`). */
export type SdPausaSla = { ok: boolean; paused_at?: string; paused_minutes?: number }

/** watcher_service.watch_ticket_command / unwatch_ticket_command. */
export type SdSeguir = { ok: boolean; already_watching?: boolean; id?: string }

/** merge_split_service.merge_ticket_command. */
export type SdFusion = { ok: boolean; primary: string; merged: string }

/** POST /sd/tickets/{id}/split. */
export type SdDivision = { ok: boolean; parent: string; child: string; child_id: string }

/** ai_suggest_service.build_ai_ticket_suggestion. */
export type SdSugerenciaIA = {
  ticket_id: string
  ticket_number: string
  draft: string | null
  ai_error: string | null
  kb_matches: { id: string; number: string; title: string; summary?: string | null }[]
  canned_matches: { id: string; title: string; body: string; [extra: string]: unknown }[]
  documents: { document_id: string; title: string; snippet: string }[]
  documents_configured: boolean
  documents_error: string | null
}

// ── Problemas y KEDB ───────────────────────────────────────────────────────

/** problem_service.list_problems_payload. */
export type SdProblema = {
  id: string
  number: string
  title: string
  description: string
  status: string
  priority: string
  root_cause: string | null
  workaround: string | null
  fix_description: string | null
  ci_name: string | null
  owner_name: string | null
  related_ticket_count: number
  created_at: string
  resolved_at: string | null
}

/** POST /sd/problems. */
export type SdProblemaCreado = { id: string; number: string }

/** problem_service.cerrar_problema. */
export type SdProblemaCerrado = { ok: boolean; id: string; status: string; already_closed: boolean }

/** known_error_service.serialize_known_error. `id` es el del Known Error;
 *  para editar se usa `problem_id`. */
export type SdErrorConocido = {
  id: string
  problem_id: string
  number: string | null
  title: string
  description: string | null
  workaround: string | null
  root_cause: string | null
  rca_type: string | null
  rca_evidence: string | null
  rca_approved_at: string | null
  ci: string | null
  ci_id: string | null
  priority: string | null
  affected_tickets: number
  affected_ticket_ids: string[]
  kedb_published_at: string | null
  kedb_expires_at: string | null
  kedb_reviewed_at: string | null
  kedb_effectiveness_score: number | null
  kb_article_id: string | null
  is_active: boolean
}

/** known_error_service.tickets_de_un_error_conocido. */
export type SdTicketDeErrorConocido = { id: string; number: string; title: string; status: string; priority: string; created_at: string | null }

// ── Base de conocimiento ───────────────────────────────────────────────────

/** kb_service.serialize_kb_articles (vista interna: con status y contadores). */
export type SdArticuloKb = {
  id: string
  number: string
  title: string
  summary: string | null
  body: string | null
  tags: string | null
  is_public: boolean
  view_count: number
  helpful_count: number
  author_name: string | null
  published_at: string | null
  status?: string
  not_helpful_count?: number
  deflection_count?: number
  review_comment?: string | null
  author_id?: string | null
}

/** kb_service.serialize_kb_article_detail (sin status ni is_public). */
export type SdArticuloKbDetalle = {
  id: string
  number: string
  title: string
  body: string
  summary: string | null
  tags: string | null
  view_count: number
  helpful_count: number
}

/** POST /sd/kb. */
export type SdArticuloCreado = { id: string; number: string }

/** POST /sd/kb/{id}/submit y /review. */
export type SdRevisionKb = { ok: boolean; status: string }

/** kb_calidad.resumen. */
export type SdCalidadKb = {
  gaps: { id: string; question: string; times_asked: number; source: string; last_asked_at: string | null }[]
  corrections: { id: string; question: string; answer: string; is_public: boolean; usage_count: number; last_used_at: string | null }[]
  findings: { id: string; kind: 'stale' | 'contradiction'; article_id: string | null; article_number: string | null; other_article_id: string | null; other_article_number: string | null; detail: string | null; first_seen_at: string | null }[]
  counts: { gaps: number; corrections: number; findings: number }
}

/** kb_calidad.pasada, o 202 `{ok, status: 'queued'}` si va a la cola. */
export type SdPasadaKb = { stale?: unknown; contradictions?: unknown; ok?: boolean; status?: 'queued' }

// ── Configuracion del service desk ─────────────────────────────────────────

/** catalog_service._servicio(interno=True). */
export type SdServicioDeCatalogo = {
  id: string
  name: string
  description: string | null
  ticket_type: string
  default_priority: string
  sla_response_hours: number
  sla_resolution_hours: number
  requires_approval: boolean
  /** Solo en la vista interna (no en el portal). */
  approval_user_id?: string | null
  /** Mejoras de mercado 16-11-2026: `single` (el aprobador) o `engine` (motor de aprobaciones). */
  approval_mode?: 'single' | 'engine'
  approval_workflow_id?: string | null
  /** Tareas estructuradas (`sd_service_item_tasks`). */
  fulfillment_tasks?: { id?: string; title: string; group_id: string; assignee_user_id?: string | null; sla_hours?: number | null; stage?: number; description?: string | null }[]
  is_visible_to_clients?: boolean
  default_support_level?: string | null
}

/** catalog_service.list_catalog_payload. */
export type SdCategoriaDeCatalogo = {
  id: string
  name: string
  description: string | null
  icon: string | null
  color: string | null
  services: SdServicioDeCatalogo[]
}

/** Creacion/edicion de categoria, servicio, grupo, politica o plantilla. */
export type SdIdNombre = { id: string; name: string }

/** sla_policy_service.list_sla_policies_payload. */
export type SdPoliticaSla = {
  id: string
  name: string
  description: string | null
  is_default: boolean
  p1_response_hours: number
  p1_resolution_hours: number
  p2_response_hours: number
  p2_resolution_hours: number
  p3_response_hours: number
  p3_resolution_hours: number
  p4_response_hours: number
  p4_resolution_hours: number
  business_hours_only: boolean
  business_start: number
  business_end: number
  business_days: string
  timezone: string | null
  calendar_id: string | null
  clients: SdIdNombre[]
  contracts: SdIdNombre[]
}

/** sla_assignment_service.assign_sla_policy_target. */
export type SdAsignacionSla = { ok: boolean; client_id?: string; contract_id?: string; sla_policy_id: string | null }

/** agent_group_service.serialize_group. */
export type SdGrupo = {
  id: string
  name: string
  description: string | null
  support_level: string
  ola_hours: number | null
  members: { id: string; full_name: string; is_lead: boolean }[]
}

/** ticket_template_service.serialize_ticket_template (solo las activas). */
export type SdPlantillaDeTicket = {
  id: string
  name: string
  ticket_type: string
  /** JSON en texto. */
  custom_fields: string | null
  default_priority: string | null
  description_template: string | null
}

/** canned_response_service.serialize_canned_response. */
export type SdRespuestaRapida = {
  id: string
  title: string
  body: string
  category: string | null
  shortcut: string | null
  is_active: boolean
  created_by: string | null
}

/** canned_response_service.serialize_canned_response_compact. */
export type SdRespuestaRapidaCompacta = Pick<SdRespuestaRapida, 'id' | 'title' | 'body' | 'category' | 'shortcut'>

/** announcement_service.serialize_announcements. */
export type SdAnuncio = {
  id: string
  title: string
  body: string
  type: string
  show_to_clients: boolean
  ci_name: string | null
  starts_at: string | null
  ends_at: string | null
}

// ── CMDB ───────────────────────────────────────────────────────────────────

/** cmdb_service.serialize_ci. */
export type SdCi = {
  id: string
  code: string
  name: string
  ci_type: string
  status: string
  criticality: string | null
  environment: string | null
  version: string | null
  description: string | null
  location: string | null
  vendor: string | null
  ip_address: string | null
  hostname: string | null
  attributes: Record<string, unknown>
  project_id: string | null
  project_name: string | null
  owner_user_id: string | null
  owner_name: string | null
  sla_policy_id: string | null
  is_discovered: boolean
  discovery_provider: string | null
  last_discovered_at: string | null
  drift_detected_at: string | null
}

/** POST /sd/cmdb. */
export type SdCiCreado = { id: string; code: string }

/** cmdb_service.ci_changelog. */
export type SdCambioDeCi = {
  id: string
  action: string
  field: string | null
  old_value: string | null
  new_value: string | null
  summary: string | null
  user_name: string | null
  created_at: string | null
}

/** cmdb_relation_service.get_ci_relations_payload. */
export type SdRelacionDeCi = {
  id: string
  relation_type: string
  source: { id: string; name: string; type: string }
  target: { id: string; name: string; type: string }
  notes: string | null
}

/** cmdb_relation_service.get_ci_topology_graph_payload. */
export type SdTopologiaDeCi = {
  root_ci_id: string
  radius: number
  nodes: { id: string; name: string; ci_type: string; criticality: string | null; is_root: boolean; depth: number }[]
  edges: { id: string; source: string; target: string; relation_type: string }[]
  truncated: boolean
}

/** cmdb_clases.campos / guardar_clase. */
export type SdCamposDeClase = {
  por_defecto: boolean
  clases: Record<string, { key: string; label: string | null; field_type: string }[]>
}

/** cmdb/models.list_agent_registrations. */
export type SdAgenteCmdb = {
  id: string
  name: string
  description: string | null
  token_prefix: string
  os_type: string | null
  is_active: boolean
  last_checkin_at: string | null
  last_checkin_ip: string | null
  last_hostname: string | null
  ci_id: string | null
  created_at: string | null
}

/** cmdb/models.generate_agent_token: el token solo se ve una vez. */
export type SdAgenteRegistrado = { agent_id: string; token: string; token_prefix: string; name: string }

/** alm_service.serialize_asset (AssetSerializer): lo que lee la ficha del CI. */
export type SdActivoDeCi = {
  id: string
  name: string
  serial_number: string | null
  status: string | null
  ci_id: string | null
  [extra: string]: unknown
}

// ── Configuracion operativa: enrutado, escalado, avisos, guardias ──────────

/** POST /sd/escalation-rules: `{ok, id}`. */
export type SdOkConId = { ok: boolean; id: string }

/** Borrados de cmdb_service (calendarios y festivos SLA). */
export type SdOkConMensaje = { ok: boolean; message: string }

/** Altas que solo devuelven el id (turno de guardia, incidente de la página de estado). */
export type SdIdCreado = { id: string }

/** routing_rule_service.serialize_routing_rule: `conditions` y `actions` llegan como objetos. */
export type SdReglaDeEnrutado = {
  id: string
  name: string
  is_active: boolean
  priority: number
  conditions: Record<string, unknown>
  actions: Record<string, unknown>
}

/** major_incident_service.serialize_major_incident (fechas ISO 8601). */
export type SdIncidenteMayor = {
  id: string
  number: string
  title: string
  status: string
  severity: string
  declared_at: string | null
  resolved_at: string | null
  commander: string | null
  impact_statement: string | null
  notifications_sent: number
}

/** escalation_service.serialize_escalation_rule (`applies_to_priority` y `notify_user_ids`: JSON en texto). */
export type SdReglaDeEscalado = {
  id: string
  name: string
  is_active: boolean
  sort_order: number
  trigger: string
  action: string
  applies_to_priority: string | null
  idle_hours_threshold: number | null
  group_id: string | null
  target_group_id: string | null
  notify_user_ids: string | null
  target_priority: string | null
}

/** escalation_service.serialize_escalation_log. */
export type SdDisparoDeEscalado = {
  id: string
  rule_name: string | null
  ticket_number: string | null
  action_taken: string | null
  triggered_at: string | null
}

/** notification_template_service.listar: textos de un aviso en un idioma. */
export type SdTextoDeAviso = {
  subject: string
  body_html: string
  is_active: boolean
  customized: boolean
  default_subject: string
  default_body_html: string
}

/** notification_template_service.listar (`code` = `sd.<event>.<role>`). */
export type SdAviso = { code: string; event: string; role: string; languages: Record<string, SdTextoDeAviso> }

/** notification_template_service.guardar / restaurar (`is_active` solo al guardar). */
export type SdAvisoGuardado = { code: string; language: string; customized: boolean; is_active?: boolean }

/** notification_template_service.vista_previa. */
export type SdVistaPreviaDeAviso = { subject: string; body_html: string }

/** oncall_service.serialize_oncall_schedule (turnos incluidos). */
export type SdCalendarioDeGuardia = {
  id: string
  name: string
  group_id: string
  group_name: string | null
  rotation: string | null
  timezone: string | null
  is_active: boolean
  description: string | null
  entries: { id: string; user_id: string; user_name: string | null; start_dt: string; end_dt: string; notes: string | null }[]
}

/** oncall_service.serialize_current_oncall_entry. */
export type SdDeGuardiaAhora = {
  schedule_id: string
  schedule_name: string | null
  group_name: string | null
  user_id: string
  user_name: string | null
  user_email: string | null
  until: string
}

/** monitoring_ingest.ultimas. */
export type SdAlertaDeMonitor = {
  id: string
  source: string
  status: string
  severity: string | null
  title: string
  occurrences: number
  ticket_id: string | null
  ticket_number: string | null
  first_seen_at: string | null
  last_seen_at: string | null
}

/** buzones.ultimos_mensajes. */
export type SdCorreoEntrante = {
  id: string
  received_at: string | null
  sender: string | null
  outcome: string
  reason: string | null
  ticket_id: string | null
  ticket_number: string | null
  channel: string | null
}

/** buzones.probar_buzon: `unread` es null si Graph no lo da. */
export type SdPruebaDeBuzon = { ok: boolean; protocol: string | null; unread?: number | null; error?: string }

/** buzones.leer_buzon: o el recuento de la pasada o el motivo por el que no se leyó. */
export type SdLecturaDeBuzon =
  | { error: string }
  | { created: number; commented: number; ignored: number; failed: number }

/** catalog_approval_service.mis_pendientes. */
export type SdAprobacionPendiente = {
  approval_id: string
  ticket_id: string
  number: string
  title: string
  requester_name: string | null
  service_item_name: string | null
  created_at: string | null
}

// ── Pagina de estado ───────────────────────────────────────────────────────

/** status_page_service.enlace_publico (`embed` solo si la organización existe). */
export type SdEnlaceDePaginaDeEstado = { slug: string | null; url: string | null; embed?: string }

/** status_page_service.serialize_status_component. */
export type SdComponenteDeEstado = {
  id: string
  name: string
  description: string | null
  group_name: string | null
  sort_order: number
  status: 'operational' | 'degraded_performance' | 'partial_outage' | 'major_outage' | 'maintenance'
  is_public: boolean
  ci_id: string | null
  uptime_30d_pct: number | null
}

// ── Planificacion de cambios y CAB ─────────────────────────────────────────

/** change_calendar_service.serializar_congelacion. */
export type SdCongelacion = { id: string; name: string; reason: string | null; start_at: string; end_at: string }

/** change_calendar_service.serializar_version (`changes` en listado y altas, no en el calendario). */
export type SdVersionDeCambios = {
  id: string
  name: string
  version: string | null
  status: string
  notes: string | null
  planned_date: string | null
  released_at: string | null
  owner_id: string | null
  owner_name: string | null
  changes?: { id: string; number: string; title: string; status: string }[]
}

/** change_calendar_service.choques. */
export type SdChoqueDeCambio = { change_id: string; number: string; title: string; planned_start: string; planned_end: string; cis: string[] }

/** change_calendar_service.calendario: un cambio del periodo. */
export type SdCambioEnCalendario = {
  id: string
  number: string
  title: string
  status: string
  change_type: string
  risk: string
  planned_start: string
  planned_end: string | null
  release_id: string | null
  conflicts: SdChoqueDeCambio[]
  in_blackout: boolean
}

/** change_calendar_service.calendario. */
export type SdCalendarioDeCambios = { changes: SdCambioEnCalendario[]; blackouts: SdCongelacion[]; releases: SdVersionDeCambios[] }

/** cab_workflow_service.get_workflow. */
export type SdComiteDeCambio = {
  change_id: string
  /** `requester` | `cab` (en revisión), `rejected`, `executor` o el estado del cambio. */
  status: string
  cab_members: string[]
  quorum: number | null
  meeting: { scheduled_at: string; agenda: string | null } | null
  votes: { user_id: string; name: string | null; approved: boolean; decision: string; note: string | null; voted_at: string | null }[]
  executor_user_id: string | null
}

/** POST /sd/changes/{id}/cab/vote. */
export type SdVotoDeComite = { ok: boolean; workflow: SdComiteDeCambio | null }

// ── Formularios dinamicos ──────────────────────────────────────────────────

/** Condición de un campo o de una pista de enrutado (dict libre que guarda el administrador). */
export type SdCondicionDinamica = { field?: string; equals?: unknown; in?: unknown[] }

/**
 * Campo dinámico. Las reglas son `list[dict]` libres (DynamicRulesIn): esto es
 * lo que escriben `_default_rules`, el asistente de importación y la pantalla.
 */
export type SdCampoDinamico = {
  id: string
  label?: string
  type?: string
  required?: boolean
  options?: string[]
  visible_when?: SdCondicionDinamica | null
  data_source?: string | null
  data_attribute?: string | null
  source_column?: string
}

/** dynamic_forms_service.reglas_o_sembrar / _save_rules_with_history. */
export type SdReglasDinamicas = {
  version: number
  updated_at: string
  updated_by: string | null
  cmdb_context_enabled: boolean
  customer_context_enabled: boolean
  fields: SdCampoDinamico[]
  routing_hints: { when?: SdCondicionDinamica; set?: Record<string, unknown> }[]
}

/** Entrada del historial (`GET /sd/dynamic-forms/history`, lista desenvuelta). */
export type SdInstantaneaDinamica = { snapshot_id: string; created_at: string; created_by: string | null; reason: string; rules: SdReglasDinamicas }

/** `rollback` e `import/apply` (`field_count` solo en este). */
export type SdReglasDinamicasGuardadas = { ok: boolean; rules: SdReglasDinamicas; field_count?: number }

/** POST /sd/dynamic-forms/import/preview. */
export type SdVistaPreviaDeImportacion = {
  columns: string[]
  row_count: number
  generated_fields: SdCampoDinamico[]
  sample_rows: Record<string, string>[]
}

/** dynamic_forms_service._context_options_payload. */
export type SdOpcionesDeContexto = {
  clients: { id: string; name: string }[]
  services: { id: string; name: string; ticket_type: string }[]
  cis: { id: string; code: string; name: string; ci_type: string; status: string; environment: string; project_id: string | null }[]
}

// ── Metricas ───────────────────────────────────────────────────────────────

/** analytics_service.get_itil_metrics_payload. */
export type SdMetricasItil = {
  period: { from: string; to: string }
  volume: { total: number; open: number; resolved: number; breached_sla: number }
  sla_compliance_pct: number
  mttr_minutes: number
  mttr_hours: number
  fcr_percent: number
  avg_csat: number | null
  by_type: Record<string, number>
  by_priority: Record<string, number>
  breach_by_priority: Record<string, number>
}

/** analytics_service.get_agent_performance_payload. */
export type SdRendimientoDeAgente = {
  agent_id: string
  agent_name: string
  total: number
  resolved: number
  open: number
  mttr_minutes: number
  avg_csat: number | null
  sla_breaches: number
}

/** cmdb_service.get_agent_dashboard (`GET /cmdb/agent-dashboard/{id}`). */
export type SdPanelDeAgente = {
  agent_id: string
  period_days: number
  current: { open_tickets: number }
  kpis: { total_resolved: number; avg_resolution_hours: number; sla_compliance_pct: number; avg_csat: number | null }
  trend: { date: string; resolved: number; sla_ok: number; sla_fail: number; csat: number | null }[]
}

// ── Asignacion y autorresolucion ───────────────────────────────────────────

/** incident_assignment_service._agregar_agentes (id y nombre duplicados a propósito). */
export type SdCargaDeAgente = {
  user_id: string
  agent_id: string
  agent_name: string
  name: string
  open_tickets: number
  active_tickets: number
  capacity: number
  specializations: string[]
  is_on_call: boolean
  groups: string[]
}

/** incident_assignment_service.get_assignment_stats (los contadores solo existen tras la primera recomendación). */
export type SdEstadisticasDeAsignacion = {
  total_recommendations?: number
  last_recommendation_at?: string
  agent_loads: SdCargaDeAgente[]
  total_unassigned: number
  lgbm_available: boolean
}

/** ml_routing_service.score_agent_for_ticket_ml, resumido por recommend_assignment. */
export type SdPuntuacionDeAgente = {
  user_id: string
  name: string
  score: number
  available: boolean
  components: { availability: number; historical_speed: number; historical_csat: number; skill_match: number }
}

/** incident_assignment_service.recommend_assignment. */
export type SdRecomendacionDeAsignacion = {
  recommended_user_id: string | null
  recommended_name: string | null
  confidence: number
  all_scores: SdPuntuacionDeAgente[]
  recommendations: SdPuntuacionDeAgente[]
  method_used: string
  reasoning: string
  lgbm_available: boolean
}

/** POST /sd/tickets/{id}/auto-resolution/feedback. */
export type SdValoracionDeAutorresolucion = { recorded: boolean; ticket_id: string; success: boolean }

// ── RCA guiado ─────────────────────────────────────────────────────────────

/** rca_wizard_service._build_initial_state: un paso (se numeran desde 1). */
export type SdPasoRca = { step: number; label: string; prompt: string; answer: string | null; ai_hint: string | null }

/** rca_wizard_service: estado del asistente guardado en el problema. */
export type SdAsistenteRca = {
  template: string
  started_at: string
  current_step: number
  total_steps: number
  completed: boolean
  steps: SdPasoRca[]
  derived_root_cause: string | null
  derived_workaround: string | null
  derived_classification: string | null
  completed_at: string | null
}

/** GET /rca-wizard: `wizard` es null si aún no se ha empezado. */
export type SdEstadoRca = { wizard: SdAsistenteRca | null }

/** POST /rca-wizard/start y /step. */
export type SdEstadoRcaGuardado = { ok: boolean; wizard: SdAsistenteRca }

/** POST /rca-wizard/ai-assist. */
export type SdPistaRca = { ok: boolean; hint: string; provider: string }

/** POST /rca-wizard/complete. */
export type SdRcaCompletado = {
  ok: boolean
  rca: { root_cause: string; workaround: string | null; rca_type: string; template: string; completed_at: string }
}

// ── Grafo 3D de la CMDB ────────────────────────────────────────────────────

/** cmdb_3d_service.get_3d_graph: nodo. */
export type SdNodo3d = {
  id: string
  name: string
  type: string
  layer: number
  layer_label: string
  x: number
  y: number
  z: number
  status: string
}

/** cmdb_3d_service.get_3d_graph (`layers`: claves numéricas que llegan como texto). */
export type SdGrafo3d = {
  nodes: SdNodo3d[]
  edges: { source: string; target: string; type: string }[]
  layers: Record<string, string>
  node_count: number
  edge_count: number
}

/** cmdb_3d_service.calculate_blast_radius (un CI fuera del grafo llega como `{id, name: id, type: 'unknown'}`). */
export type SdRadioDeImpacto = {
  ci_id: string
  ci_name: string
  impacted_count: number
  impacted_cis: (Partial<SdNodo3d> & { id: string; name: string; type: string; impact_depth: number })[]
  max_depth_reached: number
}

// ── Diseñador de flujos ────────────────────────────────────────────────────

/** Valor de configuración de un nodo. */
export type SdValorDeConfigDeNodo = string | number | null | undefined

/** Nodo tal como lo guarda la pantalla en el grafo (dict libre en el backend). */
export type SdNodoDeFlujoGuardado = {
  id: string
  type: string
  position?: { x: number; y: number }
  data?: { label?: string; type: string; config?: Record<string, SdValorDeConfigDeNodo> }
  label?: string
  config?: Record<string, SdValorDeConfigDeNodo>
}
export type SdAristaDeFlujoGuardada = { id: string; source: string; target: string; branch?: string; label?: string }
export type SdGrafoDeFlujo = { nodes?: SdNodoDeFlujoGuardado[]; edges?: SdAristaDeFlujoGuardada[] }

/** workflow_designer_service.serialize_blueprint. */
export type SdBlueprint = {
  id: string
  name: string
  description: string | null
  process_type: string
  scope: string | null
  status: string
  latest_version: number
  published_version: number | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

/** workflow_designer_service.serialize_version. */
export type SdVersionDeBlueprint = {
  id: string
  blueprint_id: string
  version: number
  graph: SdGrafoDeFlujo
  rules: Record<string, unknown>
  is_published: boolean
  published_at: string | null
  created_at: string
}

/** GET /workflow-designer/blueprints/{id}. */
export type SdDetalleDeBlueprint = { blueprint: SdBlueprint; versions: SdVersionDeBlueprint[] }

/** workflow_designer_service.builtin_templates. */
export type SdPlantillaDeFlujo = { id: string; name: string; process_type: string; description: string; graph: SdGrafoDeFlujo }

/** workflow_designer_service.validate_graph (sin recuentos si el grafo no tiene listas o está vacío). */
export type SdValidacionDeFlujo = { valid: boolean; errors: string[]; warnings: string[]; node_count?: number; edge_count?: number }

/** POST /blueprints/{id}/publish/{version}. */
export type SdBlueprintPublicado = { ok: boolean; blueprint_id: string; published_version: number }

/** DELETE /blueprints/{id} (archivado). */
export type SdBlueprintArchivado = { ok: boolean; archived: boolean }

/** workflow_engine.serialize_run. */
export type SdEjecucionDeFlujo = {
  id: string
  blueprint_id: string
  blueprint_version: number
  target_entity_type: string | null
  target_entity_id: string | null
  status: string
  current_node_id: string | null
  wake_at: string | null
  last_error: string | null
  context: Record<string, unknown>
  created_by_user_id: string | null
  started_at: string | null
  completed_at: string | null
}

/** workflow_engine.serialize_step. */
export type SdPasoDeEjecucion = {
  id: string
  node_id: string
  node_type: string
  status: string
  branch_taken: string | null
  payload: Record<string, unknown>
  error: string | null
  created_at: string | null
  completed_at: string | null
}

/** Ejecución con su historial (detalle, inicio y reanudación). */
export type SdDetalleDeEjecucion = { run: SdEjecucionDeFlujo; steps: SdPasoDeEjecucion[] }

/** POST /runs/{id}/cancel. */
export type SdEjecucionCancelada = { ok: boolean; run: SdEjecucionDeFlujo }

// ── Calendarios SLA (`/cmdb/sla-calendars`) ────────────────────────────────

/** cmdb_service.list_sla_holidays / add / update (`holiday_date`: YYYY-MM-DD). */
export type SdFestivoSla = { id: string; holiday_date: string; name: string | null }

/** cmdb_service.check_is_business_day. */
export type SdComprobacionDeDia = {
  date: string
  is_business_day: boolean
  is_weekend: boolean
  is_holiday: boolean
  holiday_name: string | null
  day_of_week: string
}
