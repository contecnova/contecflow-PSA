/**
 * Respuestas de analítica, cuadros de mando e IA de asistencia (`/analytics/**`,
 * `/dashboard/**`, `/semantic/**`, `/ai/**`, `/ai-modules/{voice,meetings,smart-schedule}`,
 * `/sd/voice/**`, `/predictions/**`, `/resources/burnout-risk`, `/global-search`,
 * `/sd/auto-resolution/**`, `/sd/alert-clusters/**`, `/portfolios/**`), comprobadas
 * contra los serializadores y servicios del backend que cita cada tipo.
 *
 * Son `type` y no `interface` a propósito (ver tipos-sd.ts). Las listas llegan ya
 * desenvueltas por el interceptor de _core.ts y los `APIResponse {data, meta}`
 * también: `res.data` es el payload.
 */
import type { SugerenciaDeAsignacion } from './tipos-rendimiento'

/** Escrituras que solo confirman. */
export type ConfirmacionAnalitica = { ok: boolean; message?: string }

// ── Consultas analíticas (/analytics) ─────────────────────────────────────────

/** Entrada de `CATALOGUE` (app/api/v1/endpoints/analytics.py), con `¤` ya cambiado por la moneda. */
export type MetricaDelCatalogo = {
  label: string
  category: string
  description: string
  x_label: string
  y_label: string
  default_chart: string
}

/** GET /analytics/catalogue: las métricas agrupadas por categoría. */
export type CatalogoDeMetricas = Record<string, Array<MetricaDelCatalogo & { id: string }>>

/**
 * Fila de una métrica (app/services/metrics/*). Cada manejador devuelve sus
 * columnas, todas escalares: `label` y `value` son las comunes; el resto
 * depende de la métrica (`hours_by_person_week` pone una columna por semana).
 */
export type FilaDeMetrica = { label?: string; value?: number; [columna: string]: string | number | null | undefined }

/** Lo que una métrica añade a su `meta` (`return filas, parche` en app/services/metrics). */
export type ParcheDeMetrica = {
  weeks?: string[]
  persons?: string[]
  forecast_days?: number
  forecast_end?: string
  error?: string
}

/** analytics_service.compute_summary: vacío si no hay valores numéricos. */
export type ResumenDeMetrica = { total?: number; max?: number; min?: number; avg?: number; count?: number }

/** `_respuesta_de_metrica` (GET /analytics/query/{metric_id}). */
export type ConsultaDeMetrica = {
  metric_id: string
  /** La entrada del catálogo, con el parche de la métrica y `error` si no se pudo calcular. */
  meta: MetricaDelCatalogo & ParcheDeMetrica
  filters: {
    date_from: string
    date_to: string
    project_id: string | null
    user_id: string | null
    department: string | null
    project_type: string | null
    client_id: string | null
  }
  rows: FilaDeMetrica[]
  total: number
  summary: ResumenDeMetrica
  /** Periodo libre (16-11-2026): el periodo calculado (`Periodo.a_dict`). */
  periodo?: Record<string, unknown>
}

/** analytics_service.get_filter_options_data (GET /analytics/filters/options). */
export type OpcionesDeFiltroAnalitico = {
  projects: Array<{ id: string; label: string; project_type: string | null; client_id: string | null }>
  users: Array<{ id: string; label: string; department: string | null }>
  departments: string[]
  project_types: string[]
  clients: Array<{ id: string; label: string }>
}

/** analytics_service.get_hours_by_week (GET /analytics/hours_by_week). */
export type HorasPorSemana = {
  data: Array<{ week: string; week_start: string; week_end: string; hours: number }>
  weeks: number
}

type CifrasDeUtilizacion = {
  capacity_hours: number
  actual_hours: number
  booked_hours: number
  actual_utilization_pct: number
  booked_utilization_pct: number
}

/** analytics_service._fila_de_utilizacion. */
export type UtilizacionDePersona = CifrasDeUtilizacion & {
  user_id: string
  full_name: string
  department: string | null
  projected: Array<{ week_start: string; booked_hours: number; capacity_hours: number; utilization_pct: number }>
}

/** analytics_service.get_advanced_utilization (GET /analytics/utilization/advanced). */
export type UtilizacionAvanzada = {
  window: { week_start: string; week_end: string; weeks_ahead: number }
  filters: { project_id: string | null; project_type: string | null; client_id: string | null }
  summary: CifrasDeUtilizacion
  team: UtilizacionDePersona[]
}

/** analytics_service.get_metric_breaches (GET /analytics/alerts/metric-breaches). */
export type AlertasDeMetricas = {
  threshold: number
  total: number
  items: Array<{
    project_code: string | null
    margin_pct: number
    margin: number
    revenue: number
    cost: number
    severity: 'critical' | 'warning'
    title: string
    description: string
  }>
}

/**
 * olap/query_engine.get_kpi_summary (GET /analytics/olap/kpis). Con DuckDB las
 * sumas sin filas llegan `null`; si no hay almacén ni Postgres, solo `source`.
 */
export type KpisOlap = {
  hours_mtd?: number | null
  cost_mtd?: number | null
  active_projects_mtd?: number | null
  billability_pct?: number | null
  active_projects?: number | null
  avg_margin_pct?: number | null
  high_risk_projects?: number | null
  open_opps?: number | null
  pipeline_weighted?: number | null
  won_revenue?: number | null
  source: 'olap' | 'postgresql' | 'unavailable'
  error?: string
}

/** bi_storytelling.generate_narrative (GET /analytics/narrative). */
export type NarrativaEjecutiva = {
  narrative: string
  kpis: KpisOlap
  lang: string
  cached: boolean
  source: string
}

/** ask_verificacion.verificar. */
export type VerificacionDeConsulta = {
  verdict: 'verified' | 'warning' | 'not_checked'
  checks: Array<{ name: string; status: 'ok' | 'warning' | 'skipped'; detail: string }>
  detail?: string
}

/** ask_valores_reales.pistas: un valor buscado que no está, con los que sí hay. */
export type PistaSinFilas = {
  table: string
  column: string
  op: string
  searched: string
  exists: boolean
  closest: string[]
  sample: string[]
  distinct_values_read: number
}

/** ask_the_data.ask (POST /analytics/ask). Los campos opcionales dependen del camino. */
export type RespuestaDeAskTheData = {
  question: string
  sql: string
  columns: string[]
  rows: Array<Record<string, unknown>>
  row_count: number
  truncated: boolean
  error: string | null
  verification?: VerificacionDeConsulta
  model_sql?: string
  examples_used?: string[]
  zero_result_hints?: PistaSinFilas[] | null
  retried_with_real_values?: { first_sql: string }
  from_validated_example?: { id: string; question: string }
}

/** POST /analytics/ask/examples. */
export type EjemploDeAskGuardado = { id: string; question: string }

/** olap/etl.estado: `detail` sin totales salvo para un superadmin. */
export type CargaDelAlmacen = { run_at: string; status: string; detail: Record<string, unknown> | null } | null

/** GET /analytics/olap/status. */
export type EstadoDelAlmacenOlap = {
  last_run: CargaDelAlmacen
  last_ok: CargaDelAlmacen
  company_rows: Record<'fact_imputations' | 'fact_projects' | 'fact_pipeline' | 'fact_tickets', number>
}

/** olap/etl.resumen_de_carga (POST /analytics/olap/refresh): completo solo para superadmin. */
export type CargaOlapRealizada = { status: string; since?: string; seconds?: number; error?: string; [k: string]: unknown }

/** get_pipeline_funnel (GET /analytics/olap/pipeline-funnel). */
export type EtapaDelEmbudoOlap = {
  stage: string
  count: number
  total_revenue: number | null
  weighted_revenue: number | null
  avg_probability: number | null
  avg_days: number | null
}

/** get_portfolio_health (GET /analytics/olap/portfolio-health); `milestones_*` solo con DuckDB. */
export type SaludDeProyectoOlap = {
  project_id: string
  code: string
  name: string
  status: string
  budget: number | null
  total_cost: number | null
  margin_pct: number | null
  tasks_total: number | null
  tasks_done: number | null
  completion_pct: number | null
  milestones_done?: number | null
  milestones_total?: number | null
  risk_level: string | null
}

/** get_margin_evolution (GET /analytics/olap/margin-evolution). */
export type MargenMensualOlap = {
  /** `YYYY-MM` del tramo (compatibilidad: antes la serie era solo mensual). */
  month: string
  total_cost: number | null
  active_projects: number
  /** Periodo libre: inicio del tramo (ISO con desfase) y su clave `YYYY-MM-DDTHH:MI`. */
  t?: string
  clave?: string
  granularidad?: 'day' | 'week' | 'month'
}

/** get_utilization_by_user (GET /analytics/olap/utilization). */
export type UtilizacionOlap = {
  user_id: string
  full_name: string
  department: string | null
  logged_hours: number | null
  monthly_capacity: number | null
  utilization_pct: number | null
}

// ── Cuadro de mando (/dashboard) ──────────────────────────────────────────────

/** schemas/dashboard.DashboardKPIs (GET /dashboard/kpis). */
export type KpisDelCuadroDeMando = {
  total_budget: number
  total_spent: number
  budget_used_pct: number
  projects_active: number
  projects_at_risk: number
  projects_over_budget: number
  total_resources: number
  overloaded_resources: number
  avg_load_pct: number
  tasks_open: number
  tasks_blocked: number
  tasks_overdue: number
  avg_efficiency_ratio: number
  hours_logged_this_week: number
}

/** schemas/dashboard.ProjectHealthItem (GET /dashboard/projects-health). */
export type SaludDeProyecto = {
  project_id: string
  project_name: string
  project_code: string
  budget_used_pct: number
  schedule_deviation_days: number
  risk_level: string
  status: string
  team_size: number
  alerts_count: number
  tasks_total: number
  tasks_done: number
  progress_pct: number
  health_score: number
}

/** schemas/dashboard.ResourceLoadItem (GET /dashboard/resource-load). */
export type CargaDeRecurso = {
  user_id: string
  user_name: string
  department: string
  load_pct: number
  hours_week: number
  active_projects: number
  efficiency: number
}

/** dashboard_service.get_profitability (GET /dashboard/profitability). */
export type RentabilidadDeProyecto = {
  project_id: string
  project_code: string
  project_name: string
  is_billable: boolean
  budget_amount: number | null
  total_cost: number
  total_hours: number
  revenue: number
  margin: number
  margin_pct: number | null
}

/** dashboard_service.get_team_productivity (GET /dashboard/productivity/team). */
export type ProductividadDelEquipo = {
  period_start: string
  period_end: string
  team_stats: Array<{
    user_id: string
    user_name: string
    department: string | null
    job_title: string | null
    hours_logged: number
    tasks_completed: number
  }>
  /** Periodo libre (16-11-2026): el periodo calculado; null sin periodo pedido (mes en curso). */
  periodo?: Record<string, unknown> | null
}

// ── Motor semántico (/semantic) ───────────────────────────────────────────────

/** semantic_engine_service.serialize_config (GET /semantic/config). */
export type ConfigDelMotorSemantico = {
  engine_mode: string
  threshold_ticket: number
  threshold_task: number
  threshold_expert_cache: number
  load_balance_weight: number
  threshold_critical: number
  threshold_high: number
  threshold_medium: number
  threshold_low: number
  history_decay_days: number
  auto_assign_tickets: boolean
  auto_assign_tasks: boolean
  embeddings_backend: 'tfidf' | 'transformer'
  local_model_name: string | null
  effective_model_name: string
  backend_en_uso: string | null
}

/** PATCH /semantic/config. */
export type ConfigDelMotorSemanticoGuardada = { ok: boolean; config: ConfigDelMotorSemantico }

/** semantic_engine_service.list_profiles_with_users (GET /semantic/profiles). */
export type PerfilSemantico = {
  id: string
  user_id: string
  user_name: string | null
  profile_text: string
  has_embedding: boolean
  open_tickets: number | null
  open_tasks: number | null
  max_load: number | null
  is_available: boolean | null
}

/** semantic_engine_service.upsert_profile (POST /semantic/profiles). */
export type PerfilSemanticoGuardado = { ok: boolean; has_embedding: boolean }

/** semantic_engine_service.auto_generate_profiles. */
export type PerfilesSemanticosGenerados = { created: number; updated: number; total: number }

/** POST /semantic/profiles/rebuild-embeddings. */
export type EmbeddingsReconstruidos = { rebuilt: number }

/** semantic_engine_service.get_stats (GET /semantic/stats). */
export type EstadisticasDelMotorSemantico = {
  total_suggestions: number
  accepted: number
  rejected: number
  pending: number
  accuracy_pct: number | null
  profiles: number
  cache_size: number
  expert_feedback: number
  by_mode: Record<string, number>
}

/** semantic_engine_service.estimate_sprint_backlog (POST /semantic/estimate/sprint-backlog). */
export type EstimacionDelBacklog = {
  estimates: Array<{
    task_id: string | number | null
    title: string
    story_points: number | null
    complexity: string
    base_hours: number
    role_hint: string
    confidence: number
  }>
  total_base_hours: number
  risk_premium_pct: number
  recommended_hours: number
  capacity_hours: number
  fit_in_sprint: boolean
  utilization_pct: number
  complex_task_count: number
}

/** POST /semantic/suggest/ticket: la misma forma que la de tareas. */
export type SugerenciaDeAsignacionDeTicket = SugerenciaDeAsignacion

// ── Asistente y agente (/ai) ──────────────────────────────────────────────────

/** agent_execution_service: estados de `AIAgentExecution` (más `queued` al encolar). */
export type EstadoDeEjecucionDelAgente = 'pending' | 'queued' | 'running' | 'awaiting_approval' | 'done' | 'failed'

/** POST /ai/agent. */
export type EjecucionDelAgenteEnCola = { execution_id: string; status: 'queued' }

/** agent_execution_service.list_agent_executions (GET /ai/agent/history). */
export type EjecucionDelAgenteResumen = {
  execution_id: string
  id: string
  instruction: string
  status: EstadoDeEjecucionDelAgente
  result: string | null
  steps_count: number | null
  created_at: string
}

/** agent_execution_service.get_agent_status (GET /ai/agent/{id}/status). */
export type EstadoDelAgente = {
  execution_id: string
  status: EstadoDeEjecucionDelAgente
  result: string | null
  steps_count: number
  created_at: string
  updated_at: string | null
}

/** Paso de una ejecución: la entrada y la salida de la herramienta, ya como JSON. */
export type PasoDelAgente = { step: number; tool: string; input: unknown; output: unknown }

/** agent_execution_service.get_agent_detail_with_steps (GET /ai/agent/{id}). */
export type EjecucionDelAgente = {
  execution_id: string
  instruction: string
  status: EstadoDeEjecucionDelAgente
  result: string | null
  steps: PasoDelAgente[]
  created_at: string
}

/** Artículo de la base citado (service_desk/kb_calidad.contexto). */
export type FuenteDeRespuesta = { id: string; number: string; title: string }

/** POST /ai/chat. */
export type RespuestaDelAsistente = {
  conversation_id: string | null
  message: string
  tokens_used: number
  latency_ms: number
  message_id: string | null
  sources: FuenteDeRespuesta[]
  correction_applied: boolean
}

/** POST /ai/texto. */
export type TextoTransformado = { texto: string }

/** conversation_service.list_conversations (GET /ai/conversations). */
export type ConversacionResumen = {
  id: string
  title: string
  context_type: string | null
  message_count: number
  updated_at: string
}

/** conversation_service.get_conversation (GET /ai/conversations/{id}). */
export type Conversacion = {
  id: string
  title: string | null
  context_type: string | null
  messages: Array<{ id: string; role: 'user' | 'assistant' | 'tool'; content: string; created_at: string }>
}

/** conversation_service.archive_all_conversations (DELETE /ai/conversations). */
export type ConversacionesArchivadas = { ok: boolean; archived: number }

/** valoracion_de_respuestas.valorar_del_asistente. */
export type ValoracionDeRespuesta = { helpful: boolean }

/** ai_copilot_service.get_ai_gantt_suggestions: sugerencia por tarea. */
export type SugerenciaDelGantt = {
  task_id: string
  task_title: string
  type: 'overdue' | 'stalled'
  severity: 'high' | 'medium'
  message: string
  suggestions: string[]
}

/** GET /ai/suggestions/gantt/{project_id}. */
export type SugerenciasDelGantt = {
  project_id: string
  project_name: string
  suggestions_count: number
  suggestions: SugerenciaDelGantt[]
  analysed_at: string
}

/** ai_copilot_service: anomalías de imputación (horas altas, huecos y proyectos cerrados). */
export type AnomaliaDeImputacion =
  | { type: 'high_hours'; date: string; value: number; message: string; suggestion: string }
  | { type: 'gap'; date: string; value: number; message: string; suggestion: string }
  | { type: 'closed_project_billing'; project_ids: string[]; message: string; suggestion: string }

/** GET /ai/suggestions/timesheets/{user_id}. */
export type AnomaliasDeImputacion = {
  user_id: string
  period: { from: string; to: string }
  total_entries: number
  anomalies_count: number
  anomalies: AnomaliaDeImputacion[]
  analysed_at: string
}

// ── Voz, reuniones y planificación (/ai-modules) ──────────────────────────────

/** ai_modules/voice: lo que se ejecutará al confirmar. */
export type AccionDeVozPendiente =
  | { type: 'log_hours'; project_id: string; project_name: string; hours: number }
  | { type: 'create_ticket'; title: string; priority: string }
  | { type: 'create_task'; title: string; project_id: string | null; project_name: string | null; priority: string }

/** ai_modules/voice.process_voice_core (POST /ai-modules/voice/command). */
export type ComandoDeVoz = {
  transcript: string
  intent: string
  entities: Record<string, unknown>
  action: string
  status: string
  latency_ms: number
  confirmed: boolean
  pending_action: AccionDeVozPendiente | null
  execution_id: string | null
}

/** POST /ai-modules/voice/transcribe: el comando en modo prueba con la transcripción. */
export type ComandoDeVozTranscrito = ComandoDeVoz & { whisper_transcript: string }

/** ai_modules/meetings.list_meetings (GET /ai-modules/meetings). */
export type ReunionResumen = {
  id: string
  title: string
  project_id: string | null
  platform: string
  duration_min: number | null
  status: string
  actions_count: number
  created_actions: number
  meeting_date: string | null
  created_at: string
}

/** ai_modules/meetings.get_meeting (GET /ai-modules/meetings/{id}): sin fechas. */
export type Reunion = {
  id: string
  title: string
  project_id: string | null
  platform: string
  duration_min: number | null
  summary: string | null
  decisions: string[]
  risks: string[]
  participants: string[]
  status: string
  actions: Array<{
    id: string
    description: string
    assignee_name: string | null
    assignee_id: string | null
    due_date_text: string | null
    is_created: boolean
    task_id: string | null
  }>
}

/** ai_modules/meetings.process_meeting (POST /ai-modules/meetings/process). */
export type ReunionProcesada = {
  meeting_id: string
  title: string
  summary: string | null
  decisions: string[]
  risks: string[]
  actions: Array<{ id: string; description: string; assignee_name: string | null; due_date_text: string | null }>
  status: string
  latency_ms: number
}

/** ai_modules/meetings.create_tasks_from_meeting. */
export type TareasDeReunionCreadas = {
  ok: boolean
  tasks_created: number
  tasks: Array<{ action_id: string; task_id: string; title: string }>
}

/** Sugerencia del modelo (task_id traducido al UUID real). */
export type FechaSugerida = { task_id: string; suggested_start: string; suggested_due: string; rationale?: string }

/** ai_modules/client_portal.smart_schedule (POST /ai-modules/smart-schedule). */
export type PlanificacionSugerida = {
  scheduled: FechaSugerida[]
  message?: string
  error?: string
  unscheduled_count?: number
  capacity_summary?: Array<{ name: string; available_hours_per_week: number }>
}

// ── Agente de voz del service desk (/sd/voice) ────────────────────────────────

/** voice_agent_service._DEFAULT_CONFIG (lo guardado se fusiona encima). */
export type ConfigDelAgenteDeVoz = {
  greeting: string
  max_silence_seconds: number
  language: string
  dtmf_menu: Record<string, { intent: string; label: string }>
  intent_keywords: Record<string, string[]>
}

/** Un turno de la transcripción. */
export type TurnoDeVoz = { speaker: string; text: string; ts: string }

/** voice_agent_service.create_session / add_transcript_turn / close_session. */
export type SesionDeVoz = {
  id: string
  caller_id: string
  channel: string
  status: 'active' | 'closed'
  intent: string | null
  entities: { ticket_ref?: string; urgency_words?: string[]; email?: string }
  transcript: TurnoDeVoz[]
  ticket_id: string | null
  created_at: string
  updated_at: string
  resolution?: string
  closed_at?: string
}

/** POST /sd/voice/sessions. */
export type SesionDeVozCreada = { session: SesionDeVoz; greeting: string }

/** GET /sd/voice/sessions. */
export type SesionesDeVoz = { sessions: SesionDeVoz[]; count: number }

/** voice_agent_service.create_ticket_from_session. */
export type TicketDeSesionDeVoz = {
  id: string
  number: string
  source: string
  channel: string
  caller_id: string | null
  intent: string
  priority: string
  summary: string
  session_id: string
  created_at: string
}

// ── Predicciones y riesgo de personas ─────────────────────────────────────────

/** ai_modules/predictions._aplicar_reglas: una señal que ha saltado. */
export type SenalDeRiesgo = { signal: string; value: string; weight: number; type: string }

/** ml_trainer.predict_project (POST /predictions/overrun-risk). */
export type PrediccionDeDesvio = {
  project_id: string
  project_name: string
  cpi: number
  spi: number
  budget_used_pct: number
  elapsed_pct: number
  task_completion_pct: number
  overdue_ratio: number
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  used_heuristic: boolean
  cost_overrun_prob: number
  schedule_overrun_prob: number
  cost_overrun_pct: number
  schedule_overrun_days: number
  confidence: 'low' | 'medium' | 'high'
  signals: SenalDeRiesgo[]
  recommendation: string
  ml_overrun_prob: number | null
  model_version: number | null
  model_accuracy: number | null
  prob_decomposition?: string
  prob_decomposition_note?: string
}

/** POST /predictions/overrun-risk cuando no se puede predecir (200 con la marca). */
export type PrediccionImposible = { project_id?: string; error: string; risk_level: 'unknown'; can_predict: false }

/** ml_trainer.portfolio_risk_summary (GET /predictions/portfolio-risk). */
export type RiesgoDeLaCartera = {
  total_projects: number
  risk_counts: Record<'critical' | 'high' | 'medium' | 'low', number>
  without_data: number
  at_risk_projects: Array<{
    project_id: string
    project_name: string
    project_code: string
    risk_level: 'low' | 'medium' | 'high' | 'critical'
    cpi: number | null
    spi: number | null
    cost_overrun_prob: number | null
    schedule_overrun_prob: number | null
    recommendation: string | null
  }>
}

/** ml_trainer.train_model (POST /predictions/train). */
export type EntrenamientoDelModelo =
  | { status: 'skipped'; reason: string; samples: number }
  | { status: 'trained'; model_id: string; version: number; samples: number; accuracy_roc_auc: number | null }

/** ml_trainer.list_models (GET /predictions/models). */
export type ModeloDePrediccion = {
  id: string
  version: number
  samples_used: number
  accuracy: number | null
  is_active: boolean
  trained_at: string | null
  features: string[]
}

/** ml_trainer.get_prediction_logs (GET /predictions/logs). */
export type RegistroDePrediccion = {
  id: string
  project_id: string
  project_name: string | null
  cost_overrun_prob: number | null
  schedule_overrun_prob: number | null
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  used_heuristic: boolean
  predicted_at: string | null
}

/** raci_service.compute_user_burnout_risk. */
export type RiesgoDeAgotamiento = {
  user_id: string
  full_name: string
  department: string | null
  job_title: string | null
  current_load_pct: number
  avg_load_4w: number
  overload_weeks_streak: number
  risk_score: number
  risk_level: 'green' | 'yellow' | 'orange' | 'red'
  factors: string[]
  weekly_history: Array<{ week_start: string; load_pct: number; hours: number }>
}

/** raci_service.get_burnout_risk (GET /resources/burnout-risk). */
export type MonitorDeAgotamiento = {
  computed_at: string
  total_analyzed: number
  summary: Record<'green' | 'yellow' | 'orange' | 'red', number>
  team_avg_load: number
  members: RiesgoDeAgotamiento[]
}

/** raci_service.compute_and_save_burnout_snapshots (POST /resources/burnout-risk/compute). */
export type InstantaneasDeAgotamiento = { week_start: string; processed: number; new_snapshots: number }

// ── Búsqueda global ───────────────────────────────────────────────────────────

/** cab_service/busqueda: un resultado (los usuarios y oportunidades no traen `status`). */
export type ResultadoDeBusqueda = {
  id: string
  type: 'project' | 'task' | 'ticket' | 'user' | 'invoice' | 'opportunity'
  title: string
  subtitle: string
  status?: string
  url: string
  icon: string
}

/** cab_service/busqueda.global_search (GET /global-search). */
export type BusquedaGlobal = {
  query: string
  total: number
  grouped: Partial<Record<'projects' | 'tasks' | 'tickets' | 'users' | 'invoices' | 'opportunities', ResultadoDeBusqueda[]>>
  flat: ResultadoDeBusqueda[]
}

// ── Auto-resolución del service desk ──────────────────────────────────────────

/** ai_auto_resolution_service._normalize_auto_resolution_config. */
export type ConfigDeAutoResolucion = {
  threshold_auto: number
  threshold_suggest: number
  auto_close_hours_after_resolution: number
  validation_window_hours: number
  default_job_limit: number
}

/** run_daily_auto_resolution_job: lo que hizo una pasada. */
export type PasadaDeAutoResolucion = { processed: number; auto_resolved: number; suggested: number; failed: number }

/** Una ejecución del trabajo (estado vigente o historial). */
export type EjecucionDeAutoResolucion = {
  status: string
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  stats: PasadaDeAutoResolucion | null
  error: string | null
}

/** ai_auto_resolution_service.estado_del_trabajo. */
export type EstadoDeAutoResolucion = EjecucionDeAutoResolucion & { running: boolean; last_job_id: string | null }

/** GET /sd/auto-resolution/stats: get_auto_resolution_stats + estado + historial. */
export type EstadisticasDeAutoResolucion = {
  total_auto_resolved: number
  pct_of_all_tickets: number
  feedback_total_validated: number
  overall_success_rate: number | null
  per_bucket: Array<{ bucket: string; total: number; success: number; failed: number; success_rate: number | null }>
  runtime: EstadoDeAutoResolucion
  job_history: EjecucionDeAutoResolucion[]
}

/** auto_resolucion_operaciones.lanzar_trabajo (POST /sd/auto-resolution/run-job). */
export type TrabajoDeAutoResolucion =
  | { status: 'queued'; job_id: string; limit: number; timestamp: string }
  | { status: 'already_running'; message: string; runtime: EstadoDeAutoResolucion; timestamp: string }
  | (PasadaDeAutoResolucion & { status: 'completed'; timestamp: string })

/** run_auto_close_job (POST /sd/auto-resolution/run-close-job). */
export type CierreAutomatico = {
  processed: number
  auto_closed: number
  validated: number
  failed: number
  status: 'completed'
  timestamp: string
}

// ── Correlación de alertas (/sd/alert-clusters) ───────────────────────────────

type CampoDeCluster = {
  cluster_id: string
  size: number
  ci_id: string | null
  category: string | null
  priority: string
  correlation_score: number
  suggested_action: 'create_problem' | 'review' | 'monitor'
  ticket_numbers: string[]
  root_ci_ids: string[]
}

/** alert_correlation.list_alert_clusters: un cluster. */
export type ClusterDeAlertas = CampoDeCluster & { ticket_ids: string[]; earliest_at: string | null; latest_at: string | null }

/** GET /sd/alert-clusters. */
export type ClustersDeAlertas = { window_hours: number; clusters: ClusterDeAlertas[]; total: number }

/** alert_correlation_service.get_correlation_stats (GET /sd/alert-clusters/stats). */
export type EstadisticasDeCorrelacion = {
  window_hours: number
  open_tickets_in_window: number
  clusters_detected: number
  tickets_in_clusters: number
  tickets_needing_problem: number
  top_clusters: CampoDeCluster[]
}

/** POST /sd/alert-clusters/merge. */
export type ClusterFusionado = { ok: boolean; problem_id: string; problem_number: string; linked_tickets: number }

/** POST /sd/alert-clusters/run-scan: el resultado, o `queued` (202) si va al worker. */
export type EscaneoDeCorrelacion =
  | { clusters_found: number; problems_created: number; errors: number }
  | { ok: boolean; status: 'queued'; organization_id: string | null }

// ── Carteras (/portfolios) ────────────────────────────────────────────────────

/** portfolio_service.serialize_portfolio. */
export type Cartera = {
  id: string
  name: string
  description: string | null
  status: string
  budget_total: number | null
  start_date: string | null
  end_date: string | null
  owner_id: string | null
  project_count: number
  created_at: string | null
}

/** Semáforo de un proyecto en la cartera (EVM o el que fija el PM). */
export type RagDeCartera = 'red' | 'yellow' | 'green' | 'grey'

/** GET /portfolios/{id}/dashboard. */
export type PanelDeCartera = {
  portfolio_id: string
  portfolio_name: string
  status: string
  budget_envelope: number
  budget_spent: number
  budget_pct: number
  project_count: number
  health_counts: Record<RagDeCartera, number>
  projects: Array<{
    project_id: string
    project_name: string
    status: string | null
    rag: RagDeCartera
    display_order: number | null
    start_date: string | null
    end_date: string | null
    pct_complete: number
    cpi: number | null
    spi: number | null
    bac: number
    ac: number
    ev: number
    milestones: Array<{ id: string; title: string; due_date: string | null; is_completed: boolean }>
  }>
}
