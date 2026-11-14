/**
 * Tipos de respuesta de aprobaciones, evaluaciones de desempeño y lo que usa
 * el tablero de tareas (campos personalizados, tipos de incidencia, flujo del
 * proyecto, tablero kanban, motor semántico). Comprobados contra los
 * serializadores del backend que cita cada JSDoc.
 *
 * Son `type` (no `interface`) para que se puedan asignar a tipos locales con
 * índice `[k: string]: unknown` sin cast.
 */

// ── Aprobaciones (app/services/approval_engine) ──────────────────────────────

/** serialize_step (_base.py). */
export type PasoDeAprobacion = {
  id: string
  step_order: number
  name: string
  approver_type: string
  approver_role: string | null
  approver_user_id: string | null
  approver_user_name: string | null
  approver_group_id: string | null
  /** La columna existe (ApprovalStep.approver_department) pero serialize_step NO la
   *  devuelve: llega siempre vacía hasta que el backend la añada. */
  approver_department?: string | null
  is_optional: boolean | null
  timeout_hours: number | null
  on_timeout: string | null
  parallel_quorum: boolean
  required_approvals: number
  step_condition: string | null
  requires_attachment: boolean
  reminder_hours: number | null
}

/** serialize_workflow (_base.py). `steps` solo con include_steps (listado y detalle lo piden). */
export type FlujoDeAprobacion = {
  id: string
  name: string
  description: string | null
  entity_type: string
  is_active: boolean
  is_default: boolean
  /** JSON en texto (columna Text). */
  trigger_conditions: string | null
  step_count: number
  created_at: string | null
  chain_on_approval_workflow_id: string | null
  sla_block_on_breach: boolean
  /** JSON en texto (columna Text). */
  auto_approval_rules: string | null
  steps?: PasoDeAprobacion[]
}

/** _WORKFLOW_TEMPLATES (_base.py). */
export type PlantillaDeFlujo = {
  id: string
  name: string
  description: string
  entity_type: string
  trigger_conditions: Record<string, unknown>
  steps: Array<{ step_order: number; name: string; approver_type: string; approver_role?: string; timeout_hours: number; on_timeout: string }>
}

/** validate_workflow (workflows.py). */
export type ValidacionDeFlujo = { workflow_id: string; valid: boolean; issues: string[]; warnings: string[] }

/** simulate_workflow (workflows.py). */
export type SimulacionDeFlujo = {
  matched: boolean
  reason?: string
  candidates?: unknown[]
  workflow?: FlujoDeAprobacion
  conditions?: unknown
  estimated_total_timeout_hours?: number
  route?: Array<{
    step_order: number
    step_name: string
    approver_type: string
    resolved_approver: string | null
    timeout_hours: number | null
    on_timeout: string | null
    optional: boolean | null
  }>
  candidate_count?: number
}

/** serialize_approval_request (_base.py). */
export type SolicitudDeAprobacion = {
  id: string
  workflow_id: string | null
  entity_type: string
  entity_id: string
  entity_summary: string | null
  requested_by: string | null
  requester_name: string | null
  current_step: number
  status: string
  final_decision: string | null
  final_note: string | null
  completed_at: string | null
  created_at: string | null
  decisions: Array<{
    step_order: number
    approver_id: string | null
    approver_name: string | null
    decision: string
    note: string | null
    attachment_url: string | null
    decided_at: string | null
  }>
  escalated: boolean
  auto_approved: boolean
  rejected: boolean
}

/** GET /approvals/requests/pending-my-action: la solicitud + el paso que me toca. */
export type SolicitudPendienteDeMi = SolicitudDeAprobacion & { step_name: string; step_order: number }

/** get_approval_stats (analytics.py). */
export type EstadisticasDeAprobacion = {
  total: number
  pending: number
  approved: number
  rejected: number
  by_entity_type: Record<string, number>
}

/** _build_bottleneck_item (analytics.py). */
export type CuelloDeBotella = {
  workflow_id: string
  workflow_name: string
  step_order: number
  step_name: string
  step_timeout_hours: number | null
  decisions_total: number
  approved_count: number
  rejected_count: number
  delegated_count: number
  rejection_rate_pct: number
  avg_decision_time_hours: number
  pending_count: number
  avg_pending_age_hours: number
  sla_risk_pct: number
  bottleneck_score: number
}

/** get_workflow_bottlenecks (analytics.py). */
export type CuellosDeBotella = {
  since: string
  days: number
  workflow_id: string | null
  count: number
  items: CuelloDeBotella[]
  top_bottlenecks: CuelloDeBotella[]
  summary: { steps_analyzed: number; critical_steps: number; pending_total: number; avg_decision_time_hours: number }
  top_workflows: Array<{ workflow_id: string; workflow_name: string; steps_analyzed: number; avg_bottleneck_score: number; max_sla_risk_pct: number; pending_total: number }>
  weekly_trend: Array<{ week: string; decisions: number; rejected: number; rejection_rate_pct: number }>
  recommendations: Array<{ priority: string; title: string; action: string; why: string }>
}

/** _build_approver_load_item (analytics.py). `rejection_rate_pct` ya es porcentaje (0-100). */
export type CargaDeAprobador = {
  user_id: string
  /** Nombre, o el id si el usuario ya no existe. */
  user_name: string
  user_email: string | null
  decisions_total: number
  approved_count: number
  rejected_count: number
  rejection_rate_pct: number
  avg_response_hours: number
  pending_count: number
  avg_pending_age_hours: number
  load_score: number
}

/** get_approver_load (analytics.py). */
export type CargaDeAprobadores = {
  days: number
  since: string
  count: number
  items: CargaDeAprobador[]
  overloaded_approvers: CargaDeAprobador[]
}

/** serialize_approval_group (groups.py): member_ids ya llega como lista. */
export type GrupoDeAprobadores = {
  id: string
  name: string
  description: string | null
  member_ids: string[]
  created_by: string | null
  created_at: string | null
}

/** GET/PUT /approvals/out-of-office (approvals.py, ausencias.fijar_ausencia). */
export type FueraDeLaOficina = { delegate_id: string | null; away_from: string | null; away_until: string | null }

/** Respuesta de borrado de /approvals. */
export type ConfirmacionDeAprobaciones = { ok: boolean }

// ── Evaluaciones de desempeño (app/api/v1/endpoints/performance.py) ──────────

/** Respuestas por `question_key`: puntuación, sí/no o texto. */
export type RespuestasDeEvaluacion = Record<string, string | number | null>

/** GET /performance/cycles (lista plana, total en X-Total-Count). */
export type CicloDeEvaluacion = {
  id: string
  name: string
  status: string
  start_date: string | null
  end_date: string | null
  total_reviews: number
  pending: number
  submitted: number
}

/** serialize_review (performance_service/evaluaciones.py). */
export type EvaluacionDeDesempeno = {
  id: string
  cycle_id: string
  reviewee_id: string
  reviewee_name: string | null
  reviewer_id: string
  reviewer_name: string | null
  review_type: string
  status: string
  answers: RespuestasDeEvaluacion
  score_quality: number | null
  score_delivery: number | null
  score_teamwork: number | null
  score_leadership: number | null
  score_innovation: number | null
  score_overall: number | null
  strengths: string | null
  improvements: string | null
  goals_next: string | null
  submitted_at: string | null
}

/** serialize_question (performance_service/ciclos_y_preguntas.py). */
export type PreguntaDeEvaluacion = {
  id: string
  cycle_id: string
  key: string
  label: string
  hint: string | null
  kind: string
  order: number | null
  required: boolean
  scale_min: number | null
  scale_max: number | null
}

/** GET /performance/cycles/{id}/eligible-reviewers/{reviewee}/{type}. */
export type EvaluadoresElegibles = {
  review_type: string
  reviewee_id: string
  reason_blocked: string | null
  users: Array<{ id: string; full_name: string; email: string; department: string | null; team: string | null; job_title: string | null }>
}

/** serialize_campaign (performance_service/campanas_360.py); el progreso va con include_progress (por defecto). */
export type Campana360 = {
  id: string
  cycle_id: string
  subject_id: string
  subject_name: string | null
  status: string
  anonymity_threshold: number
  created_at: string | null
  closed_at: string | null
  total_reviewers?: number
  submitted?: number
  pending?: number
  by_type?: Record<string, number>
}

/** aggregate_campaign (campanas_360.py). */
export type PanelDeCampana360 = {
  campaign: Campana360
  questions: PreguntaDeEvaluacion[]
  groups: Record<string, {
    count: number
    anonymized: boolean
    ratings_by_question: Record<string, { avg: number; min: number; max: number; n: number }>
    text_by_question: Record<string, Array<{ text: unknown }>>
  }>
  comparison: Record<string, Record<string, number | null>>
  anonymity_threshold: number
  total_submitted: number
  total_assigned: number
}

/** history_360_for_subject (campanas_360.py). */
export type Historico360 = {
  subject_id: string
  subject_name: string | null
  series: Array<{
    campaign_id: string
    cycle_id: string
    cycle_name: string | null
    created_at: string | null
    status: string
    ratings: Record<string, { label: string; scale_max: number; self: number | null; others: number | null }>
  }>
}

/** perf_reminder_service.org_perf_kpis. */
export type KpisDeDesempeno = {
  total_cycles: number
  active_cycles: number
  closed_cycles: number
  draft_cycles: number
  total_reviews_active: number
  submitted_reviews_active: number
  pending_reviews_active: number
  global_completion_rate: number
  stalled_cycles: Array<{ cycle_id: string; cycle_name: string; completion_rate: number; end_date: string | null; overdue: boolean }>
  avg_days_to_submit_closed: number | null
}

/** perf_reminder_service.cycle_kpis. */
export type KpisDeCiclo = {
  cycle_id: string
  cycle_name: string
  status: string
  total_reviews: number
  submitted: number
  pending: number
  completion_rate: number
  avg_days_to_submit: number | null
  by_type: Record<string, { total: number; submitted: number }>
  days_to_close: number | null
  end_date: string | null
  top_stalled_reviewers: Array<{ user_id: string; user_name: string; pending: number }>
}

/** perf_reminder_service.send_pending_review_reminders. */
export type EjecucionDeRecordatorios = { cycles_processed: number; reminders_sent: number; reminders_skipped_dedup: number; ran_at: string }

/** dev_plan_service.serialize_goal. */
export type ObjetivoDeDesarrollo = {
  id: string
  plan_id: string
  title: string
  description: string | null
  status: string
  due_date: string | null
  progress: number | null
  order: number | null
  completed_at: string | null
}

/** dev_plan_service.serialize_plan. */
export type PlanDeDesarrollo = {
  id: string
  subject_id: string
  subject_name: string | null
  campaign_id: string | null
  cycle_id: string | null
  cycle_name: string | null
  title: string
  summary: string | null
  status: string
  target_date: string | null
  next_review_at: string | null
  created_at: string | null
  goals: ObjetivoDeDesarrollo[]
  progress_pct: number
}

// ── Tablero de tareas ────────────────────────────────────────────────────────

/** custom_fields_service.serialize_field. `options` ya llega como lista. */
export type CampoPersonalizado = {
  id: string
  project_id: string
  name: string
  field_key: string
  field_type: string
  options: string[]
  is_required: boolean
  show_in_list: boolean
  sort_order: number | null
  created_at: string | null
}

/** custom_fields_service.get_task_custom_values. */
export type ValorDeCampoPersonalizado = { field_id: string; field_key: string; field_name: string; field_type: string; value: string | null }

/** custom_fields_service.save_task_custom_values. */
export type CamposPersonalizadosGuardados = { saved: number }

/** custom_fields_service.serialize_state. */
export type EstadoDelFlujoDeProyecto = {
  id: string
  project_id: string
  name: string
  value: string
  color: string | null
  icon: string | null
  is_initial: boolean
  is_final: boolean
  sort_order: number | null
  transitions_from: Array<{ id: string; to_state_id: string; to_state_name: string | null; label: string | null; required_role: string | null; requires_comment: boolean }>
}

/** custom_fields_service.get_workflow (GET /project-workflows/{id}). */
export type FlujoDelProyecto = { project_id: string; states: EstadoDelFlujoDeProyecto[] }

/** issue_type_service.serialize_issue_type (solo activos). */
export type TipoDeIncidencia = {
  id: string
  project_id: string
  name: string
  value: string
  icon: string | null
  color: string | null
  description: string | null
  is_subtask: boolean
  sort_order: number | null
  field_keys: string[]
  created_at: string | null
}

/** cmdb_service.get_kanban_config. Sin configurar: `configured: false`, sin id y sin columnas. */
export type ConfigDelTablero = {
  id?: string
  project_id: string
  swimlane_by: string
  show_subtasks: boolean
  card_fields: string[]
  configured: boolean
  columns: Array<{ id: string; status: string; label: string | null; wip_limit: number | null; color: string | null; sort_order: number }>
}

/** cmdb_service.upsert_kanban_config. */
export type ConfigDelTableroGuardada = { id: string; project_id: string; swimlane_by: string }

/** cmdb_service.add_kanban_column / update_kanban_column. */
export type ColumnaDelTablero = { id: string; status: string; wip_limit: number | null }

/** SemanticAssigner._result + enrich_suggestion (POST /semantic/suggest/task). */
export type SugerenciaDeAsignacion = {
  suggested_user_id: string | null
  suggested_user_name?: string | null
  confidence: number
  engine_mode: string
  top_scores?: Record<string, number>
  top_candidates?: Record<string, { score: number; name: string }>
  needs_review: boolean
  reasoning: string
  sem_score?: number
}

/** SemanticAssigner.estimate_effort (POST /semantic/estimate/effort). */
export type EstimacionDeEsfuerzo = { complexity: string; base_hours: number; role_hint: string; confidence: number }
