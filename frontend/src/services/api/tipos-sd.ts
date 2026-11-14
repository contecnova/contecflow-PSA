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
  fulfillment_tasks: { id: string; number: string; title: string; status: string; group_name: string | null; assignee_name: string | null }[]
  parent: { id: string; number: string | null } | null
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
  fulfillment_tasks?: { title: string; group_id: string }[]
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
