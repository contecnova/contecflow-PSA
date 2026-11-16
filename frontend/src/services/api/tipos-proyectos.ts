/**
 * Respuestas de la ejecución de proyectos: sprints, épicas, dependencias,
 * control de cambios, UAT, entregables, riesgos, flujo y tipos del tablero,
 * plantillas de proyecto, OKRs y Git. Comprobadas contra el serializador del
 * backend que cita cada JSDoc.
 *
 * Son `type` (no `interface`) para que se puedan asignar a tipos con índice
 * `[k: string]: unknown` sin cast.
 *
 * Las listas llegan ya desenvueltas por el interceptor de _core.ts y los
 * `APIResponse {data, meta}` también: `res.data` es el payload.
 */
import type { Epic, Risk } from './tipos'
import type { ConfirmacionOk, Entregable } from './tipos-alm'

/** Borrados que solo confirman (`{deleted: true}`). */
export type Borrado = { deleted: boolean }

// ── Sprints (app/services/sprint_service.py, endpoints/sprints.py) ──────────

/** sprint_service.serialize_task (backlog y tareas de un sprint). */
export type TareaDeSprint = {
  id: string
  code: string | null
  title: string
  status: string
  priority: string
  story_points: number | null
  estimated_hours: number | null
  assignee_id: string | null
  assignee_name: string | null
  due_date: string | null
  tags: string | null
  blocked_reason: string | null
}

/** sprint_service.serialize_sprint. `tasks` solo en la lista del proyecto y al actualizar. */
export type SprintDelProyecto = {
  id: string
  number: number
  name: string
  goal: string | null
  status: 'planning' | 'active' | 'completed' | 'cancelled'
  start_date: string | null
  end_date: string | null
  duration_days: number
  /** Solo en el sprint activo. */
  days_remaining: number | null
  planned_points: number
  completed_points: number
  velocity: number | null
  went_well: string | null
  to_improve: string | null
  action_items: string | null
  created_at: string | null
  task_count: number
  tasks?: TareaDeSprint[]
}

/** POST /sprints/{p}/sprints/{s}/start. */
export type SprintIniciado = { ok: boolean; sprint: SprintDelProyecto }

/** psa_flows.close_sprint_flow. */
export type SprintCerrado = { ok: boolean; completed_points: number; velocity: number | null; incomplete_tasks: number }

/** POST /sprints/{p}/sprints/{s}/tasks. */
export type TareasAnadidasAlSprint = { ok: boolean; added: number }

/** sprint_service.compute_sprint_burndown (`date` es MM-DD). */
export type PuntoDeBurndown = { date: string; remaining: number; ideal: number }
export type Burndown = { burndown: PuntoDeBurndown[] }

/** GET /sprints/{p}/sprints/{s}/burnup (`date` es MM-DD). Sin fechas: sin `target`. */
export type PuntoDeBurnup = { date: string; scope: number; completed: number }
export type Burnup = { burnup: PuntoDeBurnup[]; sprint: SprintDelProyecto; target?: number }

/** GET /sprints/{p}/velocity. */
export type Velocidad = {
  sprints: Array<{ sprint: string; name: string; planned: number; completed: number; velocity: number }>
  avg_velocity: number
}

/** raci_service._metricas_de_sprint. */
export type MetricasDeRetro = {
  total_tasks: number
  completed: number
  blocked: number
  carryover: number
  added_mid_sprint: number
  completion_rate_pct: number
  planned_hours: number
  completed_hours: number
  velocity_ratio_pct: number
}

/** raci_service.get_sprint_retrospective. */
export type Retrospectiva = {
  sprint_id: string
  sprint_name: string
  sprint_status: string | null
  start_date: string | null
  end_date: string | null
  computed_insights: {
    metrics: MetricasDeRetro
    went_well: string[]
    improve: string[]
    actions: Array<{ text: string; owner_id: string | null }>
    risks: string[]
  }
  saved_notes: {
    id: string
    manual_notes: string | null
    action_items: Array<{ text: string; owner_id?: string | null }>
    updated_at: string | null
  } | null
}

/** raci_service.save_sprint_retrospective. */
export type RetrospectivaGuardada = { id: string; sprint_id: string; updated_at: string }

// ── Plan de sprint asistido (cmdb_service, /cmdb/sprint-plans) ──────────────

export type EstadoDePlanDeSprint = 'draft' | 'accepted' | 'rejected'

/** cmdb_service.list_sprint_plans. */
export type PlanDeSprint = {
  id: string
  name: string
  status: EstadoDePlanDeSprint
  total_points: number
  team_capacity: number
  task_count: number
  created_at: string | null
}

/** cmdb_service.generate_sprint_plan (no trae `created_at`). */
export type PlanDeSprintGenerado = Omit<PlanDeSprint, 'created_at'> & {
  utilization_pct: number
  ai_reasoning: string
  unestimated_count: number
  tasks: Array<{ task_id: string; title: string; story_points: number; priority: string | null; unestimated: boolean }>
}

/** cmdb_service.update_sprint_plan_status. */
export type PlanDeSprintActualizado = { id: string; status: EstadoDePlanDeSprint; tareas_anadidas: number }

// ── Épicas (app/services/epics_service.py) ───────────────────────────────────

/** epics_service.serialize_epic (lista, alta y edición). `status` y `priority` son texto
 *  libre en la tabla; la interfaz usa open/in_progress/done/cancelled y low…critical. */
export type EpicaSerializada = Epic & {
  project_id: string
  title: string
  description: string | null
  color: string | null
  status: string
  priority: string
  start_date: string | null
  end_date: string | null
  sort_order: number | null
  task_count: number
  created_at: string | null
  updated_at: string | null
}

/** epics_service.get_epic_record: añade las tareas enlazadas y los ids de las épicas de las que depende. */
export type EpicaDetalle = EpicaSerializada & {
  tasks: Array<{ id: string; title: string; status: string; story_points: number | null; assigned_to_user_id: string | null }>
  dependencies: string[]
}

/** POST /epics/{id}/tasks/{task_id}. */
export type TareaEnlazada = { linked: boolean }

/** get_roadmap_data. */
export type EpicaDelRoadmap = EpicaSerializada & {
  done_tasks: number
  total_tasks: number
  progress: number
  dependencies: string[]
}
export type RoadmapDeEpicas = { project_id: string; epics: EpicaDelRoadmap[] }

/** get_cfd_data: cada punto lleva `date` y una clave por estado con su recuento. */
export type FlujoAcumulado = {
  project_id: string
  statuses: string[]
  data: Array<{ date: string; t?: string; clave?: string } & Record<string, number | string>>
  periodo?: Record<string, unknown>
}

/** take_cfd_snapshot. */
export type FotoDeFlujoAcumulado = { date: string; states: number }

/** execute_nql_search: la forma de `results` depende de `entity_type`. */
export type ResultadoNqlTarea = { id: string; title: string; status: string; priority: string; project_id: string }
export type ResultadoNqlProyecto = { id: string; name: string; status: string }
export type BusquedaNql = {
  entity_type: 'task' | 'project' | 'epic'
  count: number
  results: Array<ResultadoNqlTarea | ResultadoNqlProyecto | EpicaSerializada>
}

// ── Dependencias ─────────────────────────────────────────────────────────────

/** issue_type_service.serialize_epic_dep (/epic-dependencies). */
export type DependenciaDeEpica = {
  id: string
  epic_id: string
  epic_title: string | null
  depends_on_id: string
  depends_on_title: string | null
  /** models/issue_types.py EpicDepType. */
  dep_type: 'finish_to_start' | 'start_to_start' | 'finish_to_finish' | 'relates_to'
  lag_days: number
}

/** task_service.list_task_dependencies / create_task_dependency (/tasks/dependencies, las del Gantt). */
export type DependenciaDeTarea = {
  id: string
  predecessor_id: string
  successor_id: string
  dependency_type: 'FS' | 'SS' | 'FF' | 'SF'
  lag_days: number | null
  /** Rev. 173: `schedule` planifica; el resto son vínculos informativos. */
  link_type?: 'schedule' | 'relates_to' | 'duplicates' | 'cloned_from'
  note?: string | null
}

/** Una entrada de POST /tasks/bulk-dates (`{updates: [...]}`, _aplicar_fechas_a_tarea). */
export type CambioDeFechas = { id: string; start_date?: string | null; due_date?: string | null }

/** task_service.bulk_update_dates_record: las que fallan no paran al resto. */
export type FechasMasivas = { updated: number; errors: Array<{ id: string; reason: string }> }

// ── Control de cambios (endpoints/changes.py ChangeRequestOut) ───────────────

export type SolicitudDeCambio = {
  id: string
  code: string
  project_id: string
  title: string
  description: string
  justification: string | null
  impact: string
  impact_label: string
  impact_color: string
  cost_impact: number | null
  schedule_impact_days: number | null
  scope_impact: string | null
  status: string
  status_label: string
  status_color: string
  requested_by: string | null
  requester_name: string | null
  reviewed_by: string | null
  approved_by: string | null
  approver_name: string | null
  submitted_at: string | null
  approved_at: string | null
  implemented_at: string | null
  resolution_notes: string | null
  created_at: string | null
  /** Solo en GET /changes/all/pending. */
  project_name: string | null
  project_code: string | null
}

/** GET /changes/{project_id}. */
export type CambiosDelProyecto = {
  change_requests: SolicitudDeCambio[]
  summary: { total: number; pending: number; approved: number; total_cost_impact: number; total_schedule_impact: number }
}

/** submit / review: mensaje y estado nuevo. */
export type TransicionDeCambio = { message: string; status: string }

/** implement: solo el mensaje. */
export type CambioImplementado = { message: string }

// ── UAT (app/services/raci_service.py) ───────────────────────────────────────

/** raci_service.serialize_user. */
export type UsuarioResumido = {
  id: string
  full_name: string
  role: string
  department: string | null
  job_title: string | null
  avatar_initials: string
}

/** raci_service.serialize_uat_case. */
export type CasoUat = {
  id: string
  project_id: string
  task_id: string | null
  title: string
  description: string | null
  expected_result: string | null
  actual_result: string | null
  status: 'pending' | 'passed' | 'failed' | 'blocked' | 'skipped'
  priority: string
  assigned_to_id: string | null
  assigned_to: UsuarioResumido | null
  task_title: string | null
  notes: string | null
  executed_at: string | null
  created_at: string | null
  updated_at: string | null
}

/** raci_service.list_uat_cases. */
export type CasosUat = {
  cases: CasoUat[]
  stats: { total: number; pending: number; passed: number; failed: number; blocked: number }
}

/** raci_service.export_uat_report (texto Markdown). */
export type InformeUat = { project_name: string; text: string; cases_count: number }

// ── Entregables y riesgos de la cartera ──────────────────────────────────────

/** GET /deliverables/all/overview: añade el proyecto ("—" si no hay). */
export type EntregableDeLaCartera = Entregable & { project_name: string; project_code: string }

/** risk_scoring.risk_level. */
export type NivelDeRiesgo = 'low' | 'medium' | 'high' | 'critical'

/** risk_service.serialize_risk (alta, edición y cartera; los enums de models/pipeline.py). */
export type RiesgoSerializado = Risk & {
  code: string
  project_id: string
  title: string
  category_label: string | null
  probability: 'very_low' | 'low' | 'medium' | 'high' | 'very_high'
  probability_label: string
  impact: 'negligible' | 'minor' | 'moderate' | 'major' | 'critical'
  impact_label: string
  risk_score: number
  risk_level: NivelDeRiesgo
  status: 'identified' | 'analyzing' | 'mitigating' | 'monitoring' | 'closed' | 'materialized'
  status_label: string
  mitigation_plan: string | null
  contingency_plan: string | null
  response_type: string | null
  owner_name: string | null
  review_date: string | null
  closed_date: string | null
  identified_date: string | null
  schedule_impact_days: number | null
  notes: string | null
}

/** GET /risks/all/portfolio (50 abiertos con más puntuación): añade el proyecto ("—" si no hay). */
export type RiesgoAbiertoDeLaCartera = RiesgoSerializado & { project_name: string; project_code: string }

// ── Flujo, campos y tipos del tablero (custom_fields_service, issue_type_service) ──

/** custom_fields_service.create_transition. */
export type TransicionDelFlujo = {
  id: string
  from_state_id: string
  to_state_id: string
  label: string | null
  required_role: string | null
  requires_comment: boolean
}

/** init_default_workflow / reset_workflow. */
export type FlujoInicializado = { initialized: boolean; states: number; transitions: number }

/** issue_type_service.init_issue_types. */
export type TiposDeIncidenciaInicializados = { initialized: boolean; types: string[] }

// ── Plantillas de proyecto (schemas/billing_reports.py) ──────────────────────

/** ProjectTemplateOut. */
export type PlantillaDeProyecto = {
  id: string
  name: string
  description: string | null
  project_type: string | null
  estimated_weeks: number | null
  estimated_hours: number | null
  phases: Array<{
    id: string
    name: string
    order: number
    estimated_weeks: number | null
    tasks: Array<{ id: string; title: string; estimated_hours: number | null; skill_required: string | null }>
  }>
  risk_count: number
  deliverable_count: number
  /** Rev. 173 (plantillas unificadas). */
  dependency_count?: number
  role_count?: number
  document_count?: number
}

/** TemplateCreateOut. */
export type PlantillaCreada = { ok: boolean; id: string }

/** TemplateInstantiateOut. */
export type ProyectoDesdePlantilla = {
  ok: boolean
  project_id: string
  project_code: string
  project_name: string
  phases_created: number
  tasks_created: number
}

// ── OKRs (app/services/okr_service.py) ───────────────────────────────────────

/** models/okrs.py OKRStatus / OKRPeriod / KRType. */
export type EstadoDeObjetivo = 'draft' | 'active' | 'completed' | 'cancelled'
export type PeriodoDeObjetivo = 'Q1' | 'Q2' | 'Q3' | 'Q4' | 'H1' | 'H2' | 'annual'
export type TipoDeResultadoClave = 'percentage' | 'number' | 'boolean' | 'currency'

/** okr_service.serialize_kr. */
export type ResultadoClave = {
  id: string
  objective_id: string
  title: string
  kr_type: TipoDeResultadoClave
  target_value: number | null
  current_value: number | null
  unit: string | null
  progress: number
  owner_id: string | null
  owner_name: string | null
  due_date: string | null
  notes: string | null
}

/** okr_service.serialize_objective (solo KRs activos). */
export type Objetivo = {
  id: string
  title: string
  description: string | null
  owner_id: string | null
  owner_name: string | null
  team_id: string | null
  project_id: string | null
  period: PeriodoDeObjetivo
  year: number
  status: EstadoDeObjetivo
  progress: number
  key_results: ResultadoClave[]
  created_at: string | null
}

export type ObjetivoCreado = { id: string; title: string }
export type ObjetivoBorrado = ConfirmacionOk & { kr_count: number }
export type CheckinDeResultadoClave = { progress: number; current_value: number | null }

// ── Git (endpoints/git_integration.py, app/services/git_service.py) ──────────

/** models/git_integration.py PRStatus / DeployStatus / GitProvider. */
export type EstadoDePullRequest = 'open' | 'draft' | 'merged' | 'closed'
export type EstadoDeDespliegue = 'pending' | 'running' | 'success' | 'failure' | 'cancelled'
export type ProveedorGit = 'github' | 'gitlab' | 'gitea'

/** PROut. Los ids son UUID en la tabla aunque el esquema declare `int` (ver informe). */
export type PullRequest = {
  id: string
  provider: ProveedorGit
  repo_full_name: string
  pr_number: number
  pr_title: string | null
  pr_url: string | null
  author_login: string | null
  source_branch: string | null
  target_branch: string | null
  status: EstadoDePullRequest
  task_id: string | null
  project_id: string | null
  merged_at: string | null
  created_at: string
}

/** DeployOut. */
export type Despliegue = {
  id: string
  provider: ProveedorGit
  repo_full_name: string | null
  environment: string | null
  deploy_url: string | null
  status: EstadoDeDespliegue
  sha: string | null
  task_id: string | null
  deployed_at: string | null
  created_at: string
}

/** git_service.direcciones_de_la_empresa: sin empresa, solo `slug: null`. */
export type DireccionDeWebhookGit = { ruta: string; secreto: boolean }
export type WebhooksGit = { slug: string | null; github?: DireccionDeWebhookGit; gitlab?: DireccionDeWebhookGit }
