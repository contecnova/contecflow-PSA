/**
 * Respuestas de BI (`/bi/**`, `/reports/**` y los informes programados de
 * `/billing-reports/scheduled-reports`), comprobadas contra el endpoint y el
 * servicio que cita cada una. El gobierno y la colaboración de BI que ya
 * estaban tipados viven en `tipos-grc.ts`.
 *
 * Son `type` y no `interface` a propósito: un alias de objeto se puede asignar
 * a los tipos con índice `[k: string]: unknown` de algunos componentes (la
 * `Table` de ui, por ejemplo).
 *
 * Las listas `APIListResponse` y los `APIResponse {data, meta}` llegan ya
 * desenvueltos por el interceptor de _core.ts: `res.data` es el payload. Los
 * `{items, count}` dentro de `data` no son APIListResponse: `ListaConCuenta`.
 */
/** Una fila de un informe: columna -> valor ya serializado por el servicio. */
export type FilaBi = Record<string, unknown>

// ── Report Builder (report_builder_service) ───────────────────────────────────

export type TipoDeColumnaBi = 'str' | 'int' | 'float' | 'bool' | 'date'

/** report_builder_service.ENTITIES[entidad].columns[col]. */
export type ColumnaDeEntidadBi = { label: string; type: TipoDeColumnaBi }

/** report_builder_service.ENTITIES[entidad] (`entidades()`: importes con la moneda de la organización). */
export type EntidadDeInformeBi = { label: string; group: string; columns: Record<string, ColumnaDeEntidadBi> }

/** GET /reports/schema y GET /bi/intelligence/query-builder/schema. */
export type EsquemaDeInformes = {
  entities: Record<string, EntidadDeInformeBi>
  operators: Record<string, { label: string }>
  groups: Record<string, string>
}

/** Filtro de una consulta del Report Builder (`FilterCondition` / `QueryBuilderFilterIn`). */
export type FiltroDeInformeBi = { column: string; operator: string; value: unknown }

/** `ReportQuery` (report_builder.py) / `VisualQueryPreviewIn` (bi_intelligence.py). */
export type ConsultaDeInformeBi = {
  entity: string
  columns: string[]
  filters: FiltroDeInformeBi[]
  sort?: { column: string; direction: string } | null
  limit: number
}

/** POST /reports/preview. */
export type VistaPreviaDeInforme = { rows: FilaBi[]; count: number; truncated: boolean }

/** GET/POST /reports/templates (report_builder.save_template). */
export type PlantillaDeInforme = { id: number; name: string; query: ConsultaDeInformeBi }

// ── BI Intelligence (bi_intelligence_service) ────────────────────────────────

/** list_advanced_report_presets. */
export type PresetAvanzadoBi = { id: string; name: string; entity: string; columns: string[]; suggested_chart: string }

/** preview_advanced_report. */
export type VistaPreviaDePresetAvanzado = { preset: PresetAvanzadoBi; count: number; rows: FilaBi[] }

/** preview_visual_query. */
export type VistaPreviaDeConsultaVisual = { entity: string; columns: string[]; count: number; rows: FilaBi[]; truncated: boolean }

/** save_visual_query_template (la consulta sin los campos nulos). */
export type PlantillaDeConsultaVisual = { id: number; name: string; query: Partial<ConsultaDeInformeBi> & { entity: string }; saved_at: string }

/** delivery_overview. */
export type ResumenDeEnviosBi = {
  timestamp: string
  total: number
  active: number
  with_slack: number
  errored: number
  by_frequency: Record<string, number>
}

// ── Report Builder v2 (bi_report_builder_v2_service) ─────────────────────────

/** BASE_PRESETS mezclado con la personalización de la organización. */
export type PresetBiV2 = {
  id: string
  name: string
  category: string
  description: string
  table: string
  columns: string[]
  group_by: string | null
  sort_by: string | null
  sort_direction: 'asc' | 'desc'
  filters: Record<string, unknown>
  customizable: boolean
}

/** execute_preset_with_controls()["result"] (GET .../preview). */
export type VistaPreviaDePresetBiV2 = {
  preset_id: string
  preset_name: string
  category: string
  columns: string[]
  rows: FilaBi[]
  count: number
  generated_at: string
  degraded: boolean
  execution_ms: number
  timeout_seconds: number
  completed_stages: number
  total_stages: number
}

/** export_preset_data. */
export type ExportacionDePresetBiV2 = {
  export_format: 'json' | 'csv' | 'xlsx'
  filename: string
  preset_name: string
  columns: string[]
  rows: FilaBi[]
  count: number
  generated_at: string
}

// ── Query Builder (bi_query_builder_service) ─────────────────────────────────

export type CampoDeDatasetBi = { name: string; key: string; label: string; type: TipoDeColumnaBi }
export type DatasetBi = { name: string; label: string; fields: CampoDeDatasetBi[] }

/** get_schema. */
export type EsquemaDelQueryBuilder = {
  datasets: DatasetBi[]
  operators: Record<string, { label: string }>
  groups: Record<string, string>
  aggregations: Array<'count' | 'sum' | 'avg' | 'min' | 'max'>
}

/** _normalize_filters. */
export type FiltroDeConsultaBi = { field: string; column: string; operator: string; value: unknown }
/** _normalize_aggregations. */
export type AgregacionDeConsultaBi = { field: string; func: string; alias: string }

/** save_query. */
export type ConsultaGuardadaBi = {
  id: string
  name: string
  dataset: string
  fields: string[]
  filters: FiltroDeConsultaBi[]
  group_by: string[]
  aggregations: AgregacionDeConsultaBi[]
  sort_by: string | null
  sort_dir: 'asc' | 'desc'
  limit: number
  created_by: string
  created_at: string
  updated_at: string
}

/** preview_query / execute_query (`query_id` nulo en la vista previa). */
export type ResultadoDeConsultaBi = {
  query_id: string | null
  executed_at: string
  execution_ms: number | null
  dataset: string
  fields: string[]
  columns: string[]
  rows: FilaBi[]
  row_count: number
  total_before_limit: number
  truncated: boolean
  group_by: string[]
  aggregations: AgregacionDeConsultaBi[]
  /** Si es true, los totales salen de `filas_leidas` de `filas_totales`. */
  incompleto: boolean
  filas_leidas: number
  filas_totales: number
}

// ── Alertas inteligentes (bi_smart_alerts) ────────────────────────────────────

export type SeveridadBi = 'info' | 'warning' | 'critical'
export type CondicionDeAlertaBi = 'threshold_above' | 'threshold_below' | 'trend_up' | 'trend_down' | 'anomaly'

/** GET /bi/alerts/supported-metrics. */
export type MetricasDeAlertaBi = {
  metrics: Array<{ key: string; label: string; is_custom: boolean }>
  conditions: CondicionDeAlertaBi[]
}

/** rules.create_alert_rule (las reglas por defecto llevan `created_by` nulo). */
export type ReglaDeAlertaBi = {
  id: string
  name: string
  metric_key: string
  condition: CondicionDeAlertaBi
  threshold: number | null
  trend_periods: number
  severity: SeveridadBi
  cooldown_minutes: number
  enabled: boolean
  correlated_metrics: string[]
  notification_channels: string[]
  created_by: string | null
  created_at: string
  last_triggered_at: string | null
}

/** custom_metrics.create_custom_metric. */
export type MetricaPersonalizadaBi = {
  key: string
  label: string
  description: string
  formula: { operand_a: string; operator: '+' | '-' | '*' | '/'; operand_b_type: 'metric' | 'constant'; operand_b: string; scale: number }
  created_at: string
  created_by: string
}

/** _metricas_correladas_que_confirman. */
export type MetricaCorreladaBi = { metric_key: string; current_value: number; corr_coef: number; z_score: number; robust_z: number }

/** _entrada_de_alerta. `detail` depende de la condición (umbral, ventana o evaluación de anomalía). */
export type AlertaDisparadaBi = {
  id: string
  rule_id: string
  rule_name: string
  metric_key: string
  condition: CondicionDeAlertaBi
  severity: SeveridadBi
  detail: { current_value: number; metric_key: string } & Record<string, unknown>
  correlated: MetricaCorreladaBi[]
  triggered_at: string
  acknowledged: boolean
  acknowledged_by: string | null
  acknowledged_at: string | null
}

/** evaluate_alerts. */
export type EvaluacionDeAlertasBi = { evaluated_at: string; rules_evaluated: number; triggered_count: number; triggered: AlertaDisparadaBi[] }

// ── RGPD (bi_gdpr_service) ────────────────────────────────────────────────────

/** record_consent. */
export type ConsentimientoBi = { user_id: string; consented: boolean; granted: boolean; purpose: string; channel: string; updated_at: string }

/** Historial de consentimiento de un usuario (lo último primero). */
export type CambioDeConsentimientoBi = { action: 'granted' | 'revoked'; purpose: string; channel: string; ip_address: string | null; timestamp: string }

/** GET /bi/gdpr/consent/{user_id}/history. */
export type HistorialDeConsentimientoBi = { user_id: string; history: CambioDeConsentimientoBi[]; count: number }

export type TipoDeDsr = 'erasure' | 'portability' | 'rectification' | 'restriction'

/** execute_erasure. */
export type InformeDeBorradoRgpd = {
  subject_id: string
  executed_at: string
  operations: Array<{ table: string; action?: string; count?: number; row_id?: string; fields_cleared?: string[] }>
}

/**
 * create_dsr / resolve_dsr. `erasure_report` solo existe si el borrado se hizo al
 * completarla por `PATCH /bi/gdpr/dsr/{id}` con `status: completed`.
 */
export type SolicitudDsr = {
  id: string
  subject_id: string
  request_type: TipoDeDsr
  status: 'pending' | 'completed'
  requester_user_id: string
  notes: string | null
  created_at: string
  deadline: string
  resolved_at: string | null
  resolution_notes: string | null
  export_data: unknown
  erasure_report?: InformeDeBorradoRgpd
}

/** POST /bi/gdpr/dsr/{id}/erasure-execute. */
export type BorradoDeDsr = { ok: true; dsr_id: string; erasure_report: InformeDeBorradoRgpd }

/** execute_portability. */
export type ExportacionDePortabilidad = {
  export_type: 'portability'
  subject_id: string
  generated_at: string
  data: Record<string, unknown>
}

/** POST /bi/gdpr/dsr/{id}/portability-export. */
export type PortabilidadDeDsr = { ok: true; dsr_id: string; export: ExportacionDePortabilidad }

/** set_field_mask. */
export type MascaraDeCampoBi = { dataset: string; field: string; mask_type: 'pseudonymize' | 'suppress' | 'hash' | 'redact'; updated_at: string }

/** get_dsr_stats. */
export type EstadisticasRgpd = {
  total_dsrs: number
  pending: number
  completed: number
  overdue: number
  overdue_ids: string[]
  by_type: Record<string, number>
  total_consents: number
  consented: number
  revoked: number
}

// ── Colaboración en paneles (bi_collaboration_service) ───────────────────────

/** compartir.list_dashboard_shares / share_dashboard. */
export type ComparticionDePanelBi = {
  id: string
  dashboard_key: string
  user_id: string
  user_name: string
  permission: 'view' | 'edit' | 'admin'
  shared_by_id: string
  shared_by_name: string | null
  created_at: string | null
  updated_at: string | null
}

/** vistas_y_versiones.list_dashboard_versions / create_dashboard_version. */
export type VersionDePanelBi = {
  id: string
  dashboard_key: string
  version: number
  config: Record<string, unknown>
  change_log: string
  created_by_id: string
  created_by_name: string | null
  created_at: string | null
}

/** avisos.list_notifications. `payload` depende de `event_type`. */
export type AvisoDePanelBi = {
  id: string
  dashboard_key: string
  event_type: string
  recipient_user_id: string | null
  payload: Record<string, unknown>
  is_read: boolean
  read_at: string | null
  created_at: string | null
}

// ── ETL (bi_etl_service, app/integrations/bi_etl_connectors.ficha) ───────────

/** Un campo del formulario de un tipo de conector. */
export type CampoDeConectorEtl = { clave: string; secreto: boolean }

/** bi_etl_connectors.ficha: lo que hace falta para pintar el formulario. */
export type FichaDeConectorEtl = { etiqueta: string; falta: string | null; campos: CampoDeConectorEtl[]; entidades: string[] }

/** bi_etl_service._fila. */
export type ConectorEtl = FichaDeConectorEtl & {
  connector_id: string
  tipo: string
  nombre: string
  personalizado: boolean
  enabled: boolean
  status: 'connected' | 'error' | 'disconnected'
  last_sync_at: string | null
  last_records: number
  last_error: string | null
  entity: string
  /** Sin los secretos: esos solo se nombran en `secretos_puestos`. */
  config: Record<string, string>
  secretos_puestos: string[]
}

/** GET /bi/etl/connectors. */
export type ConectoresEtl = { connectors: ConectorEtl[]; count: number; generico: FichaDeConectorEtl }

/** bi_etl_service.probar. */
export type PruebaDeConectorEtl = { ok: boolean; records?: number; error?: string }

/** bi_etl_service.sincronizar (BaseConnector.run_sync). */
export type SincronizacionEtl = {
  connector_id: string
  ok: boolean
  connector: string
  records_ingested: number
  entity?: string
  error?: string
  started_at: string
  finished_at: string
}

/** bi_etl_connectors._log_sync. */
export type EntradaDeRegistroEtl = { connector: string; ok: boolean; records_ingested: number; error: string | null; started_at: string; finished_at: string }

/** GET /bi/etl/connectors/{id}/log. */
export type RegistroDeConectorEtl = { connector_id: string; entries: EntradaDeRegistroEtl[]; count: number }

// ── Previsión y anomalías (bi_forecasting_service, bi_anomaly_service) ───────

/** GET /bi/forecast/metrics. */
export type MetricasDePrevisionBi = { metrics: string[]; methods: string[]; prophet_available: boolean; arima_available: boolean }

/** bi_forecasting_service.forecast: listas paralelas, una posición por periodo. */
export type PrevisionBi = {
  metric: string
  method: string
  horizon: number
  freq: string
  prophet_available: boolean
  arima_available: boolean
  history: number[]
  forecast: number[]
  lower_bound: number[]
  upper_bound: number[]
}

/** POST /bi/forecast/multi (`forecasts` repite `results`). */
export type PrevisionesBi = { results: PrevisionBi[]; forecasts: PrevisionBi[]; errors: Array<{ metric: string; error: string }>; total: number }

/** GET /bi/anomaly/info. */
export type CapacidadesDeAnomaliasBi = { sklearn_available: boolean; lgbm_available: boolean; methods: string[]; churn_features: string[] }

/** POST /bi/anomaly/detect (detect_anomalies + `anomalies`). */
export type DeteccionDeAnomaliasBi = {
  method_used: string
  sklearn_available: boolean
  total_points: number
  anomaly_count: number
  anomaly_indices: number[]
  anomaly_scores: number[]
  is_anomaly: boolean[]
  anomalies: Array<{ index: number; period: string | null; value: number; score: number }>
}

export type NivelDeAbandono = 'low' | 'medium' | 'high'

/** predict_churn()["clients"][i]. */
export type AbandonoDeClienteBi = { client_id: string; client_name: string; churn_probability: number; risk_level: NivelDeAbandono; top_factors: string[] }

/** predict_churn. */
export type PrediccionDeAbandonoBi = {
  method_used: string
  lgbm_available: boolean
  total_clients: number
  high_risk_count: number
  medium_risk_count: number
  low_risk_count: number
  clients: AbandonoDeClienteBi[]
}

/** POST /bi/churn/predict: con `client_id` (contrato heredado) devuelve solo ese cliente. */
export type ResultadoDeAbandonoBi = (AbandonoDeClienteBi & { method_used: string }) | PrediccionDeAbandonoBi

// ── Plataforma (bi_platform_service) ─────────────────────────────────────────

export type AristaDeLinajeBi = { id: string; source_table: string; target_table: string; transformation_sql: string; created_by: string; created_at: string; updated_at: string }
export type AccesoDePlataformaBi = { id: string; timestamp: string; user_id: string; entity_type: string; entity_id: string; action: string; extra: Record<string, unknown> }

/** get_lineage. */
export type LinajeDePlataformaBi = { edges: AristaDeLinajeBi[]; audit: AccesoDePlataformaBi[] }

/** create_dataset_snapshot. */
export type InstantaneaDeDatasetBi = { id: string; dataset_key: string; created_at: string; created_by: string; payload: Record<string, unknown> }

/** diff_snapshots. */
export type DiferenciaDeInstantaneasBi = {
  dataset_key: string
  from_id: string
  to_id: string
  changes: Array<{ field: string; from: unknown; to: unknown }>
  change_count: number
}

// ── Entrega condicional (bi_conditional_delivery_service) ────────────────────

/** create_rule (+ `updated_at` tras editarla). */
export type ReglaDeEntregaBi = {
  id: string
  name: string
  report_id: string
  condition_metric: string | null
  condition_operator: 'gt' | 'gte' | 'lt' | 'lte' | 'eq' | null
  condition_value: number | null
  diff_threshold_pct: number
  recipients: string[]
  schedule_cron: string
  enabled: boolean
  created_by: string
  created_at: string
  updated_at?: string
  last_triggered_at: string | null
  trigger_count: number
}

/** evaluate_rule. */
export type EvaluacionDeEntregaBi = {
  should_deliver: boolean
  reason: 'rule_disabled' | 'condition_not_met' | 'diff_threshold_met' | 'no_significant_change'
  diff_pct: number
  condition_met: boolean
  rule_id?: string
}

// ── Office 365 (bi_o365_service) ──────────────────────────────────────────────

/** get_config: sin el secreto (`secret_puesto` dice si hay uno guardado). */
export type ConfigO365 = {
  tenant_id: string
  client_id: string
  enabled: boolean
  sync_period: 'D7' | 'D30' | 'D90' | 'D180'
  enabled_reports: string[]
  last_sync_at: string | null
  secret_puesto: boolean
  /** Informes que el servidor sabe traer. */
  reports: string[]
}

/** run_sync. */
export type SincronizacionO365 = {
  ok: boolean
  synced: Array<{ report: string; ok: boolean; records?: number; error?: string }>
  period?: string
  error?: string
}

/** get_report_data: las filas son el CSV de Graph tal cual. */
export type InformeO365 = { report: string; rows: Array<Record<string, string>>; count: number; fetched_at: string | null }

/** get_adoption_summary (sin datos solo llegan `active_users`, `products` y `note`). */
export type AdopcionO365 = {
  total_users?: number
  active_users: number
  adoption_rate?: number
  by_product?: Record<string, number>
  fetched_at?: string | null
  products?: Record<string, number>
  note?: string
}

// ── Informes programados (app/schemas/billing_reports.py) ─────────────────────

/** ScheduledReportOut. */
export type InformeProgramado = {
  id: string
  name: string
  metric: string | null
  frequency: string
  recipients: string[]
  include_pdf: boolean
  is_active: boolean
  last_run_at: string | null
  next_run_at: string | null
  created_at: string | null
}

/** ScheduledReportCreateOut. */
export type InformeProgramadoCreado = { ok: boolean; id: string }

/** ScheduledReportRunOut; con cola, 202 `respuesta_en_cola` con `status: 'queued'`. */
export type EjecucionDeInformeProgramado = { ok: boolean; recipients: string[]; status?: 'queued'; report_id?: string }
