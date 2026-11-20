/**
 * Tipos de `/suppliers` (proveedores y externalización, 19-11-2026, migración 189).
 *
 * Formas comprobadas contra `app/services/proveedores/serializar.py` (entidades)
 * y las respuestas calculadas documentadas en docs/PROVEEDORES_Y_EXTERNALIZACION.md §9.
 * Entradas: `app/schemas/proveedores.py`.
 */
import type { SubTrabajador, Subcontratista } from './tipos-alm'

export type TipoDeProveedor = 'freelance' | 'company'
export type ModoDeRelacion = 'staff_augmentation' | 'outsourcing' | 'managed_services'
export type CicloDeVida = 'onboarding' | 'active' | 'suspended' | 'offboarded'
export type ModeloDeCobro = 'per_resource' | 'fixed_price' | 'per_unit' | 'subscription' | 'expense' | 'bonus'
export type PeriodoDeCobro = 'monthly' | 'quarterly' | 'annual' | 'one_time'
export type TipoDeContratoProveedor = 'msa' | 'sow' | 'service' | 'framework' | 'freelance'
export type EstadoDeContratoProveedor = 'draft' | 'active' | 'suspended' | 'expired' | 'terminated'
export type AlcanceDePaquete = 'project' | 'phase' | 'milestone' | 'deliverable' | 'tasks'
export type EstadoDePaquete = 'planned' | 'in_progress' | 'delivered' | 'accepted' | 'rejected' | 'cancelled'
export type TipoDeDocumentoProveedor =
  | 'dpa_art28' | 'nda' | 'iso27001' | 'soc2' | 'ens' | 'insurance_liability' | 'insurance_cyber'
  | 'security_questionnaire' | 'due_diligence' | 'tax_certificate' | 'social_security_certificate' | 'other'
export type NivelDeAcceso = 'read' | 'write' | 'admin'
export type NivelDeRiesgoProveedor = 'low' | 'medium' | 'high' | 'critical'
export type CriterioDeRiesgo = 'data_access' | 'criticality' | 'dependency' | 'financial' | 'location' | 'security'
export type EstadoDeServicioProveedor = 'active' | 'paused' | 'ended'
export type EstadoDeCuentaProveedor = 'closed' | 'reconciled' | 'pending_approval' | 'disputed' | 'approved'
/** Migración 191: tipos de informe, fuentes de medición, agregación y qué cuenta la CMDB. */
export type TipoDeInforme = 'progress' | 'periodic' | 'service_log' | 'sla_evidence'
export type FuenteDeMedicion = 'manual' | 'cmdb' | 'external'
export type AgregacionDeMedicion = 'last' | 'max' | 'average'
export type CuentaDeMedicion = 'devices' | 'owners'
export type EstadoDeCumplimiento = 'ok' | 'attention' | 'blocked'
export type AQuienSeAsigna = 'person' | 'supplier' | 'person_and_supplier' | 'none'
export type TonoDePuntuacion = 'ok' | 'warning' | 'critical' | string

/** Campos de clasificación que `serializar.clasificacion` añade a la ficha del subcontratista. */
export interface ClasificacionDeProveedor {
  kind: TipoDeProveedor
  engagement_modes: ModoDeRelacion[]
  lifecycle_status: CicloDeVida
  freelancer_worker_id: string | null
  alm_vendor_id: string | null
  internal_owner_id: string | null
  legal_name: string | null
  website: string | null
  address: string | null
  training_enabled: boolean
  data_access: boolean
  data_categories: string | null
  systems_access: string | null
  risk_level: NivelDeRiesgoProveedor | null
  risk_score: number | null
  next_review_date: string | null
  suspended_at: string | null
  offboarded_at: string | null
  offboarding_reason: string | null
}

/** `GET /suppliers/meta`: listas de claves. */
export interface MetaDeProveedores {
  kinds: TipoDeProveedor[]
  modes: ModoDeRelacion[]
  lifecycle: CicloDeVida[]
  contract_types: TipoDeContratoProveedor[]
  contract_statuses: EstadoDeContratoProveedor[]
  pricing_models: ModeloDeCobro[]
  periods: PeriodoDeCobro[]
  scope_types: AlcanceDePaquete[]
  work_package_statuses: EstadoDePaquete[]
  document_types: TipoDeDocumentoProveedor[]
  access_levels: NivelDeAcceso[]
  risk_criteria: CriterioDeRiesgo[]
  risk_levels: NivelDeRiesgoProveedor[]
  auto_units: string[]
  /** Migración 191. */
  report_types?: TipoDeInforme[]
  statement_statuses?: EstadoDeCuentaProveedor[]
  metering_sources?: FuenteDeMedicion[]
  metering_aggregations?: AgregacionDeMedicion[]
  metering_counts?: CuentaDeMedicion[]
  metered_units?: string[]
}

/** `GET /suppliers/overview`. */
export interface PanoramaDeProveedores {
  by_kind: Record<TipoDeProveedor, number>
  by_mode: Record<ModoDeRelacion, number>
  by_lifecycle: Record<CicloDeVida, number>
  documents_expiring: number
  documents_expired: number
  reviews_overdue: number
  statements_disputed: number
  statements_pending_approval: number
  forecast_month: number
  currency: string | null
}

export interface PaqueteAsignable { id: string; title: string; project_id: string; status: EstadoDePaquete }
/** `GET /suppliers/assignable?project_id=`. */
export interface ProveedorAsignable {
  id: string
  code: string | null
  name: string
  kind: TipoDeProveedor
  work_packages: PaqueteAsignable[]
}

/** `POST /suppliers/freelance`. */
export interface FreelanceCreado {
  supplier: Subcontratista
  worker: SubTrabajador
  login_username: string | null
  temp_password?: string | null
}

/** `GET /suppliers/{id}/profile`. */
export type FichaDeProveedor = Subcontratista & {
  workers: SubTrabajador[]
  counts: { contracts_active: number; services_active: number; work_packages_open: number; statements_pending: number }
  compliance: { status: EstadoDeCumplimiento; missing: TipoDeDocumentoProveedor[]; expiring: DocumentoDeProveedor[] }
  scorecard: { score: number | null; tone: TonoDePuntuacion }
  assign_to: AQuienSeAsigna
}

/** Tramo de escalado por volumen. */
export interface TramoDePrecio { from: number; to: number | null; price: number }

/** `serializar.linea`. */
export interface LineaDePrecio {
  id: string
  contract_id: string
  model: ModeloDeCobro
  unit: string | null
  description: string | null
  rate_id: string | null
  rate_description: string | null
  service_id: string | null
  work_package_id: string | null
  unit_price: number | null
  period: PeriodoDeCobro | null
  included_units: number | null
  overage_price: number | null
  tiers: TramoDePrecio[]
  min_amount: number | null
  max_amount: number | null
  valid_from: string | null
  valid_until: string | null
  is_active: boolean
}

/** `serializar.contrato` (también las plantillas, `is_template`). */
export interface ContratoDeProveedor {
  id: string
  subcontractor_id: string | null
  is_template: boolean
  code: string | null
  title: string
  contract_type: TipoDeContratoProveedor
  modes: ModoDeRelacion[]
  status: EstadoDeContratoProveedor
  start_date: string | null
  end_date: string | null
  auto_renew: boolean
  notice_days: number | null
  currency: string | null
  committed_minimum: number | null
  minimum_period: PeriodoDeCobro | null
  total_cap: number | null
  po_number: string | null
  po_amount: number | null
  budget_id: string | null
  project_id: string | null
  cost_center_id: string | null
  payment_terms_days: number | null
  expenses_rebillable: boolean
  expenses_cap: number | null
  internal_owner_id: string | null
  document_url: string | null
  notes: string | null
  terminated_at: string | null
  created_at: string | null
  lines?: LineaDePrecio[]
}

export interface KpiDeServicio { key: string; label: string; target: number | null; unit: string | null; direction: 'higher' | 'lower' }
export interface ReglaDeCredito { below_pct: number; credit_pct: number }
export interface ReglaDeBonus { above_pct: number; bonus_pct: number }

/** `serializar.servicio`. */
export interface ServicioDeProveedor {
  id: string
  subcontractor_id: string
  contract_id: string | null
  service_type: string
  name: string
  scope: string | null
  status: EstadoDeServicioProveedor
  start_date: string | null
  end_date: string | null
  agent_group_id: string | null
  service_item_id: string | null
  alm_contract_id: string | null
  sla_response_hours: number | null
  sla_resolution_hours: number | null
  sla_target_pct: number | null
  kpis: KpiDeServicio[]
  contracted_units: number | null
  unit: string | null
  reporting_frequency: 'weekly' | 'monthly' | 'quarterly' | null
  credit_rules: ReglaDeCredito[]
  bonus_rules: ReglaDeBonus[]
  internal_owner_id: string | null
  notes: string | null
  /** Migración 191: fuente de medición de dispositivos/usuarios. */
  metering_source: FuenteDeMedicion
  metering_config: ConfigDeMedicion
  metering_last_at: string | null
  metering_last_quantity: number | null
  metering_last_error: string | null
}

/** Configuración de la fuente de medición (`proveedores.medicion`). */
export interface ConfigDeMedicion {
  ci_types?: string[]
  ci_classes?: string[]
  environment?: string | null
  vendor?: string | null
  location?: string | null
  project_id?: string | null
  software_product_id?: string | null
  seen_within_days?: number | null
  count?: CuentaDeMedicion
  system?: string | null
  aggregation?: AgregacionDeMedicion
}

/** `POST /suppliers/metering/preview` y el detalle de `medir`. */
export interface VistaPreviaDeMedicion { quantity: number; detail: { examples?: string[]; count?: string; filters?: Record<string, unknown> } }

/** `POST /suppliers/services/{sid}/metering/measure`. */
export interface MedicionHecha { service: ServicioDeProveedor; usage: ConsumoDeProveedor; detail: VistaPreviaDeMedicion['detail'] }

/** `POST /suppliers/{id}/metering/import`. */
export interface ResultadoDeImportacionDeRecuentos {
  imported: number
  failed: number
  rows: { row: number; ok: boolean; usage_id?: string; quantity?: number; code?: string | null; error?: string }[]
}
export interface RecuentoIn { quantity?: number | null; items?: string[] | null; as_of?: string | null; system?: string | null }
export interface FilaDeRecuento extends RecuentoIn { service_id: string }

/** `GET /suppliers/references`: datos reales para los selectores de la ficha. */
export interface OpcionDeReferencia { id: string; label: string; [k: string]: unknown }
export interface ReferenciasDeProveedores {
  budgets: OpcionDeReferencia[]
  cost_centers: OpcionDeReferencia[]
  alm_contracts: (OpcionDeReferencia & { same_vendor: boolean })[]
  service_items: OpcionDeReferencia[]
  uat_sessions: OpcionDeReferencia[]
  ci_types: string[]
  ci_classes: OpcionDeReferencia[]
  software_products: OpcionDeReferencia[]
}

/** Contacto del portal del proveedor (`GET /suppliers/{id}/portal-contacts`). */
export interface ContactoDelPortal {
  worker_id: string
  name: string
  email: string | null
  has_access: boolean
  access_until: string | null
  supplier_portal: boolean
  user_id: string | null
}

/** Adjunto (evidencia) de un informe. */
export interface AdjuntoDeInforme {
  kind: 'file' | 'link'
  name: string
  url?: string
  document_id?: string
  size?: number
  mime?: string
  uploaded_at?: string
  via?: 'internal' | 'portal'
}

/** `GET /supplier-portal/me`. */
export interface PortalYo {
  enabled: boolean
  can_write?: boolean
  supplier?: { id: string; name: string; kind: TipoDeProveedor; engagement_modes: ModoDeRelacion[]; lifecycle_status: CicloDeVida; currency: string | null }
  person?: { id: string; name: string; access_until: string | null }
  report_types?: TipoDeInforme[]
}

/** `GET /supplier-portal/usage`. */
export interface ConsumoDelPortal {
  period_start: string
  period_end: string
  contracts: {
    contract_id: string; title: string; code: string | null; currency: string | null
    lines: Pick<LineaDePrevision, 'model' | 'unit' | 'description' | 'quantity' | 'unit_price' | 'amount' | 'source' | 'service_id'>[]
    subtotal: number; credits: number; bonus: number; adjustments: number; expected_amount: number
  }[]
  usage: Pick<ConsumoDeProveedor, 'id' | 'contract_id' | 'service_id' | 'period_start' | 'period_end' | 'unit' | 'quantity' | 'amount' | 'source' | 'source_system' | 'description'>[]
}

/** `GET /suppliers/services/{sid}/sla`. */
export interface SlaDeServicio {
  service_id: string
  period_start: string
  period_end: string
  tickets_total: number
  tickets_resolved: number
  response_met_pct: number | null
  resolution_met_pct: number | null
  compliance_pct: number | null
  target_pct: number | null
  met: boolean | null
  breaches_response: number
  breaches_resolution: number
}

/** `serializar.paquete`. */
export interface PaqueteDeTrabajo {
  id: string
  subcontractor_id: string
  contract_id: string | null
  project_id: string
  project_name: string | null
  scope_type: AlcanceDePaquete
  phase_id: string | null
  milestone_id: string | null
  deliverable_id: string | null
  uat_session_id: string | null
  title: string
  description: string | null
  acceptance_criteria: string | null
  status: EstadoDePaquete
  planned_start: string | null
  planned_end: string | null
  delivered_at: string | null
  accepted_at: string | null
  accepted_by: string | null
  rejection_reason: string | null
  rejections: number
  price: number | null
  currency: string | null
  progress_pct: number | null
  last_report_at: string | null
  internal_owner_id: string | null
  task_count: number | null
}

/** `GET /suppliers/by-project/{project_id}`. */
export interface ExternalizadoDelProyecto {
  work_packages: PaqueteDeTrabajo[]
  tasks: { id: string; code: string | null; title: string; status: string; supplier_id: string; supplier_name: string | null; supplier_work_package_id: string | null }[]
}

/** `serializar.informe`. */
export interface InformeDeProveedor {
  id: string
  subcontractor_id: string
  work_package_id: string | null
  service_id: string | null
  period_start: string | null
  period_end: string | null
  progress_pct: number | null
  summary: string
  kpi_values: Record<string, unknown>
  risks: string | null
  /** Migración 191. */
  report_type: TipoDeInforme
  attachments: AdjuntoDeInforme[]
  submitted_via: 'internal' | 'portal'
  status: 'submitted' | 'reviewed'
  submitted_by: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  review_notes: string | null
  created_at: string | null
}

/** `serializar.consumo`. */
export interface ConsumoDeProveedor {
  id: string
  subcontractor_id: string
  contract_id: string | null
  pricing_line_id: string | null
  service_id: string | null
  project_id: string | null
  period_start: string
  period_end: string
  unit: string | null
  quantity: number
  amount: number | null
  source: 'manual' | 'import' | 'cmdb' | 'api'
  description: string | null
  statement_id: string | null
  created_at: string | null
  /** Migración 191: muestras del recuento (máximo, media, último) y sistema de origen. */
  detail?: { samples?: { date: string; quantity: number }[]; max?: number; min?: number; average?: number; last?: number; aggregation?: AgregacionDeMedicion; system?: string | null }
  source_system?: string | null
}

/** Línea calculada de la previsión (y del detalle del estado de cuenta). */
export interface LineaDePrevision {
  pricing_line_id: string | null
  model: ModeloDeCobro
  unit: string | null
  description: string | null
  quantity: number
  unit_price: number | null
  amount: number
  project_id: string | null
  source: string | null
  detail: unknown
  /** Servicio al que pertenece la línea (créditos, bonus y líneas de servicio). */
  service_id: string | null
}

export interface AvisoDePrevision { code: string; params?: Record<string, unknown> | null }

/** `GET /suppliers/contracts/{cid}/forecast`. */
export interface PrevisionDeContrato {
  contract_id: string
  period_start: string
  period_end: string
  currency: string | null
  lines: LineaDePrevision[]
  subtotal: number
  credits: number
  bonus: number
  adjustments: number
  expected_amount: number
  warnings: AvisoDePrevision[]
}

/** `serializar.estado_de_cuenta`. */
export interface EstadoDeCuenta {
  id: string
  subcontractor_id: string
  contract_id: string
  contract_title: string | null
  period_start: string
  period_end: string
  currency: string | null
  lines: LineaDePrevision[]
  subtotal: number
  credits: number
  bonus: number
  adjustments: number
  expected_amount: number
  status: EstadoDeCuentaProveedor
  invoice_id: string | null
  invoice_amount: number | null
  difference: number | null
  difference_pct: number | null
  dispute_reason: string | null
  closed_by: string | null
  approved_by: string | null
  approved_at: string | null
  created_at: string | null
  /** Migración 191: solicitud de la bandeja de aprobaciones (tipo `supplier_statement`). */
  approval_request_id?: string | null
}

/** `serializar.documento`. */
export interface DocumentoDeProveedor {
  id: string
  subcontractor_id: string
  doc_type: TipoDeDocumentoProveedor
  reference: string | null
  issuer: string | null
  issued_at: string | null
  expires_at: string | null
  coverage_amount: number | null
  document_url: string | null
  notes: string | null
  verified_by: string | null
  verified_at: string | null
  /** `grc.estado_de_documento`: vigente, por caducar, caducado… */
  status: string
}

/** `serializar.evaluacion`. */
export interface EvaluacionDeRiesgo {
  id: string
  subcontractor_id: string
  assessed_at: string
  assessed_by: string | null
  criteria: Partial<Record<CriterioDeRiesgo, number>>
  score: number
  level: NivelDeRiesgoProveedor
  next_review_date: string | null
  due_diligence_done: boolean
  notes: string | null
}

/** `serializar.acceso`. */
export interface AccesoDeProveedor {
  id: string
  subcontractor_id: string
  worker_id: string | null
  system: string
  data_category: string | null
  access_level: NivelDeAcceso
  personal_data: boolean
  justification: string | null
  granted_at: string
  granted_by: string | null
  expires_at: string | null
  revoked_at: string | null
  revoked_by: string | null
  revoke_reason: string | null
  active: boolean
}

/** `GET /suppliers/{id}/compliance`. */
export interface CumplimientoDeProveedor {
  status: EstadoDeCumplimiento
  required: TipoDeDocumentoProveedor[]
  missing: TipoDeDocumentoProveedor[]
  expiring: DocumentoDeProveedor[]
  documents: DocumentoDeProveedor[]
  latest_assessment: EvaluacionDeRiesgo | null
  assessments_count: number
  review_overdue: boolean
  access_grants: AccesoDeProveedor[]
}

export type DimensionDePuntuacion = 'sla' | 'on_time' | 'acceptance' | 'billing' | 'compliance' | 'hours'

/** `GET /suppliers/{id}/scorecard`. */
export interface PuntuacionDeProveedor {
  subcontractor_id: string
  period_start: string
  period_end: string
  score: number | null
  tone: TonoDePuntuacion
  dimensions: { key: DimensionDePuntuacion; value: number | null; weight: number; detail: unknown }[]
}

// ── Entradas (app/schemas/proveedores.py) ────────────────────────────────────

export interface ClasificacionIn {
  kind?: TipoDeProveedor | null
  engagement_modes?: ModoDeRelacion[] | null
  training_enabled?: boolean | null
  alm_vendor_id?: string | null
  internal_owner_id?: string | null
  legal_name?: string | null
  website?: string | null
  address?: string | null
  data_access?: boolean | null
  data_categories?: string | null
  systems_access?: string | null
}

export interface AltaDeFreelanceIn {
  name: string
  email?: string | null
  phone?: string | null
  vat_number?: string | null
  country?: string | null
  currency?: string | null
  role?: string | null
  cost_rate?: number | null
  sell_rate?: number | null
  weekly_capacity_hours?: number | null
  available_from?: string | null
  available_until?: string | null
  internal_owner_id: string
  has_access: boolean
  access_until?: string | null
  engagement_modes?: ModoDeRelacion[] | null
  training_enabled: boolean
  notes?: string | null
}

export type ContratoIn = Partial<Omit<ContratoDeProveedor, 'id' | 'subcontractor_id' | 'is_template' | 'status' | 'terminated_at' | 'created_at' | 'lines'>>
export type LineaIn = Partial<Omit<LineaDePrecio, 'id' | 'contract_id' | 'rate_description'>>
export type ServicioIn = Partial<Omit<ServicioDeProveedor, 'id' | 'subcontractor_id'>>
export type PaqueteIn = Partial<Pick<PaqueteDeTrabajo,
  'project_id' | 'contract_id' | 'scope_type' | 'phase_id' | 'milestone_id' | 'deliverable_id' | 'uat_session_id' | 'title' |
  'description' | 'acceptance_criteria' | 'planned_start' | 'planned_end' | 'price' | 'currency' | 'progress_pct' | 'internal_owner_id'>>
export interface InformeIn {
  work_package_id?: string | null
  service_id?: string | null
  report_type?: TipoDeInforme | null
  attachments?: { name?: string | null; url: string }[] | null
  period_start?: string | null
  period_end?: string | null
  progress_pct?: number | null
  summary: string
  kpi_values?: Record<string, unknown> | null
  risks?: string | null
}
export interface ConsumoIn {
  contract_id?: string | null
  pricing_line_id?: string | null
  service_id?: string | null
  project_id?: string | null
  period_start: string
  period_end: string
  unit?: string | null
  quantity: number
  amount?: number | null
  source?: 'manual' | 'import'
  description?: string | null
}
export interface DocumentoIn {
  doc_type?: TipoDeDocumentoProveedor
  reference?: string | null
  issuer?: string | null
  issued_at?: string | null
  expires_at?: string | null
  coverage_amount?: number | null
  document_url?: string | null
  notes?: string | null
  verified?: boolean | null
}
export interface EvaluacionIn {
  criteria: Partial<Record<CriterioDeRiesgo, number>>
  due_diligence_done?: boolean
  notes?: string | null
  assessed_at?: string | null
}
export interface AccesoIn {
  worker_id?: string | null
  system: string
  data_category?: string | null
  access_level?: NivelDeAcceso
  personal_data?: boolean
  justification?: string | null
  granted_at?: string | null
  expires_at?: string | null
}
