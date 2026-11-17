/**
 * services/api/serviceDeskMercado.ts — Service desk, mejoras de mercado (16-11-2026).
 *
 * Rutas que ya existían sin pantalla (IA del ticket, agente autónomo, problemas,
 * cambios y CAB, CMDB) y las nuevas (catálogo multinivel, SLA condicionales,
 * ciclos de vida, puesto del agente, canales y asistente del portal).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 */
import api from './_core'
import type { ParamsPeriodoApi } from '../../utils/periodo'

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

// ── IA del ticket ─────────────────────────────────────────────────────────────
export interface TriajeIa {
  ticket_id: string; suggested_category: string; suggested_priority: string
  suggested_agent: string | null; suggested_agent_id: string | null; confidence_pct: number | null; reasoning: string
}
export interface PrediccionSla {
  ticket_id: string; already_breached: boolean; breach_probability: number
  sla_response_due: string | null; sla_resolution_due: string | null
  minutes_until_resolution_due: number | null; predicted_resolution_min: number | null
  risk_level: string; recommendation: string
}
export interface CandidatoDuplicado {
  id: string; number: string; title: string; status: string; priority: string
  created_at: string | null; score: number; reasons: string[]
}
export interface Duplicados { ticket_id: string; ticket_number: string; min_similarity: number; window_days: number; candidates: CandidatoDuplicado[] }
export interface AnalisisIa {
  ticket_id: string; analysis: string; suggestion: string; confidence: number
  kb_sources: { id: string; title: string; number?: string }[]; action_taken: string; recommendation: string
}
export interface ExplicacionIa {
  ok?: boolean; ticket_id: string; ticket_number: string
  auto_resolution: { score?: number; eligible?: boolean; reasons?: string[]; [k: string]: unknown }
  assignment_candidates: { user_id: string; assignment_score: number }[]
  confidence_trace: { auto_resolution_threshold: number; routing_method: string }
}
export interface CandidatoDeAsignacion {
  user_id: string; user_name: string; composite_score: number
  components: { availability: number; historical_speed: number; historical_csat: number; skill_match: number }
  user_status: string; available: boolean
}
export interface CandidatosDeAsignacion { ticket_id: string; ticket_number: string; candidates: CandidatoDeAsignacion[]; score_weights: Record<string, number> }
export interface TicketPriorizado {
  id: string; number: string; title: string; status: string; priority: string
  sla_resolution_due?: string | null; priority_score: number; sla_risk_score: number; business_value_score: number
}

export const iaDelTicketApi = {
  triaje: (id: string) => D<TriajeIa>(api.post(`/ai-planning/triage/${id}`)),
  aceptarTriaje: (id: string, accepted: boolean) => D<{ ok: boolean }>(api.post(`/ai-planning/triage/${id}/accept`, { accepted })),
  prediccionSla: (id: string) => D<PrediccionSla>(api.get(`/sd/predictive/tickets/${id}/sla-breach`)),
  duplicados: (id: string) => D<Duplicados>(api.get(`/sd/tickets/${id}/duplicate-candidates`)),
  /** Fusiona `duplicado` en `destino` (el destino se queda). */
  fusionar: (destino: string, duplicado: string, reason?: string) => D<unknown>(api.post(`/sd/tickets/${destino}/merge`, { merged_ticket_id: duplicado, reason })),
  analizar: (id: string) => D<AnalisisIa>(api.post(`/sd/tickets/${id}/ai-analyze`)),
  explicar: (id: string) => D<ExplicacionIa>(api.get(`/sd/tickets/${id}/ai-explain`)),
  candidatos: (id: string) => D<CandidatosDeAsignacion>(api.get(`/sd/tickets/${id}/routing-candidates`)),
  asignarMejor: (id: string) => D<{ ok: boolean; assigned_to: string; agent_name: string }>(api.post(`/sd/tickets/${id}/smart-assign`)),
  asignarA: (id: string, userId: string) => D<unknown>(api.patch(`/sd/tickets/${id}`, { assigned_to_user_id: userId })),
  colaPriorizada: (params: { page?: number; page_size?: number }) =>
    api.get('/sd/tickets/my-queue/prioritized', { params }).then(r => ({ items: r.data as TicketPriorizado[], meta: (r as { meta?: { total?: number } }).meta })),
}

// ── Agente autónomo ───────────────────────────────────────────────────────────
export type ModoDelAgente = 'suggest' | 'execute'
export interface ConfigDelAgente {
  enabled: boolean; mode: ModoDelAgente; resolve_threshold: number | null; suggest_threshold: number | null
  disabled_playbooks: string[]; builtin_playbooks: string[]; modes: ModoDelAgente[]
}
export interface PasoDePlaybook { type: 'comment' | 'notify' | 'escalate' | 'resolve'; content: string; status?: string }
export interface Playbook {
  id: string; name: string; playbook_type: string; description: string | null; steps: PasoDePlaybook[]
  conditions: { trigger_keywords?: string[]; trigger_categories?: string[]; max_priority?: string; auto_resolve?: boolean }
  is_active: boolean; enabled: boolean; success_count: number; failure_count: number; source: 'custom' | 'builtin'
}
export interface EjecucionDelAgente {
  id: string; ticket_id: string; ticket_number: string | null; playbook_type: string; playbook_id: string | null
  action: string | null; status: string; mode: ModoDelAgente | null; confidence_score: number | null
  resolution_note: string | null; error_message: string | null; actions: PasoDePlaybook[]
  executed_at: string | null; decided_by_user_id: string | null; decided_at: string | null; triggered_by: string
}
export interface EstadisticasDelAgente {
  total_executions: number; success: number; applied: number; suggested: number; discarded: number
  skipped: number; failed: number; success_rate_pct: number; by_playbook_type: Record<string, number>
}

export const agenteAutonomoApi = {
  config: () => D<ConfigDelAgente>(api.get('/sd/autonomous/config')),
  guardarConfig: (data: Partial<ConfigDelAgente>) => D<ConfigDelAgente>(api.put('/sd/autonomous/config', data)),
  playbooks: () => D<Playbook[]>(api.get('/sd/autonomous/playbooks')),
  crearPlaybook: (data: { name: string; description?: string; steps: PasoDePlaybook[]; conditions: Playbook['conditions'] }) => D<{ id: string }>(api.post('/sd/autonomous/playbooks', data)),
  editarPlaybook: (id: string, data: Partial<Playbook>) => D<{ id: string }>(api.put(`/sd/autonomous/playbooks/${id}`, data)),
  borrarPlaybook: (id: string) => D<{ id: string }>(api.delete(`/sd/autonomous/playbooks/${id}`)),
  estadisticas: () => D<EstadisticasDelAgente>(api.get('/sd/autonomous/stats')),
  registro: (params: { page?: number; page_size?: number; status?: string; ticket_id?: string }) =>
    api.get('/sd/autonomous/log', { params }).then(r => ({ items: r.data as EjecucionDelAgente[], meta: (r as { meta?: { total?: number } }).meta })),
  aplicar: (id: string) => D<unknown>(api.post(`/sd/autonomous/executions/${id}/apply`)),
  descartar: (id: string) => D<unknown>(api.post(`/sd/autonomous/executions/${id}/discard`)),
  pasarPorTicket: (ticketId: string, mode?: ModoDelAgente) => D<{ mode: ModoDelAgente; action: string; reason: string; eligible: boolean }>(api.post(`/sd/autonomous/tickets/${ticketId}/resolve`, { mode })),
  pasarAhora: () => D<Record<string, number>>(api.post('/sd/autonomous/scan')),
}

// ── Problemas, RCA y KEDB ─────────────────────────────────────────────────────
export interface IncidenteVinculado {
  id: string; number: string; title: string; status: string; priority: string; ci_id: string | null
  created_at: string | null; is_causal: boolean; notes: string | null; linked_by: string | null; linked_at: string | null
}
export interface PlantillaRca {
  id: string; uuid?: string; name: string; template_type: string; description: string | null
  total_steps: number; is_system: boolean; is_active: boolean; steps?: { step: number; label: string; prompt: string }[]
}

export const problemasApi = {
  incidentes: (id: string) => D<IncidenteVinculado[]>(api.get(`/sd/problems/${id}/linked-incidents`)),
  vincular: (id: string, ticket_ids: string[]) => D<unknown>(api.post(`/sd/problems/${id}/link-incidents`, { ticket_ids })),
  crearCambio: (id: string, data: { change_type: string; planned_start?: string; planned_end?: string }) => D<{ id: string; number: string; status: string }>(api.post(`/sd/problems/${id}/create-change`, data)),
  aprobarRca: (id: string, evidence?: string) => D<unknown>(api.post(`/sd/problems/${id}/approve-rca`, { evidence })),
  revisarKedb: (id: string, extend_days?: number) => D<unknown>(api.post(`/sd/problems/${id}/kedb-review`, { extend_days })),
  efectividadKedb: (id: string) => D<{ problem_id: string; problem_number: string; effectiveness_score: number | null }>(api.get(`/sd/problems/${id}/kedb-effectiveness`)),
  promoverKedb: (id: string, data: { workaround?: string; review_days?: number; auto_kb?: boolean }) => D<unknown>(api.post(`/sd/problems/${id}/promote-kedb`, data)),
  plantillas: () => D<PlantillaRca[]>(api.get('/sd/rca/templates')),
  crearPlantilla: (data: { name: string; template_type: string; steps_json: string; description?: string }) => D<{ id: string }>(api.post('/sd/rca/templates', data)),
  editarPlantilla: (id: string, data: { name?: string; description?: string; steps_json?: string; is_active?: boolean }) => D<unknown>(api.put(`/sd/rca/templates/${id}`, data)),
  borrarPlantilla: (id: string) => D<unknown>(api.delete(`/sd/rca/templates/${id}`)),
}

// ── Cambios y CAB ─────────────────────────────────────────────────────────────
export interface PanelDelCabItem {
  id: string; number: string; title: string; status: string; change_type: string; risk: string | null
  auto_risk_score: number | null; auto_risk_label: string | null; impact_analyzed: boolean
  planned_start: string | null; planned_end: string | null
}
export interface WhatIf {
  downtime_minutes?: number; change_type?: string; extra_ci_ids?: string[]; remove_ci_ids?: string[]
  scheduled_hour_utc?: number; scheduled_dow?: number
}

export const cambiosApi = {
  analizarImpacto: (id: string) => D<Record<string, unknown>>(api.post(`/sd/changes/${id}/impact-analysis`)),
  impacto: (id: string) => D<Record<string, unknown>>(api.get(`/sd/changes/${id}/impact-analysis`)),
  matrizDeRiesgo: (id: string) => D<{ change_id: string; risk_matrix: Record<string, unknown>[] }>(api.get(`/sd/changes/${id}/risk-matrix`)),
  generarVueltaAtras: (id: string) => D<Record<string, unknown>>(api.post(`/sd/changes/${id}/rollback-plan`)),
  vueltaAtras: (id: string) => D<Record<string, unknown>>(api.get(`/sd/changes/${id}/rollback-plan`)),
  generarPruebas: (id: string) => D<Record<string, unknown>>(api.post(`/sd/changes/${id}/testing-plan`)),
  pruebas: (id: string) => D<Record<string, unknown>>(api.get(`/sd/changes/${id}/testing-plan`)),
  generarComunicaciones: (id: string) => D<Record<string, unknown>>(api.post(`/sd/changes/${id}/comms-plan`)),
  comunicaciones: (id: string) => D<Record<string, unknown>>(api.get(`/sd/changes/${id}/comms-plan`)),
  simular: (id: string, data: WhatIf) => D<Record<string, unknown>>(api.post(`/sd/changes/${id}/whatif`, data)),
  panelDelCab: (params: { status?: string; min_risk_score?: number; page?: number; page_size?: number }) => D<{ items: PanelDelCabItem[]; total?: number; unscored?: number }>(api.get('/sd/changes/cab-dashboard', { params })),
  flujoCab: (id: string) => D<Record<string, unknown>>(api.get(`/sd/changes/${id}/cab/workflow`)),
  reunionCab: (id: string, data: { scheduled_at: string; agenda: string }) => D<unknown>(api.post(`/sd/changes/${id}/cab/meeting`, data)),
  aprobarDirecto: (id: string, approved: boolean, reason?: string) => D<{ ok: boolean; status: string }>(api.post(`/sd/changes/${id}/approve`, { approved, reason })),
  viaRapida: (id: string, data: { approver_ids: string[]; justification: string }) => D<unknown>(api.post(`/sd/changes/${id}/cab/fast-track`, data)),
  radioDeImpacto: (ciId: string) => D<Record<string, unknown>>(api.get(`/sd/cmdb/${ciId}/blast-radius`)),
}

// ── Catálogo inteligente ──────────────────────────────────────────────────────
export interface ServicioSugerido { service_id: string; service_name: string; category_name?: string | null; ticket_count?: number; reason?: string; score?: number }
export interface SugerenciaDeServicio { service_id: string | null; service_name: string | null; category_name: string | null; confidence: 'high' | 'medium' | 'low'; method: string; alternatives: ServicioSugerido[] }
export interface RellenoSugerido { suggested_title?: string; suggested_priority?: string; suggested_urgency?: string; custom_fields?: Record<string, unknown>; method?: string }

export const catalogoInteligenteApi = {
  recomendados: (query?: string) => D<{ recommendations: ServicioSugerido[] }>(api.get('/sd/catalog/smart/recommendations', { params: { query } })).then(r => r.recommendations),
  populares: () => D<ServicioSugerido[]>(api.get('/sd/catalog/smart/popular')),
  sugerir: (query: string) => D<SugerenciaDeServicio>(api.post('/sd/catalog/smart/suggest', { query, use_ai: true })),
  rellenar: (description: string, service_id?: string) => D<RellenoSugerido>(api.post('/sd/catalog/smart/prefill', { description, service_id })),
}

// ── SLA condicionales, OLA por prioridad y ciclos de vida ─────────────────────
export interface ReglaSla {
  id?: string; name: string; is_active: boolean; sort_order: number
  service_item_id: string | null; ticket_type: string | null; client_id: string | null; contract_id: string | null; priority: string | null
  response_hours: number | null; resolution_hours: number | null; sla_policy_id: string | null
}
export interface OlaDeCola { group_id: string; default_hours: number | null; targets: Record<string, number | null> }
export interface EstadoDeCiclo { key: string; label: string; base_status: string; is_initial?: boolean; color?: string | null; allowed?: boolean }
export interface CicloDeVida {
  id?: string; ticket_type: string; name: string; is_active: boolean; restrict_transitions: boolean
  states: EstadoDeCiclo[]; transitions: { from_key: string; to_key: string }[]
}
export interface CicloDelTicket { lifecycle: string | null; current: string | null; states: EstadoDeCiclo[] }

export const slaAvanzadoApi = {
  reglas: () => D<ReglaSla[]>(api.get('/sd/sla-rules')),
  crearRegla: (r: ReglaSla) => D<ReglaSla>(api.post('/sd/sla-rules', r)),
  editarRegla: (id: string, r: ReglaSla) => D<ReglaSla>(api.put(`/sd/sla-rules/${id}`, r)),
  borrarRegla: (id: string) => D<unknown>(api.delete(`/sd/sla-rules/${id}`)),
  ola: (groupId: string) => D<OlaDeCola>(api.get(`/sd/groups/${groupId}/ola-targets`)),
  guardarOla: (groupId: string, targets: Record<string, number | null>) => D<OlaDeCola>(api.put(`/sd/groups/${groupId}/ola-targets`, { targets })),
  ciclos: () => D<CicloDeVida[]>(api.get('/sd/lifecycles')),
  guardarCiclo: (c: CicloDeVida) => D<CicloDeVida>(api.put('/sd/lifecycles', c)),
  borrarCiclo: (id: string) => D<unknown>(api.delete(`/sd/lifecycles/${id}`)),
  cicloDelTicket: (ticketId: string) => D<CicloDelTicket>(api.get(`/sd/tickets/${ticketId}/lifecycle`)),
  cambiarEstado: (ticketId: string, lifecycle_state: string) => D<unknown>(api.patch(`/sd/tickets/${ticketId}`, { lifecycle_state })),
}

// ── Puesto del agente: contexto del cliente y panel personalizable ───────────
export interface ContextoDeCliente {
  ticket_id: string
  requester: { name: string | null; email: string | null; phone: string | null; kind: 'user' | 'portal' | 'external'; department?: string | null }
  client: { id: string; name: string | null } | null
  contract: { id: string; name: string | null; status: string | null } | null
  open_tickets: number; total_tickets: number; avg_csat: number | null
  recent_tickets: { id: string; number: string; title: string; status: string; priority: string; created_at: string | null }[]
  alm: {
    available: boolean
    assets: { id: string; name: string; asset_tag: string | null; serial_number: string | null; type: string; mode: string; since: string | null }[]
    licenses: { id: string; name: string; product_name: string | null; quantity: number; since: string | null; until: string | null }[]
  }
}
export type RolDePanel = 'operation' | 'manager' | 'executive'
export interface PanelGuardado { role: RolDePanel; layout: { widgets: string[]; origin: 'user' | 'org' | 'default' }; widgets?: string[] }

export const puestoDelAgenteApi = {
  contexto: (ticketId: string) => D<ContextoDeCliente>(api.get(`/sd/tickets/${ticketId}/customer-context`)),
  panel: (role: RolDePanel) => D<PanelGuardado>(api.get('/sd/dashboard/layout', { params: { role } })),
  guardarPanel: (role: RolDePanel, widgets: string[], scope: 'user' | 'org' = 'user') => D<PanelGuardado>(api.put('/sd/dashboard/layout', { widgets }, { params: { role, scope } })),
  restablecerPanel: (role: RolDePanel) => D<PanelGuardado>(api.delete('/sd/dashboard/layout', { params: { role } })),
  get: <T,>(ruta: string, params?: Record<string, unknown>) => D<T>(api.get(ruta, { params })),
}

// ── CMDB: descubrimiento, reconciliación, deriva, impacto y clases propias ────
export interface ProveedorDeDescubrimiento {
  id: string; name: string; provider_type: string; is_active: boolean; scan_interval_minutes: number
  next_run_at: string | null; last_run_at: string | null; last_run_status: string | null; created_at: string | null
  config: Record<string, unknown>
}
export interface ClaseDeCi { id: string; key: string; label: string; base_type: string; description: string | null; is_active: boolean; sort_order: number; ci_count: number }

export const cmdbMercadoApi = {
  proveedores: () => D<ProveedorDeDescubrimiento[]>(api.get('/sd/cmdb/discovery/providers')),
  crearProveedor: (data: { name: string; provider_type: string; config: Record<string, unknown>; is_active: boolean; scan_interval_minutes: number }) => D<ProveedorDeDescubrimiento>(api.post('/sd/cmdb/discovery/providers', data)),
  editarProveedor: (id: string, data: Partial<{ name: string; config: Record<string, unknown>; is_active: boolean; scan_interval_minutes: number }>) => D<ProveedorDeDescubrimiento>(api.patch(`/sd/cmdb/discovery/providers/${id}`, data)),
  lanzar: (id: string) => D<Record<string, unknown>>(api.post(`/sd/cmdb/discovery/providers/${id}/run`)),
  lanzarTodos: () => D<Record<string, unknown>>(api.post('/sd/cmdb/discovery/run-all')),
  ejecuciones: (id: string) => D<Record<string, unknown>[]>(api.get(`/sd/cmdb/discovery/providers/${id}/jobs`, { params: { page: 1, page_size: 10 } })),
  aprobarLineaBase: (id: string) => D<Record<string, unknown>>(api.post(`/sd/cmdb/discovery/providers/${id}/approve-baseline`)),
  saludDeReconciliacion: () => D<Record<string, unknown>>(api.get('/sd/cmdb/discovery/reconciliation-health')),
  candidatosDeReconciliacion: (min_confidence: number) => D<{ items: Record<string, unknown>[]; count: number }>(api.get('/sd/cmdb/discovery/reconciliation-candidates', { params: { min_confidence } })),
  fusionarDuplicados: (min_confidence: number) => D<Record<string, unknown>>(api.post('/sd/cmdb/discovery/reconciliation-merge', null, { params: { min_confidence } })),
  // Periodo libre (16-11-2026): `desde`/`hasta`/`days`/`tz` del selector (sigue aceptando `hours`).
  deriva: (params: Partial<ParamsPeriodoApi> & { hours?: number }) => D<Record<string, unknown>>(api.get('/sd/cmdb/discovery/drift-report', { params })),
  radio: (ciId: string) => D<Record<string, unknown>>(api.get(`/sd/cmdb/${ciId}/blast-radius`)),
  retirada: (ciId: string) => D<Record<string, unknown>>(api.get(`/sd/cmdb/${ciId}/deprecation-impact`)),
  clases: () => D<{ base_types: string[]; classes: ClaseDeCi[] }>(api.get('/sd/cmdb/ci-classes')),
  crearClase: (c: Omit<ClaseDeCi, 'id' | 'ci_count'>) => D<ClaseDeCi>(api.post('/sd/cmdb/ci-classes', c)),
  editarClase: (id: string, c: Omit<ClaseDeCi, 'id' | 'ci_count'>) => D<ClaseDeCi>(api.put(`/sd/cmdb/ci-classes/${id}`, c)),
  borrarClase: (id: string) => D<unknown>(api.delete(`/sd/cmdb/ci-classes/${id}`)),
}

// ── Canales: bandeja de conversaciones y estado ───────────────────────────────
export interface Conversacion {
  id: string; channel: 'whatsapp' | 'livechat' | 'slack' | 'teams'; status: 'bot' | 'waiting_agent' | 'agent' | 'closed'
  visitor_name: string | null; external_id: string | null; ticket_id: string | null; ticket_number: string | null
  assigned_user_id: string | null; language: string | null; last_message_at: string | null; created_at: string | null
  /** 17-11-2026: hasta cuándo ha leído cada lado y la ventana de 24 h de WhatsApp. */
  client_read_at?: string | null; agent_read_at?: string | null
  whatsapp_window?: { open: boolean; expires_at: string | null; template: boolean }
}
export interface MensajeDeCanal { id: string; direction: 'in' | 'out'; author_type: 'customer' | 'agent' | 'bot' | 'system'; body: string; created_at: string | null
  /** Traducción en tiempo real (16-11-2026): idioma del mensaje. */
  language?: string | null
  /** 17-11-2026: cómo se entregó (sent | template | failed | outside_window) y el adjunto que lleva. */
  delivery_status?: string | null; attachment_document_id?: string | null; attachment_name?: string | null }
/** Documento del ticket que se puede enviar por el canal (17-11-2026). */
export interface AdjuntoDelTicket { id: string; title: string; file_name: string; mime_type: string | null; size: number | null }

export const canalesApi = {
  conversaciones: (params: { status?: string; page?: number; page_size?: number }) =>
    api.get('/sd/channels/conversations', { params }).then(r => ({ items: r.data as Conversacion[], meta: (r as { meta?: { total?: number } }).meta })),
  conversacion: (id: string, after?: string) => D<{ conversation: Conversacion; messages: MensajeDeCanal[]; attachments?: AdjuntoDelTicket[] }>(api.get(`/sd/channels/conversations/${id}`, { params: { after } })),
  /** Envía un documento del ticket por el canal (WhatsApp o el hilo de Slack), 17-11-2026. */
  enviarAdjunto: (id: string, documentId: string, caption?: string) =>
    D<MensajeDeCanal>(api.post(`/sd/channels/conversations/${id}/attachments`, { document_id: documentId, caption: caption || undefined })),
  /** Conversaciones abiertas de WhatsApp/Slack de un ticket y sus documentos (ficha del ticket, 17-11-2026). */
  delTicket: (ticketId: string) =>
    D<{ conversations: Conversacion[]; attachments: AdjuntoDelTicket[] }>(api.get(`/sd/channels/tickets/${ticketId}/conversations`)),
  tomar: (id: string) => D<Conversacion>(api.post(`/sd/channels/conversations/${id}/take`)),
  /** `salida`: la vista previa revisada (`client_text`/`client_language`); es lo que recibe el cliente (16-11-2026). */
  responder: (id: string, body: string, salida?: { client_text: string; client_language: string } | null) =>
    D<MensajeDeCanal>(api.post(`/sd/channels/conversations/${id}/reply`, { body, ...(salida ?? {}) })),
  cerrar: (id: string) => D<Conversacion>(api.post(`/sd/channels/conversations/${id}/close`)),
  estado: () => D<{ slack: boolean; slack_threads?: boolean; teams: boolean; whatsapp: boolean; livechat: boolean; endpoints: Record<string, string> }>(api.get('/sd/channels/status')),
}
