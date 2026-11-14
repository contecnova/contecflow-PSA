/**
 * Respuestas de la gestion del cambio: peticiones de cambio ITSM (`/sd/changes`),
 * planes de despliegue (rollout) y el CAB de peticiones de cambio de proyecto
 * (`/cab/*`). Comprobadas contra los serializadores del backend que cita cada tipo.
 *
 * Son `type` y no `interface` (ver tipos-sd.ts). Las listas llegan ya
 * desenvueltas por el interceptor de _core.ts y los `APIResponse {data, meta}`
 * tambien: `res.data` es el payload.
 */

// ── Peticiones de cambio ITSM (`/sd/changes`) ──────────────────────────────

/** `ChangeStatus` (app/models/service_desk/_enums.py). */
export type EstadoDeCambio =
  | 'draft' | 'submitted' | 'cab_review' | 'approved' | 'scheduled' | 'in_progress'
  | 'implemented' | 'post_review' | 'closed_success' | 'closed_failed' | 'cancelled'

/** `suggest_maintenance_window` (change_impact_service/riesgo.py). */
export type VentanaSugerida = {
  day_of_week: number
  hour_utc: number
  window_label: string
  avg_incidents_in_window: number
  confidence: 'low' | 'medium' | 'high'
}

/** `serialize_change` (app/services/service_desk/change_service.py): lista, alta y edicion. */
export type CambioItsm = {
  id: string
  number: string
  title: string
  /** standard | normal | emergency */
  change_type: string | null
  status: EstadoDeCambio | null
  /** low | medium | high | critical */
  risk: string | null
  priority: string | null
  planned_start: string | null
  planned_end: string | null
  actual_start: string | null
  actual_end: string | null
  requester_id: string | null
  /** Nombre de quien lo pide. */
  requester: string | null
  owner_id: string | null
  /** Nombre del responsable. */
  owner: string | null
  approved_by: string | null
  approved_at: string | null
  pir_success: boolean | null
  pir_date: string | null
  downtime_minutes: number | null
  created_at: string
  affected_cis: string[]
  release_id: string | null
  implementer_id: string | null
  rejected_reason: string | null
  auto_risk_score: number | null
  auto_risk_label: 'low' | 'medium' | 'high' | 'critical' | null
  impact_analyzed: boolean
  suggested_window: VentanaSugerida | null
}

/** `serialize_change(full=True)`: detalle (`GET /sd/changes/{id}`). */
export type CambioItsmDetalle = CambioItsm & {
  description: string | null
  business_justification: string | null
  implementation_plan: string | null
  rollback_plan: string | null
  test_plan: string | null
  impact_description: string | null
  pir_notes: string | null
}

/** `cancelar_cambio` (DELETE `/sd/changes/{id}`): cancela, no borra. */
export type CambioCancelado = { ok: boolean; id: string; status: 'cancelled'; already_cancelled: boolean }

/** `POST /sd/changes/{id}/approve`. */
export type CambioAprobado = { ok: boolean; status: EstadoDeCambio }

/** `POST /sd/changes/{id}/rollback` (trigger_change_rollback). */
export type VueltaAtrasDeCambio = { ok: boolean; change_id: string; rollback_triggered: boolean; reason: string }

// ── Planes de despliegue (change_rollout_service.py) ───────────────────────

export type EstadoDeFaseDeDespliegue = 'pending' | 'ready' | 'completed'

export type FaseDeDespliegue = {
  id: string
  name: string
  description: string
  target_pct: number
  gate_criteria: string[]
  steps: unknown[]
  duration_minutes: number
  status: EstadoDeFaseDeDespliegue
  started_at: string | null
  completed_at: string | null
  notes: string | null
}

/** `simulate_impact`. */
export type SimulacionDeDespliegue = {
  risk_score: number
  risk_label: string
  affected_services_count: number
  affected_users_count: number
  estimated_duration_minutes: number
  phases_count: number
  recommended_window: string
  recommendations: string[]
  canary_recommended: boolean
  rollback_readiness: 'required' | 'recommended'
}

/** `create_rollout_plan` (y lo que devuelven aprobar y avanzar fase). */
export type PlanDeDespliegue = {
  id: string
  change_request_id: string
  title: string
  name: string
  status: 'draft' | 'approved' | 'in_progress' | 'completed'
  rollout_phases: FaseDeDespliegue[]
  rollback_steps: string[]
  rollback_plan: string
  testing_checklist: { test_name: string; required: boolean; automated: boolean; status: string }[]
  communication_plan: { stakeholder_group: string; channel: string; message_template: string; send_at: string | null; status: string }[]
  maintenance_window_start: string | null
  maintenance_window_end: string | null
  created_by: string
  created_at: string
  updated_at: string
  approved_by: string | null
  approved_at: string | null
  executed_at: string | null
  completed_at: string | null
  current_phase_index: number
  gates_passed: string[]
  simulation: SimulacionDeDespliegue | null
}

/** `POST /sd/changes/{cr}/rollout-plans/{plan}/simulate` sin cuerpo: simula el plan guardado. */
export type SimulacionDePlan = { simulation: SimulacionDeDespliegue; impact: SimulacionDeDespliegue; plan_id: string }

// ── CAB de peticiones de cambio de proyecto (app/services/cab_service/cab.py) ──

/** `get_cab_pending_changes`. */
export type CambioEnCab = {
  id: string
  code: string
  title: string
  /** `ChangeRequestStatus`: aqui siempre submitted | under_review. */
  status: string
  /** `ChangeRequestImpact`. */
  impact: string | null
  cost_impact: number | null
  schedule_impact_days: number | null
  project_name: string | null
  project_code: string | null
  requester: string | null
  created_at: string | null
  votes: { approve: number; reject: number; total: number }
  my_vote: 'approve' | 'reject' | 'abstain' | null
  has_window: boolean
  rollback_plan: string | null
}

/** `list_maintenance_windows`. */
export type VentanaDeMantenimiento = {
  id: string
  name: string
  description: string | null
  start_dt: string
  end_dt: string
  /** production | staging | all */
  environment: string | null
  is_recurring: boolean | null
  creator: string | null
  created_at: string | null
}

/** `cast_cab_vote`. */
export type VotoDeCab = { ok: boolean; vote: 'approve' | 'reject' | 'abstain'; approvals: number; rejections: number }

/** `close_cab_vote`. */
export type VotacionDeCabCerrada = { ok: boolean; new_status: 'approved' | 'rejected' }
