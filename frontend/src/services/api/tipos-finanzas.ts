/**
 * Respuestas de finanzas: tarifas, hitos de facturación, gastos, reconocimiento
 * de ingresos (ASC 606), facturas, costes de personal, contabilidad,
 * rentabilidad, contratos, contratos IA, NexusOracle, escenarios, e-firma y
 * tipos de cambio. Comprobadas contra los serializadores del backend
 * (app/services/*_service.py, app/schemas/billing_reports.py y los endpoints
 * de app/api/v1/endpoints/).
 *
 * Son `type` y no `interface` (ver tipos-sd.ts): un alias de objeto se puede
 * asignar a tipos con índice `[k: string]: unknown`.
 *
 * Las listas llegan ya desenvueltas por el interceptor de _core.ts y los
 * `APIResponse {data, meta}` también: `res.data` es el payload.
 */
import type { Incumplimiento } from './gastos'

/** `{"ok": True}` de las escrituras que no devuelven la entidad. */
export type FinOk = { ok: boolean }
/** `{"ok": True, "message": ...}` de los borrados con mensaje. */
export type FinOkConMensaje = { ok: boolean; message: string }

// ── Tarifas (rate_card_service.serialize_rate_*) ──────────────────────────

export type TarifaEntrada = {
  id: string
  label: string
  cost_rate: number | null
  billing_rate: number | null
  escalation_pct: number
  valid_from: string | null
  valid_to: string | null
  notes: string | null
}

export type TarifaExcepcion = {
  id: string
  client_id: string | null
  project_id: string | null
  role_label: string
  billing_rate: number
  valid_from: string | null
  valid_to: string | null
  notes: string | null
}

export type TarifaAplicaA = 'role' | 'department' | 'client'

/** serialize_rate_table: la lista trae `entry_count`; el detalle y las escrituras, `entries` y `overrides`. */
export type TablaDeTarifas = {
  id: string
  name: string
  description: string | null
  applies_to: TarifaAplicaA
  is_default: boolean
  is_active: boolean
  created_at: string | null
  entry_count?: number
  entries?: TarifaEntrada[]
  overrides?: TarifaExcepcion[]
}

/** rate_card_service.get_effective_rate: `source` dice de dónde sale; `not_found` no es un error. */
export type TarifaEfectiva = {
  billing_rate: number | null
  source: string
  role_label: string
  cost_rate?: number | null
  override_id?: string
  table_id?: string
  entry_id?: string
  escalation_applied?: boolean
}

// ── Hitos de facturación (milestone_service.serialize_milestone) ──────────

export type EstadoDeFacturacionDeHito = 'pending' | 'completed' | 'pending_approval' | 'approved' | 'rejected' | 'invoiced'

export type HitoDeFacturacion = {
  id: string
  project_id: string
  name: string
  description: string | null
  due_date: string | null
  sort_order: number | null
  /** Puesta en marcha (go-live): al completarlo se programa la PIR del proyecto (migración 206). */
  is_go_live?: boolean
  billing_status: EstadoDeFacturacionDeHito
  is_completed: boolean
  completed_date: string | null
  billing_amount: number | null
  billing_pct: number | null
  is_billed: boolean
  invoice_id: string | null
  approved_at: string | null
  rejected_at: string | null
  rejection_reason: string | null
  approval_requested_at: string | null
}

/** request-approval y approve: el hito con el mensaje para el aviso. */
export type HitoConMensaje = HitoDeFacturacion & { message: string }

export type HitoFacturado = HitoConMensaje & {
  invoice: { id: string; invoice_number: string; amount: number; total_with_tax: number; status: string }
}

/** GET /milestones/dashboard/pending. */
export type HitoPendiente = HitoDeFacturacion & {
  project_name: string
  project_code: string
  next_action: 'request-approval' | 'approve' | 'generate-invoice' | '—'
}

// ── Gastos (expense_service.serialize_expense) ────────────────────────────

export type EstadoDeGasto = 'draft' | 'submitted' | 'approved' | 'rejected' | 'reimbursed'

export type Gasto = {
  id: string
  code: string | null
  user_id: string
  user_name: string | null
  project_id: string | null
  project_name: string | null
  contract_id: string | null
  category: string
  category_label: string
  description: string
  amount: number
  currency: string
  expense_date: string | null
  is_billable: boolean
  receipt_url: string | null
  receipt_name: string | null
  status: EstadoDeGasto
  submitted_at: string | null
  reviewed_by_name: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  reimbursed_at: string | null
  notes: string | null
  km: number | null
  /** Avisos de política guardados al enviar (gastos_avanzados.avisos_guardados). */
  policy_flags: Incumplimiento[]
  created_at: string | null
}

/** GET /expenses/team. */
export type GastosDelEquipo = {
  expenses: Gasto[]
  total: number
  billable_total: number
  by_category: Record<string, number>
}

/** expense_service.review_expense. */
export type RevisionDeGasto = { ok: boolean; status: EstadoDeGasto; avisos_de_presupuesto: string[] }

/** POST /expenses/ocr (expense_service.ocr_receipt). */
export type ReciboEscaneado = {
  ok: boolean
  extracted: {
    amount: number | null
    currency: string
    merchant: string | null
    date: string | null
    category: string
    description: string
  }
}

// ── Reconocimiento de ingresos ASC 606 (revenue_service) ──────────────────

export type MetodoAsc606 = 'over_time' | 'milestone' | 'consumption' | 'straight_line' | 'percentage_complete' | 'completed_contract'

/** _serialize_contract. */
export type ContratoAsc606 = {
  id: string
  project_id: string | null
  client_id: string | null
  name: string
  contract_value: number
  currency: string
  method: MetodoAsc606 | null
  start_date: string | null
  end_date: string | null
  duration_months: number | null
  is_active: boolean
  notes: string | null
  created_at: string | null
}

/** _serialize_obligation. */
export type ObligacionAsc606 = {
  id: string
  contract_id: string
  milestone_id: string | null
  name: string
  allocated_pct: number
  allocated_amount: number
  is_satisfied: boolean
  satisfied_date: string | null
  method: string | null
  standalone_price: number | null
  notes: string | null
}

/** _serialize_entry (reverse devuelve solo esto). */
export type EntradaAsc606 = {
  id: string
  rev_contract_id: string
  entry_type: 'recognized' | 'deferred' | 'unbilled' | 'reversal' | null
  amount: number
  currency: string
  period_year: number
  period_month: number
  milestone_id: string | null
  description: string | null
  reverses_entry_id: string | null
  created_by: string | null
  created_at: string | null
}

/** serialize_entries (GET /entries): la fila con el contrato y si está revertida. */
export type EntradaAsc606DelDiario = EntradaAsc606 & {
  contract_name: string | null
  method: MetodoAsc606 | null
  is_reversed: boolean
}

/** _serialize_period_close. */
export type CierreAsc606 = {
  id: string
  period_year: number
  period_month: number
  closed_by: string | null
  closed_at: string | null
  notes: string | null
}

/** get_asc606_dashboard. */
export type PanelAsc606 = {
  year: number
  total_recognized: number
  entry_count: number
  by_month: { month: number; year: number; recognized: number; deferred: number; unbilled: number }[]
  contracts: ContratoAsc606[]
}

/** run_monthly_recognition: importes por vía; las de avance solo si hubo contratos de ese método. */
export type ReconocimientoMensual = {
  period: string
  recognized: {
    over_time: number
    consumption: number
    straight_line: number
    skipped: number
    percentage_complete?: number
    completed_contract?: number
  }
}

// ── Facturas (app/schemas/billing_reports.py) ─────────────────────────────

/** InvoiceLineOut. */
export type LineaDeFactura = {
  id: string
  order: number
  description: string
  quantity: number
  unit: string | null
  unit_price: number
  discount_pct: number
  amount: number
  source_type: string | null
  /** JSON con los ids de origen (imputaciones si `source_type` es `timesheet`): la edición lo reenvía. */
  source_ids: string | null
}

/** InvoiceOut (lista, ficha, alta, edición y cambio de estado). */
export type Factura = {
  id: string
  number: string
  project_id: string | null
  client_id: string | null
  project_name: string | null
  project_code: string | null
  client_name: string | null
  client_email: string | null
  client_vat: string | null
  client_address: string | null
  subtotal: number | null
  tax_rate: number | null
  tax_amount: number | null
  total: number | null
  currency: string | null
  issue_date: string | null
  due_date: string | null
  paid_date: string | null
  status: string | null
  notes: string | null
  po_reference: string | null
  period_from: string | null
  period_to: string | null
  lines: LineaDeFactura[]
  created_at: string | null
}

/** InvoiceSummaryOut. */
export type ResumenDeFacturas = {
  by_status: Record<string, { count: number; total: number }>
  currency: string
  total_invoiced: number
  total_paid: number
  total_pending: number
  overdue_count: number
  overdue_amount: number
  /** Importes sin tipo de cambio a `currency`, por moneda: no se suman. */
  sin_tipo_de_cambio: Record<string, number>
}

/** psa_flows.build_invoice_preview_from_timesheets_flow. */
export type BorradorDeFacturaDesdePartes = {
  preview: true
  project_name: string
  client_name: string | null
  period_from: string | null
  period_to: string | null
  lines: {
    order: number
    description: string
    quantity: number
    unit: string
    unit_price: number
    discount_pct: number
    amount: number
    source_type: string
    /** JSON con los ids de las imputaciones. */
    source_ids: string
  }[]
  subtotal: number
  tax_rate: number
  tax_amount: number
  total: number
  currency: string
  imputation_count: number
}

// ── Contabilidad (accounting_hub) ─────────────────────────────────────────

/** accounting_hub_service.get_sync_status. */
export type EstadoDeSincronizacionContable = {
  invoices: { total_sent: number; synced_xero: number; synced_qb: number; pending_sync: number }
  /** `type` es `xero` o `quickbooks`; `last_sync` es "AAAA-MM-DD HH:MM". */
  active_integrations: { type: string; name: string; last_sync: string | null }[]
}

/** POST /accounting/push-invoices-bulk. */
export type SincronizacionContableEnLote = {
  ok: boolean
  provider: string
  total: number
  synced: number
  errors: number
  results: { invoice_number: string; status: 'synced' | 'already_synced' | 'error'; error?: string | null }[]
}

// ── Costes de personal (cost_service) ─────────────────────────────────────

/** serialize_country. */
export type PresetDePais = {
  id: string
  organization_id: string | null
  country_code: string
  country_name: string
  currency: string
  employer_cost_pct: number
  productive_hours_year: number
  notes: string | null
  is_default: boolean
}

/** seed_country_presets. */
export type CargaDePresetsDePais = { created: number; updated: number; skipped: number; total: number }

/** serialize_profile. */
export type PerfilDeCoste = {
  id: string
  user_id: string
  country_code: string | null
  currency: string
  gross_annual_salary: number
  employer_cost_pct: number
  extra_annual_costs: number
  productive_hours_year: number
  total_annual_cost: number
  cost_per_hour: number
  valid_from: string | null
  valid_to: string | null
  notes: string | null
  is_active: boolean
  created_at: string | null
}

/** GET /user-costs/summary. */
export type ResumenDeCostes = {
  as_of: string
  users: {
    user_id: string
    full_name: string
    department: string | null
    cost_per_hour: number | null
    source: 'profile' | 'legacy_hourly_rate' | 'none'
  }[]
  total_users: number
  users_with_cost: number
  users_missing_cost: number
  avg_cost_per_hour: number
  truncated: boolean
  limit: number
}

// ── Rentabilidad (profitability_service.calc_project_profitability) ───────

export type RentabilidadCalculada = {
  project_id: string
  project_code: string
  project_name: string
  client_name: string | null
  department: string | null
  status: string
  billing_type: string
  is_billable: boolean
  project_currency: string
  reporting_currency: string
  total_hours: number
  billable_hours: number
  budget_hours: number | null
  hours_used_pct: number | null
  internal_cost: number
  expenses_cost: number
  subcontract_cost: number
  total_cost: number
  billing_revenue: number
  gross_margin: number
  margin_pct: number
  budget_amount: number | null
  contract_amount: number | null
  budget_used_pct: number
  forecast_cost: number
  billing_rate: number | null
  avg_cost_rate: number
  progress_pct: number
  pv: number | null
  ev: number
  ac: number
  cpi: number | null
  spi: number | null
  cv: number
  sv: number | null
  evm_no_schedule: boolean
  eac: number
  etc: number
  vac: number
  margin_at_completion: number
  risk_flag: 'critical' | 'warning' | 'ok'
}

/** GET /profitability/summary. */
export type ResumenDeRentabilidad = {
  projects: RentabilidadCalculada[]
  portfolio: {
    total_revenue: number
    total_cost: number
    total_margin: number
    margin_pct: number
    project_count: number
    billable_projects: number
  }
  /** Periodo libre (16-11-2026): el periodo calculado; null sin periodo (histórico completo). */
  periodo?: Record<string, unknown> | null
}

/** Hito de rentabilidad (profitability._milestone_out). */
export type HitoDeRentabilidad = {
  id: string
  name: string
  description?: string | null
  due_date: string | null
  completed_date: string | null
  billing_amount: number | null
  billing_pct: number | null
  is_billed: boolean
  billed_at: string | null
  is_completed: boolean
  sort_order?: number | null
}

/** GET /profitability/{id}: la rentabilidad con el desglose por persona, semana e hitos. */
export type RentabilidadDetallada = RentabilidadCalculada & {
  by_person: { user_id: string; user_name: string; hours: number; cost: number; billing: number }[]
  by_week: { week: string; hours: number; cost: number }[]
  milestones: HitoDeRentabilidad[]
}

// ── Contratos (contract_service.serialize_contract) ───────────────────────

export type OrdenDeTrabajo = {
  id: string
  code: string
  name: string
  amount: number | null
  hours: number | null
  status: string
  start_date: string | null
  end_date: string | null
}

/** El contrato de servicio con sus órdenes; `hours_used` son las horas imputadas en su vigencia. */
export type ContratoDeServicio = {
  id: string
  code: string
  name: string
  project_id: string
  client_id: string | null
  client_name: string
  client_contact: string | null
  contract_type: 'fixed_price' | 'time_material' | 'retainer' | 'hourly_bag'
  contract_type_label: string
  status: 'draft' | 'active' | 'expired' | 'cancelled'
  total_amount: number | null
  hourly_rate: number | null
  hours_bag: number | null
  hours_used: number
  hours_pct: number | null
  monthly_retainer: number | null
  start_date: string | null
  end_date: string | null
  signed_date: string | null
  payment_terms: string | null
  notes: string | null
  work_orders: OrdenDeTrabajo[]
}

/** POST /contracts/{id}/work-orders. */
export type OrdenDeTrabajoCreada = { id: string; code: string; name: string; status: string }

// ── Contratos IA (ai_modules/contracts.py) ────────────────────────────────

export type EstadoDeContratoIa = 'analyzing' | 'done' | 'failed'

/** list_ai_contracts. */
export type ContratoIa = {
  id: string
  client_name: string | null
  project_id: string | null
  filename: string | null
  status: EstadoDeContratoIa
  total_value: number | null
  risk_level: string | null
  scope_creep_alerts: number | null
  clauses_count: number
  at_risk_clauses: number
  created_at: string
}

export type ClausulaDeContratoIa = {
  id: string
  clause_type: string
  title: string
  description: string | null
  original_text: string | null
  impact_amount: number | null
  due_date: string | null
  is_at_risk: boolean
  risk_reason: string | null
}

/** get_ai_contract. */
export type ContratoIaDetalle = {
  id: string
  client_name: string | null
  project_id: string | null
  filename: string | null
  status: EstadoDeContratoIa
  total_value: number | null
  scope_summary: string | null
  risk_level: string | null
  scope_creep_alerts: number | null
  created_at: string
  clauses: ClausulaDeContratoIa[]
}

/** analyze_contract (texto y PDF). */
export type AnalisisDeContratoIa = {
  contract_id: string
  status: EstadoDeContratoIa
  risk_level: string | null
  scope_summary: string | null
  total_value: number | null
  clauses_count: number
  at_risk_clauses: number | null
  latency_ms: number
}

// ── NexusOracle (ai_modules/predictions.py y oracle.py) ───────────────────

/** list_predictions. */
export type PrediccionDelOraculo = {
  id: string
  type: string
  severity: string
  title: string
  explanation: string | null
  recommended_action: string | null
  probability: number | null
  entity_type: string | null
  entity_id: string | null
  entity_name: string | null
  is_acknowledged: boolean
  created_at: string
  methodology: 'rules_based'
}

/** run_oracle_analysis: `budget_overrun` añade los ratios. */
export type AnalisisDelOraculo = {
  ok: boolean
  methodology: 'rules_based'
  alerts_generated: number
  alerts: {
    type: 'project_delay' | 'sla_breach' | 'burnout' | 'budget_overrun'
    entity: string
    probability: number
    revenue_ratio?: number
    cost_ratio?: number
    margin_eroded?: boolean
  }[]
  run_at: string
}

// ── Escenarios what-if (scenarios_service) ────────────────────────────────

/** list_scenarios. */
export type EscenarioResumen = {
  id: string
  name: string
  description: string | null
  status: string
  horizon_weeks: number
  project_count: number
  creator: string | null
  created_at: string | null
  computed_at: string | null
  has_results: boolean
}

/** compute_scenario (y `results` del detalle). */
export type ResultadoDeEscenario = {
  feasible: boolean
  risk_level: 'low' | 'medium' | 'high'
  avg_utilization_pct: number
  peak_utilization_pct: number
  overloaded_weeks_count: number
  overloaded_weeks: string[]
  total_demand_hours: number
  team_size: number
  weekly_capacity: number
  committed_hours: number
  horizon_weeks: number
  project_breakdown: { name: string; total_hours: number; hours_per_week: number; start: string; end: string; is_existing: boolean }[]
  capacity_timeline: { week: string; demand: number; capacity: number; utilization_pct: number; is_overloaded: boolean }[]
  recommendation: string
}

/** get_scenario. */
export type EscenarioDetalle = {
  id: string
  name: string
  description: string | null
  status: string
  horizon_weeks: number
  base_date: string | null
  computed_at: string | null
  results: ResultadoDeEscenario | null
  projects: { id: string; name: string; start_date: string | null; end_date: string | null; total_hours: number; is_existing: boolean }[]
}

export type EscenarioCreado = { ok: boolean; id: string }

// ── E-firma (GET /esign/config) ───────────────────────────────────────────

export type ClaveDeFirma =
  | 'docusign_integration_key' | 'docusign_account_id' | 'docusign_secret_key' | 'docusign_base_url'
  | 'adobe_sign_client_id' | 'adobe_sign_client_secret' | 'adobe_sign_base_url'

/** Claves en texto (los secretos como '***' o '') y dos indicadores. */
export type ConfigDeFirma = Record<ClaveDeFirma, string> & { docusign_configured: boolean; adobe_configured: boolean }

// ── SmartMatch (app/schemas/billing_reports.py: SmartMatchOut) ────────────

export type CandidatoSmartMatch = {
  user_id: string
  user_name: string
  role: string | null
  department: string | null
  job_title: string | null
  hourly_rate: number
  weekly_capacity: number
  active_tasks: number
  matched_skills: string[]
  missing_skills: string[]
  avg_skill_level: number
  availability_hours: number
  scores: { overall: number; skills: number; availability: number; workload: number; cost: number }
  recommendation: string
}

export type ResultadoSmartMatch = {
  query: { skills: string[]; role: string | null; hours_needed: number; start_date: string | null; end_date: string | null }
  candidates: CandidatoSmartMatch[]
  total_evaluated: number
  message: string
}

// ── Tipos de cambio (currency_rates.py) ───────────────────────────────────

export type TipoDeCambio = {
  id: string
  from_currency: string
  to_currency: string
  rate: number
  effective_date: string
  source: string | null
}

/** POST /currency/rates: `created` o `updated` según si ya existía. */
export type TipoDeCambioGuardado = TipoDeCambio & { created?: true; updated?: true }
