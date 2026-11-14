/**
 * Tipos de respuesta de GRC, retención, proveedores de IA, observabilidad
 * predictiva y gobierno de datos de BI (GrcPage, AIHubPage, DataGovernancePage).
 * Comprobados contra los serializadores del backend que cita cada uno. Las
 * respuestas `APIResponse`/`APIListResponse` llegan desenvueltas por el
 * interceptor de _core.ts.
 */

// ── GRC (app/api/v1/endpoints/grc.py) ─────────────────────────────────────────

/** rol -> módulo -> acción -> permitido. */
export type MatrizDePermisos = Record<string, Record<string, Record<string, boolean>>>

/** GET /grc/permissions. */
export interface PermisosGrc { matrix: MatrizDePermisos; modules: string[]; roles: string[] }

/** PATCH /grc/permissions/{role}/{module}/{action}. */
export interface PermisoGrcActualizado { role: string; module: string; action: string; allowed: boolean }

/** grc_service.serialize_sod_rule. */
export interface ReglaSod {
  id: string
  module_a: string
  action_a: string
  module_b: string
  action_b: string
  risk: string
  description: string | null
  is_active: boolean
  roles_conflict: string[]
  mitigated_by_workflow_id: string | null
  created_at: string | null
}

/** Conflicto potencial de GET /grc/sod-check (no tiene `id`: es por regla y rol). */
export interface ConflictoSod {
  rule_id: string
  rule_description: string | null
  module_a: string
  action_a: string
  module_b: string
  action_b: string
  risk: string
  conflicting_role: string
  mitigated: boolean
}

/** GET /grc/sod-check. */
export interface ComprobacionSod { violations: ConflictoSod[]; count: number }

/** grc_service.serialize_violation. */
export interface ViolacionSod {
  id: string
  rule_id: string | null
  user_id: string | null
  user_name: string | null
  role: string | null
  context_type: string | null
  context_id: string | null
  detected_at: string | null
  resolved: boolean
  resolved_at: string | null
  resolution_note: string | null
}

/** GET /grc/audit-log (grc.get_audit_log). */
export interface EventoDeAuditoriaGrc {
  id: string
  timestamp: string | null
  user_id: string | null
  user_name: string | null
  action_type: string
  resource_type: string | null
  resource_id: string | null
  detail: Record<string, unknown> | null
  ip_address: string | null
  severity: string
}

/** explicar_acceso._capa: los datos extra de cada capa van al mismo nivel. */
export interface CapaDeAcceso {
  layer: string
  verdict: 'allow' | 'deny' | 'not_applicable' | 'unknown'
  detail: string
  [extra: string]: unknown
}

/** explicar_acceso._resumen. */
export interface ExplicacionDeAcceso {
  user: { id: string; name: string | null; role: string }
  method: string
  path: string
  template: string | null
  verdict: 'allow' | 'deny' | 'unknown'
  decided_by: string | null
  layers: CapaDeAcceso[]
}

/** explicar_acceso.rutas. */
export interface RutaExplicable { method: string; path: string }

/** informe_de_cumplimiento._control. */
export interface ControlMedido {
  id: string
  status: 'pass' | 'attention' | 'info' | 'not_measurable'
  measured: Record<string, unknown>
  source: string
  frameworks: string[]
}

/** informe_de_cumplimiento.generar (GET /grc/compliance-report sin firmar). */
export interface InformeDeCumplimiento {
  format: string
  organization_id: string | null
  organization_name: string | null
  generated_at: string
  summary: Record<string, number>
  controls: ControlMedido[]
  audit_chain_head: unknown
  [extra: string]: unknown
}

// ── Retención y bloqueo legal (app/services/retencion.py) ─────────────────────

/** retencion.politicas. */
export interface PoliticaDeRetencion {
  entity: string
  hold_fields: string[]
  keep_days: number | null
  is_active: boolean
  last_run_at: string | null
  last_deleted: number | null
}

/** GET /governance/retention/policies. */
export interface PoliticasDeRetencion { policies: PoliticaDeRetencion[]; min_days: number }

/** retencion.vista_previa. */
export interface VistaPreviaDeRetencion {
  entity: string
  keep_days: number
  expired: number
  held: number
  would_delete: number
  cutoff: string
}

/** retencion.aplicar: por tipo de registro. */
export type ResultadoDeRetencion = Record<string, { deleted: number; failed: number; keep_days: number }>

/** retencion.lista_de_bloqueos. */
export interface BloqueoLegal {
  id: string
  case_reference: string
  reason: string | null
  entity: string
  field: string
  value: string
  is_active: boolean
  created_at: string
  released_at: string | null
}

// ── Proveedores de IA (app/api/v1/endpoints/ai_providers.py) ──────────────────

/** ai_providers._out; `source: 'env'` es el del `.env` (id "env", no es una fila). */
export interface ProveedorIa {
  id: string
  source?: 'env'
  name: string
  provider: string
  status: string
  is_default: boolean
  default_model: string | null
  available_models: string[]
  api_base_url: string | null
  has_api_key: boolean
  max_tokens: number | null
  temperature: number | null
  priority: number | null
  total_requests: number
  total_cost_usd: number
  last_used_at: string | null
  last_error: string | null
  created_at: string | null
}

/** app/core/ai_models.json. */
export interface ModeloDelCatalogoIa { id: string; name: string; context?: number; cost_in: number; cost_out: number }

/** catalogo.PROVIDER_CATALOG[proveedor]. */
export interface EntradaCatalogoIa {
  name: string
  icon: string
  models: ModeloDelCatalogoIa[]
  base_url: string
  key_hint: string
  docs_url: string
}

/** GET /ai-providers/catalog. */
export type CatalogoIa = Record<string, EntradaCatalogoIa>

/** POST /ai-providers/{id}/test, /test-config y /env/test (los fallos llegan como error HTTP). */
export interface PruebaDeProveedorIa { ok: boolean; response: string; latency_ms: number; model: string | null }

/** POST /ai-providers/{id}/sync-models. */
export interface ModelosSincronizadosIa {
  ok: boolean
  provider_id: string
  provider: string
  models: string[]
  default_model: string | null
}

/** POST /ai-providers/sync-models/all (sin proveedores: solo `ok`, `results` y `message`). */
export interface SincronizacionIa {
  ok: boolean
  results: Array<{ provider_id: string; name: string; provider: string; ok: boolean; count?: number; default_model?: string | null; error?: string }>
  total?: number
  failed?: number
  message?: string
}

/** clientes.diagnose_provider. */
export interface DiagnosticoDeProveedorIa {
  id: string
  name: string
  provider_type: string
  status: 'ok' | 'warning' | 'error'
  latency_ms: number | null
  model: string | null
  models_found: number
  error: string | null
}

/** GET /ai-providers/diagnostics. */
export interface DiagnosticoIa { total: number; healthy: number; warning: number; error: number; providers: DiagnosticoDeProveedorIa[] }

/** GET /ai-providers/stats. */
export interface EstadisticasIa {
  providers: ProveedorIa[]
  by_module: Array<{ module: string; calls: number; tokens: number; cost: number }>
  total_cost: number
  total_requests: number
}

/** rutas.rutas_por_modulo / guardar_rutas. */
export type RutasIa = Record<string, { provider_id: string | null; model: string | null }>

/** GET /ai-providers/routing. */
export interface EnrutadoIa { modules: Array<{ key: string; label: string }>; routes: RutasIa }

/** GET /ai-providers/spend-today. */
export interface GastoIaDeHoy { spent_usd: number; budget_usd: number; warn_pct: number; used_pct: number | null; blocked: boolean }

// ── Observabilidad predictiva (predictive_retraining_service) ─────────────────

/** evaluate_itsm_model_health / evaluate_bi_model_health: comunes + los de cada modelo. */
export interface SaludDeModeloPredictivo {
  model: string
  organization_id: string | null
  score: number
  status: 'healthy' | 'attention' | 'insufficient_data'
  evaluated_at: string
  // ITSM
  lookback_days?: number
  samples?: number
  evaluated_resolution?: number
  mae_minutes?: number | null
  severity_accuracy?: number | null
  // BI
  forecast_engine?: string
  overrun_engine?: string
  history_months?: number
  forecast_library_available?: boolean
  overrun_library_available?: boolean
}

/** GET /bi/predictive/observability/health. */
export interface SaludPredictiva {
  organization_id: string | null
  overall_score: number
  overall_status: string
  status_rank: Record<string, number>
  itsm: SaludDeModeloPredictivo
  bi: SaludDeModeloPredictivo
}

// ── Gobierno y colaboración BI ────────────────────────────────────────────────

/** bi_collaboration_service.comentarios.list_comments / create_comment. */
export interface ComentarioBi {
  id: string
  dashboard_key: string | null
  widget_id: string | null
  message: string
  author_id: string | null
  author_name: string | null
  resolved: boolean
  resolved_at: string | null
  resolved_by: string | null
  created_at: string | null
}

/** vistas_y_versiones.create_shared_view. */
export interface VistaCompartidaBi {
  id: string
  name: string
  dashboard_key: string
  filters: Record<string, unknown>
  active: boolean
  created_at: string
  created_by_id: string
  created_by_name: string | null
}

/** gobierno.governance_overview. */
export interface ResumenDeGobiernoBi {
  timestamp: string
  olap: { path: string; available: boolean; staleness_hours: number | null }
  scheduled_reports: { active: number; error: number }
  collaboration: { unresolved_comments: number }
  cache_policy: { metric_count: number; default_ttl_seconds: number; min_ttl_seconds: number; max_ttl_seconds: number }
}

/** gobierno.default_governance_rules (más lo que se haya guardado). */
export interface ReglasDeGobiernoBi {
  olap_max_staleness_hours: number
  max_error_reports: number
  require_active_schedules: boolean
}

/** gobierno.run_governance_checks. */
export interface EjecucionDeGobiernoBi {
  timestamp: string
  status: 'ok' | 'attention'
  finding_count: number
  findings: Array<{ code: string; severity: string; message: string }>
  overview: ResumenDeGobiernoBi
  rules: ReglasDeGobiernoBi
}

/** bi_governance_service._fila_de_acceso. */
export interface AccesoBi {
  id: string
  timestamp: string
  user_id: string | null
  user_name: string | null
  entity_type: string
  entity_id: string | null
  action: string
  ip_address: string | null
  user_agent: string | null
  before_state: unknown
  after_state: unknown
  extra: Record<string, unknown>
}

/** bi_governance_service.track_data_lineage. */
export interface LinajeBi {
  id: string
  source_table: string
  target_table: string
  transformation_sql: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export type NivelDeSensibilidadBi = 'public' | 'internal' | 'confidential' | 'restricted'

/** bi_governance_service.upsert_field_sensitivity. */
export interface SensibilidadDeCampoBi {
  id: string
  dataset_id: string
  field_name: string
  sensitivity_level: NivelDeSensibilidadBi
  pii_fields: string[]
  requires_approval: boolean
  created_at: string
  updated_at: string
  created_by: string
  updated_by: string
}

/** bi_bookmarks_service.create_bookmark. */
export interface MarcadorBi {
  id: string
  name: string
  description: string
  period_days: number
  active_tab: string
  filters: Record<string, unknown>
  widget_states: Record<string, unknown>
  chart_types: Record<string, string>
  shared: boolean
  created_by: string
  created_at: string
  updated_at: string
}

/** Respuestas `{items, count}` dentro de `data` (no son APIListResponse). */
export interface ListaConCuenta<T> { items: T[]; count: number }
