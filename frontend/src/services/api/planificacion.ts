/**
 * services/api/planificacion.ts — Proyectos: planificador, hub y vistas (rev. 173, 16-11-2026).
 *
 * Planificador (camino crítico con calendarios), líneas base, nivelación, valor
 * ganado con curva S, vistas guardadas, cartera (intake → fases → proyecto),
 * plantillas unificadas y la IA de proyectos. El interceptor de `_core` ya
 * desenvuelve `{ data, meta }` (y deja la lista en `r.data` para `{ items }`).
 */
import api from './_core'
import type { SugerenciaDeAsignacion } from './tipos-rendimiento'

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

// ── Planificador ─────────────────────────────────────────────────────────────

export type TipoDeDependencia = 'FS' | 'SS' | 'FF' | 'SF'
export type TipoDeVinculo = 'schedule' | 'relates_to' | 'duplicates' | 'cloned_from'
export type Restriccion = 'snet' | 'mso' | 'fnlt' | 'mfo'

export interface NodoDelPlan {
  id: string; code: string; title: string; status: string; assignee_id: string | null
  duration_days: number; start_date: string | null; due_date: string | null
  early_start: string; early_finish: string; late_start: string; late_finish: string
  total_float: number; free_float: number; is_critical: boolean; is_near_critical: boolean
  constraint_type: Restriccion | null; constraint_date: string | null
  baseline_start: string | null; baseline_end: string | null; in_cycle: boolean
}
export interface PlanDelProyecto {
  project_id: string; project_start: string | null; project_finish: string | null
  deadline: string | null; finish_vs_deadline_days: number | null; project_duration_days: number
  critical_path: string[]; cycle: string[]; nodes: NodoDelPlan[]
  links: { predecessor_id: string; successor_id: string; dependency_type: TipoDeDependencia; lag_days: number }[]
  calendar: { workdays: number[]; hours_per_day: number; holidays: string[] } | null
}
export interface Movimiento {
  task_id: string; code: string; title: string
  old_start: string | null; old_due: string | null; new_start: string; new_due: string
  assignee_id?: string; delay_days?: number; max_delay_days?: number
}
export interface Sobrecarga { user_id: string; date: string; hours: number; capacity: number }
export interface Nivelacion {
  project_id: string; moves: Movimiento[]
  overallocations_before: Sobrecarga[]; overallocations_after: Sobrecarga[]
  overallocated_hours_before: number; overallocated_hours_after: number
  skipped_without_estimate: number; applied?: Movimiento[]; total_applied?: number
}
export interface Dependencia {
  id: string; predecessor_id: string; successor_id: string
  dependency_type: TipoDeDependencia; lag_days: number; link_type: TipoDeVinculo; note: string | null
}

// ── Líneas base ──────────────────────────────────────────────────────────────

export interface LineaBase {
  id: string; name: string; description: string | null; baseline_date: string
  total_tasks: number; completed_tasks: number; total_hours: number; budget_at_freeze: number | null
  is_initial: boolean; is_current: boolean; created_at: string | null
}
export interface DesvioDeTarea {
  task_id: string; title?: string | null; delta?: 'new_task' | 'removed'
  baseline_start?: string | null; baseline_end?: string | null
  current_start?: string | null; current_end?: string | null
  start_slip_days?: number | null; slip_days?: number | null
  baseline_hours?: number | null; current_hours?: number | null
}
export interface Comparacion {
  baseline_id: string; baseline_name: string; baseline_date: string
  against: { id: string; name: string; baseline_date: string } | null
  summary: { tasks_compared: number; tasks_slipped: number; tasks_ahead: number; avg_slip_days: number
    max_slip_days: number; tasks_removed: number; tasks_added: number; baseline_hours: number; current_hours: number }
  task_deltas: DesvioDeTarea[]
}

// ── Valor ganado ─────────────────────────────────────────────────────────────

export interface ValorGanado {
  bac: number; pv: number | null; ev: number; ac: number; cpi: number | null; spi: number | null
  cv: number; sv: number | null; eac: number; etc: number; vac: number; tcpi: number | null
  pct_complete: number; pct_planned: number | null; pv_source: 'baseline' | 'current_plan'
  baseline_id: string | null; has_schedule: boolean
}
export interface CurvaS {
  project_id: string; today: ValorGanado
  history: { date: string; pv: number | null; ev: number | null; ac: number | null; cpi: number | null; spi: number | null }[]
  planned: { date: string; pv: number }[]
}

// ── Vistas guardadas ─────────────────────────────────────────────────────────

export type TipoDeVista = 'kanban' | 'list' | 'table' | 'timeline' | 'calendar' | 'workload'
export interface VistaGuardada {
  id: string; name: string; entity_type: string; view_type: TipoDeVista | null; project_id: string | null
  config: Record<string, unknown>; nql_query: string; is_shared: boolean; created_by: string | null
}

export interface CargaPorPersona {
  from: string; weeks: number
  people: { user_id: string; name: string | null
    weeks: { week: string; capacity: number; hours: number; project_hours: number | null; pct: number | null; state: 'over' | 'under' | 'ok' }[] }[]
}

export const planificacionApi = {
  carga: (params: { project_id?: string; from?: string; weeks?: number }) => D<CargaPorPersona>(api.get('/planning/workload', { params })),
  plan: (projectId: string) => D<PlanDelProyecto>(api.get(`/planning/projects/${projectId}/schedule`)),
  replanificar: (projectId: string) => D<{ moved: Movimiento[]; total_moved: number }>(api.post(`/planning/projects/${projectId}/schedule/apply`)),
  nivelacion: (projectId: string) => D<Nivelacion>(api.get(`/planning/projects/${projectId}/leveling`)),
  aplicarNivelacion: (projectId: string, taskIds?: string[]) => D<Nivelacion>(api.post(`/planning/projects/${projectId}/leveling/apply`, { task_ids: taskIds ?? null })),
  valorGanado: (projectId: string) => D<ValorGanado>(api.get(`/planning/projects/${projectId}/evm`)),
  curvaS: (projectId: string) => D<CurvaS>(api.get(`/planning/projects/${projectId}/evm/curve`)),
  guardarPuntoDeCurva: (projectId: string) => D<{ saved: boolean }>(api.post(`/planning/projects/${projectId}/evm/snapshot`)),
  vistas: (params: { entity_type?: string; project_id?: string }) => D<VistaGuardada[]>(api.get('/planning/views', { params })),
  crearVista: (body: Partial<VistaGuardada>) => D<VistaGuardada>(api.post('/planning/views', body)),
  editarVista: (id: string, body: Partial<VistaGuardada>) => D<VistaGuardada>(api.patch(`/planning/views/${id}`, body)),
  borrarVista: (id: string) => D<{ deleted: boolean }>(api.delete(`/planning/views/${id}`)),
}

export const dependenciasApi = {
  listar: (projectId: string) => D<Dependencia[]>(api.get(`/tasks/dependencies/${projectId}`)),
  crear: (body: { predecessor_id: string; successor_id: string; dependency_type: TipoDeDependencia | TipoDeVinculo; lag_days?: number; link_type?: TipoDeVinculo; note?: string }) =>
    D<Dependencia>(api.post('/tasks/dependencies', body)),
  editar: (id: string, body: Partial<Pick<Dependencia, 'dependency_type' | 'lag_days' | 'link_type' | 'note'>>) => D<Dependencia>(api.patch(`/tasks/dependencies/${id}`, body)),
  borrar: (id: string) => D<{ ok: boolean }>(api.delete(`/tasks/dependencies/${id}`)),
}

export const lineasBaseApi = {
  listar: (projectId: string) => D<LineaBase[]>(api.get(`/projects/${projectId}/baselines`)),
  crear: (projectId: string, body: { name: string; description?: string; is_initial?: boolean; make_current?: boolean }) =>
    D<LineaBase>(api.post(`/projects/${projectId}/baselines`, body)),
  hacerVigente: (projectId: string, id: string) => D<LineaBase>(api.post(`/projects/${projectId}/baselines/${id}/make-current`)),
  comparar: (projectId: string, id: string, against?: string) =>
    D<Comparacion>(api.get(`/projects/${projectId}/baselines/${id}/compare`, { params: against ? { against } : {} })),
  borrar: (projectId: string, id: string) => api.delete(`/projects/${projectId}/baselines/${id}`),
}

// ── Cartera ──────────────────────────────────────────────────────────────────

export interface Criterio { id: string; name: string; description: string | null; weight: number; inverse: boolean; sort_order: number; is_active: boolean }
export interface Fase { id: string; name: string; description: string | null; sort_order: number; workflow_id: string | null; min_score: number | null; is_active: boolean }
export type EstadoDePropuesta = 'draft' | 'in_review' | 'in_progress' | 'approved' | 'rejected' | 'converted'
export interface Propuesta {
  id: string; title: string; description: string | null; portfolio_id: string | null
  requested_by: string | null; sponsor_id: string | null; client_id: string | null
  estimated_budget: number | null; estimated_hours: number | null; wanted_start: string | null; wanted_end: string | null
  roles_needed: { role: string; hours: number }[]; scores: Record<string, number>; score: number | null
  status: EstadoDePropuesta; gate_index: number; gates_total: number; current_gate: Fase | null
  approval_status: string | null; decision_note: string | null; project_id: string | null; template_id: string | null
}
export interface Capacidad {
  proposal_id: string; from: string; to: string; fits: boolean
  roles: { role: string; needed_hours: number; people: number; capacity_hours: number; booked_hours: number; free_hours: number; gap_hours: number }[]
}

export const carteraApi = {
  criterios: () => D<Criterio[]>(api.get('/portfolio-intake/criteria')),
  crearCriterio: (b: Partial<Criterio>) => D<Criterio>(api.post('/portfolio-intake/criteria', b)),
  editarCriterio: (id: string, b: Partial<Criterio>) => D<Criterio>(api.patch(`/portfolio-intake/criteria/${id}`, b)),
  fases: () => D<Fase[]>(api.get('/portfolio-intake/gates')),
  crearFase: (b: Partial<Fase>) => D<Fase>(api.post('/portfolio-intake/gates', b)),
  editarFase: (id: string, b: Partial<Fase>) => D<Fase>(api.patch(`/portfolio-intake/gates/${id}`, b)),
  propuestas: (status?: string) => D<Propuesta[]>(api.get('/portfolio-intake/proposals', { params: status ? { status } : {} })),
  crearPropuesta: (b: Partial<Propuesta>) => D<Propuesta>(api.post('/portfolio-intake/proposals', b)),
  editarPropuesta: (id: string, b: Partial<Propuesta>) => D<Propuesta>(api.patch(`/portfolio-intake/proposals/${id}`, b)),
  enviar: (id: string) => D<Propuesta>(api.post(`/portfolio-intake/proposals/${id}/submit`)),
  decidir: (id: string, approved: boolean, note?: string) => D<Propuesta>(api.post(`/portfolio-intake/proposals/${id}/decision`, { approved, note })),
  convertir: (id: string, b: { name?: string; pm_id?: string }) => D<Propuesta>(api.post(`/portfolio-intake/proposals/${id}/convert`, b)),
  capacidad: (id: string) => D<Capacidad>(api.get(`/portfolio-intake/proposals/${id}/capacity`)),
}

// ── Plantillas (API canónica) ────────────────────────────────────────────────

export interface PlantillaResumen {
  id: string; name: string; description: string | null; project_type: string | null
  estimated_weeks: number | null; estimated_hours: number | null
  phase_count: number; task_count: number; dependency_count: number; role_count: number
  document_count: number; risk_count: number; deliverable_count: number
}
export const plantillasApi = {
  listar: () => D<PlantillaResumen[]>(api.get('/templates')),
  desdeProyecto: (projectId: string, b: { name?: string; description?: string }) =>
    D<{ template_id: string; name: string; tasks_exported: number; dependencies_exported: number }>(api.post(`/templates/from-project/${projectId}`, b)),
  aplicar: (templateId: string, projectId: string, startDate?: string) =>
    D<{ tasks_created: number; dependencies_created: number }>(api.post(`/templates/${templateId}/apply/${projectId}`, { start_date: startDate })),
  borrar: (templateId: string) => D<{ ok: boolean }>(api.delete(`/templates/${templateId}`)),
}

// ── IA de proyectos ──────────────────────────────────────────────────────────

export interface EstimacionIa { task_id: string; task_title: string; estimated_hours: number; confidence_pct: number; reasoning: string; similar_count: number; current_estimate: number | null }
export interface SaludDelProyecto {
  project_id: string; project_name: string
  current: { score: number; schedule_score: number; budget_score: number; quality_score: number; velocity_score: number; client_score: number; traffic_light: 'green' | 'yellow' | 'red'; overdue_tasks: number; total_tasks: number; open_bugs: number }
  history: { score: number; traffic_light: string; snapshot_at: string | null }[]
}
export interface Simulacion {
  project_id: string; project_name: string
  simulation: { base_end_date: string; simulated_end_date: string; days_delta: number; total_remaining_hours: number
    effective_remaining_hours: number; cost_delta_eur: number; deferred_tasks: number; cut_tasks: number; at_risk_tasks: number }
  notes: string[]; at_risk: { id: string; code: string; title: string; due_date: string }[]
}
export type SugerenciaDePersona = SugerenciaDeAsignacion

export const iaDeProyectosApi = {
  estimar: (taskId: string) => D<EstimacionIa>(api.post(`/ai-planning/estimate/${taskId}`)),
  aceptarEstimacion: (taskId: string, accepted: boolean) => D<{ ok: boolean }>(api.post(`/ai-planning/estimate/${taskId}/accept`, { accepted })),
  sugerirPersona: (body: { title: string; description?: string; project_id?: string; priority?: string }) =>
    D<SugerenciaDePersona>(api.post('/semantic/suggest/task', body)),
  salud: (projectId: string) => D<SaludDelProyecto>(api.get(`/activity/projects/${projectId}/health`)),
  simular: (projectId: string, body: { delay_days?: number; compress_pct?: number; add_resources?: { hours_per_week: number }[] }) =>
    D<Simulacion>(api.post(`/activity/projects/${projectId}/simulate`, body)),
}

// ── Recursos (pantallas sobre /resources, rev. 173) ──────────────────────────

export interface AlertaDeRecurso { id: string; user_id: string; user_name: string; alert_type: string; context: string | null; severity: string; triggered_at: string; acknowledged_at: string | null }
export interface SkillDeEquipo { user_id: string; skills: { skill_id: string; skill_name: string; level: string }[] }
export interface PersonaPorSkill { user_id: string; user_name: string; level: string; available_hours: number; load_pct: number }
export interface UtilizacionSemanal { user_id: string; user_name: string; week_iso: string; planned_hours: number; actual_hours: number; billable_hours: number; utilization_pct: number | null; billable_pct: number | null }

export const recursosApi = {
  alertas: (acknowledged = false) => D<AlertaDeRecurso[]>(api.get('/resources/alerts', { params: { acknowledged } })),
  reconocerAlerta: (id: string) => D<unknown>(api.patch(`/resources/alerts/${id}/acknowledge`)),
  skillsDelProyecto: (projectId: string) => D<SkillDeEquipo[]>(api.get(`/resources/${projectId}/skill-gaps`)),
  personasPorSkill: (skillId: string) => D<PersonaPorSkill[]>(api.get(`/resources/available-by-skill/${skillId}`)),
  historico: (weeksBack: number) => D<UtilizacionSemanal[]>(api.get('/resources/utilization-history', { params: { weeks_back: weeksBack } })),
}
