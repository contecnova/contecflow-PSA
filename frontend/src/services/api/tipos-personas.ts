/**
 * Respuestas de tiempo y personas: imputaciones y cronometro (`/imputations`),
 * timesheets, ausencias, proyeccion y capacidad de recursos, skills, formacion,
 * comentarios y menciones, pipeline comercial y NPS. Comprobadas contra los
 * esquemas y serializadores del backend que cita cada tipo.
 *
 * Son `type` y no `interface` (ver tipos-sd.ts). Las listas llegan ya
 * desenvueltas por el interceptor de _core.ts y los `APIResponse {data, meta}`
 * tambien: `res.data` es el payload.
 */
import type { ProjectListItem } from './projects'
import type { TaskListItem } from './tasks'
import type { UserPublic } from './users'

/** Respuesta de las escrituras que solo devuelven un texto. */
export type SoloMensaje = { message: string }

// ── Imputaciones y cronometro ──────────────────────────────────────────────

/** `ImputationOut` (app/schemas/imputations.py). */
export type Imputacion = {
  id: string
  user: UserPublic
  task: TaskListItem | null
  project: ProjectListItem | null
  date: string
  hours: number
  /** `null` en imputaciones ajenas de un proyecto con `can_see_rates = false`. */
  cost_amount: number | null
  description: string | null
  is_billable: boolean
  is_approved: boolean
  is_invoiced: boolean
  invoiced_invoice_id: string | null
  timer_session_id: string | null
  created_at: string
}

/** `WeekSummary` (app/schemas/imputations.py; `get_week_summary`). */
export type ResumenSemanal = {
  user_id: string
  week_start: string
  week_end: string
  total_hours: number
  capacity_hours: number
  load_pct: number
  by_project: { project_id: string; project_name: string; hours: number }[]
  by_day: { date: string; hours: number }[]
}

/** `TimerSessionOut` (app/schemas/time_tracking.py; `timer_out`). */
export type SesionDeCronometro = {
  id: string
  user_id: string
  task_id: string | null
  task_name: string | null
  project_id: string
  project_name: string | null
  started_at: string
  paused_at: string | null
  paused_duration_secs: number
  ended_at: string | null
  total_elapsed_seconds: number | null
}

// ── Timesheets ─────────────────────────────────────────────────────────────

/** `TimesheetStatus` (app/models/financial.py). */
export type EstadoDeTimesheet = 'draft' | 'submitted' | 'approved' | 'rejected'

/** `TimesheetOut` (app/schemas/timesheets.py). */
export type Timesheet = {
  id: string
  user_id: string
  week_start: string
  week_end: string
  status: EstadoDeTimesheet
  total_hours: number
  billable_hours: number
  total_cost: number
  submitted_at: string | null
  reviewed_at: string | null
  review_notes: string | null
  /** `null` en `/timesheets/my` (no lo rellena). */
  user_name: string | null
  reviewer_name: string | null
}

/** Linea de `get_timesheet_lines` (app/services/timesheet_service.py). */
export type LineaDeTimesheet = {
  id: string
  date: string
  hours: number
  project_id: string
  project_name: string | null
  task_id: string | null
  task_title: string | null
  description: string | null
  billable: boolean
  is_approved: boolean
}

/** Envio y revision de un timesheet (app/api/v1/endpoints/timesheets.py). */
export type TimesheetCambiado = { message: string; status: EstadoDeTimesheet }

// ── Ausencias ──────────────────────────────────────────────────────────────

/** `serialize_absence` (app/services/absence_service.py). */
export type Absence = {
  id: string
  user_id: string
  user_name: string
  /** `AbsenceType`: vacation | sick | personal | training | maternity | paternity | other. */
  type: string
  type_label: string
  /** `AbsenceStatus`: pending | approved | rejected | cancelled. */
  status: string
  status_label: string
  status_color: string
  start_date: string
  end_date: string
  working_days: number | null
  reason: string | null
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
  created_at: string | null
}

/** `get_vacation_balance` (app/services/absence_service.py). */
export type SaldoDeVacaciones = {
  year: number
  days_entitled: number
  days_carried: number
  days_taken: number
  days_pending: number
  days_remaining: number
}

/** `GET /absences/calendar`. */
export type CalendarioDeAusencias = {
  year: number
  month: number
  absences: Absence[]
  holidays: { date: string; name: string; type: string | null }[]
}

/** `POST /absences/{id}/review`. */
export type AusenciaRevisada = { message: string; status: string }

// ── Proyeccion de recursos (`/resource-forecast`) ──────────────────────────

/** Periodo que ha calculado un horizonte de previsión (periodo libre, 16-11-2026). */
export type PeriodoDeHorizonte = {
  desde: string | null
  hasta: string | null
  granularidad: string
  /** `weeks` si se pidió por número de semanas; si no, `rango`/`days`. */
  origen: string
  zona?: string
}

/** Estado de carga de una semana del mapa de calor. */
export type EstadoDeCarga = 'overloaded' | 'high' | 'medium' | 'low' | 'available'

/** Semana de una persona en `GET /resource-forecast/weeks`. */
export type SemanaDeCarga = {
  week: string
  week_start: string
  load_pct: number
  committed_hours: number
  available_hours: number
  absence_hours: number
  holiday_hours: number
  tentative_hours: number
  status: EstadoDeCarga
  /** Horas reservadas por id de proyecto. */
  projects: Record<string, number>
}

/** `GET /resource-forecast/weeks` (forecast_heatmap). */
export type MapaDeCarga = {
  from_date: string
  weeks: number
  week_labels: string[]
  users: {
    user_id: string
    user_name: string
    department: string
    role: string
    capacity_hours: number
    avg_load_pct: number
    overloaded_weeks: number
    weeks: SemanaDeCarga[]
  }[]
  periodo?: PeriodoDeHorizonte | null
}

/** `GET /resource-forecast/users/{id}` (forecast_user_detail). */
export type ProyeccionDePersona = {
  user_id: string
  user_name: string
  department: string | null
  capacity_hours: number
  weeks: {
    week: string
    week_start: string
    load_pct: number
    committed_hours: number
    available_hours: number
    absence_hours: number
    breakdown: { project_id: string; project_name: string; hours: number; pct_of_week: number }[]
  }[]
  periodo?: PeriodoDeHorizonte | null
}

/** Persona de `GET /resource-forecast/availability`. */
export type CandidatoDisponible = {
  user_id: string
  user_name: string
  department: string
  avg_available_hrs: number
  min_available_hrs: number
  fits_requirement: boolean
  availability_pct: number
}

/** `GET /resource-forecast/availability` (find_available). */
export type DisponibilidadDeRecursos = {
  from_date: string
  to_date: string
  hours_needed: number
  candidates: CandidatoDisponible[]
  insufficient: CandidatoDisponible[]
}

/** `GET /resource-forecast/summary` (forecast_summary). */
export type ResumenDeCapacidad = {
  total_users: number
  weeks: number
  avg_team_load_pct: number
  total_capacity_hrs: number
  total_committed_hrs: number
  total_available_hrs: number
  risk_weeks_count: number
  overloaded_users_count: number
  week_trend: { week: string; load_pct: number }[]
  risk_weeks: string[]
  periodo?: PeriodoDeHorizonte | null
}

// ── Planificacion de capacidad (`/capacity`) ───────────────────────────────

/** Plan del tablero (`GET /capacity/board`). */
export type PlanDeCapacidad = {
  id: string
  user_id: string
  project_id: string | null
  project_name: string | null
  week_start: string
  planned_hours: number
  notes: string | null
}

/** `POST /capacity/plans`. */
export type PlanDeCapacidadCreado = Pick<PlanDeCapacidad, 'id' | 'user_id' | 'week_start' | 'planned_hours' | 'project_id'>
/** `PATCH /capacity/plans/{id}`. */
export type PlanDeCapacidadMovido = { ok: boolean; id: string }

// ── Skills ─────────────────────────────────────────────────────────────────

/** Skill de una persona (`GET /skills/users/{id}`). `id` es el de la asignacion. */
export type SkillDePersona = {
  id: string
  skill_id: string
  skill_name: string
  category: string
  category_label: string
  /** basic | intermediate | advanced | expert */
  level: string
  level_label: string
  years_experience: number | null
  certified: boolean
  cert_name: string | null
  cert_expiry: string | null
  notes: string | null
}

/** Cambio de nivel (`GET /skills/users/{id}/history`). */
export type CambioDeNivelDeSkill = {
  id: string
  skill_id: string
  skill_name: string
  old_level: string | null
  new_level: string
  notes: string | null
  recorded_by: string
  recorded_at: string | null
}

/** `GET /skills/matrix`. */
export type MatrizDeSkills = {
  skills: { id: string; name: string; category: string; category_label: string }[]
  users: {
    user_id: string
    user_name: string
    department: string | null
    /** Por id de skill; `level` y `level_label` son `null` si no la tiene. */
    skills: Record<string, { level: string | null; level_label: string | null; certified: boolean }>
  }[]
}

/** Persona de `GET /skills/search` (`search_by_skills`). */
export type PersonaPorSkills = {
  user_id: string
  user_name: string
  department: string | null
  role: string
  matching_skills: {
    skill_id: string
    skill_name: string
    level: string
    level_label: string
    years_experience: number | null
    certified: boolean
  }[]
  skill_count: number
}

/** `POST /skills/catalog`. */
export type SkillCreada = { id: string; name: string; category: string }
/** `POST /skills/users/{id}`. */
export type SkillAsignada = { id: string; message: string }

// ── Formacion (`/training`) ────────────────────────────────────────────────

/** `serialize_course` (app/services/training_service.py). */
export type Curso = {
  id: string
  title: string
  description: string | null
  provider: string | null
  category: string | null
  duration_h: number | null
  url: string | null
  cost: number | null
  enrolled: number
}

export type EstadoDeInscripcion = 'planned' | 'in_progress' | 'completed' | 'cancelled'

/** `serialize_enrollment`. */
export type Inscripcion = {
  id: string
  course_id: string
  course_title: string | null
  user_id: string
  user_name: string | null
  /** `CourseStatus` (app/models/training.py). */
  status: EstadoDeInscripcion
  start_date: string | null
  end_date: string | null
  score: number | null
  notes: string | null
}

/** `serialize_certification`. */
export type Certificacion = {
  id: string
  user_id: string
  user_name: string | null
  name: string
  issuer: string | null
  cert_id: string | null
  obtained_at: string | null
  expires_at: string | null
  days_until_expiry: number | null
  is_expired: boolean
  expiring_soon: boolean
  url: string | null
  notes: string | null
}

/** Altas y ediciones de formacion: solo el id. */
export type IdCreado = { id: string }
/** `POST /training/courses`. */
export type CursoCreado = { id: string; title: string }
/** `DELETE /training/certifications/{id}` (sin sobre `APIResponse`). */
export type CertificacionBorrada = { deleted: boolean }

// ── Comentarios en hilo y menciones ────────────────────────────────────────

/** `list_threaded_comments` (app/services/epics_service.py). */
export type ComentarioEnHilo = {
  id: string
  content: string
  created_by: string | null
  created_by_email: string | null
  created_by_name: string | null
  is_resolved: boolean
  created_at: string | null
  replies: ComentarioEnHilo[]
}

/** `add_threaded_comment`. */
export type ComentarioEnHiloCreado = {
  id: string
  content: string
  entity_type: string
  entity_id: string
  parent_id: string | null
}

/** `resolve_threaded_comment`. */
export type ComentarioResuelto = { resolved: boolean }

/** `my_mentions_payload` (app/services/activity_service/actividad.py). */
export type Mencion = {
  id: string
  entity_type: string
  entity_id: string
  mentioned_by_name: string
  context_text: string | null
  /** @deprecated alias de `context_text`; se conserva para clientes externos. */
  context?: string | null
  is_read: boolean
  created_at: string | null
}

/** `mark_mention_read_record`. */
export type MencionLeida = { ok: boolean }
/** `mark_all_mentions_read`. */
export type MencionesLeidas = { marked_read: number }

// ── Pipeline comercial (`/pipeline`) ───────────────────────────────────────

/** `OpportunityStage` (app/models/pipeline.py). */
export type EtapaDeOportunidad = 'lead' | 'qualification' | 'proposal' | 'negotiation' | 'won' | 'lost' | 'cancelled'

/** `serialize_opportunity` (app/services/pipeline_service.py). */
export type Oportunidad = {
  id: string
  code: string
  name: string
  client_id: string | null
  client_name: string | null
  /** Contacto propio de la oportunidad (no el contacto principal del cliente). */
  contact_name: string | null
  stage: EtapaDeOportunidad
  stage_label: string
  probability: number
  expected_revenue: number | null
  expected_margin_pct: number | null
  expected_hours: number | null
  hourly_rate: number | null
  contract_type: string | null
  weighted_revenue: number
  expected_close_date: string | null
  expected_start_date: string | null
  expected_duration_weeks: number | null
  owner_id: string | null
  owner_name: string | null
  project_id: string | null
  notes: string | null
  lost_reason: string | null
  description: string | null
  proposal_status: 'none' | 'generated' | 'sent'
  proposal_template_id: string | null
  proposal_generated_at: string | null
  proposal_sent_at: string | null
  created_at: string | null
}

/** `POST /pipeline/{id}/generate-proposal`. */
export type PropuestaGenerada = {
  id: string
  proposal_content: string | null
  proposal_status: 'generated'
  proposal_generated_at: string | null
  message: string
}

/** `POST /pipeline/{id}/mark-proposal-sent`. */
export type PropuestaEnviada = {
  id: string
  proposal_status: 'sent'
  proposal_sent_at: string | null
  message: string
}

/** `GET /pipeline/{id}/proposal`. */
export type Propuesta = {
  id: string
  proposal_content: string | null
  proposal_template_id: string | null
  proposal_generated_at: string | null
  proposal_sent_at: string | null
}

/** `convert_opportunity_to_project`. */
export type OportunidadConvertida = {
  project_id: string
  project_code: string
  project_name: string
  rev_contract_id: string | null
  message: string
}

// ── NPS y salud de cliente (`/nps`) ────────────────────────────────────────

/** `GET /nps/leaderboard`. */
export type SaludDeClienteEnRanking = {
  client_id: string
  client_name: string
  health_score: number
  snapshot_at: string | null
}

/** `compute_nps_summary` + `days` (app/services/nps_service.py). */
export type ResumenNps = {
  /** `null` sin respuestas en el periodo. */
  nps: number | null
  total: number
  promoters: number
  passives: number
  detractors: number
  /** Un punto por tramo del periodo (`t` ISO; `nps` null sin respuestas). */
  trend: { t: string; clave: string; nps: number | null; count: number }[]
  days: number
  periodo?: Record<string, unknown>
}

/** Foto de salud (`GET /nps/{id}/health`); los componentes son `null` si no se calcularon. */
export type FotoDeSalud = {
  id: string
  health_score: number
  nps_component: number | null
  delivery_component: number | null
  budget_component: number | null
  activity_component: number | null
  note: string | null
  snapshot_at: string | null
}

/** `POST /nps/{id}/health-compute`. */
export type FotoDeSaludCreada = Pick<FotoDeSalud, 'id' | 'health_score' | 'snapshot_at'>

/** `POST /nps/{id}/responses`. */
export type RespuestaNpsCreada = {
  id: string
  score: number
  category: 'promoter' | 'passive' | 'detractor'
  created_at: string | null
}
