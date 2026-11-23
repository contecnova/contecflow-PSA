/**
 * Tipos de respuesta de ALM, subcontratistas, extensiones de cliente y portal
 * (equipo). Comprobados contra los serializadores del backend que se citan en
 * cada uno. Las listas llegan ya desenvueltas por el interceptor de _core.ts.
 * Columnas con valor por defecto en el modelo se tipan sin `null`.
 */
import type { ClasificacionDeProveedor } from './tipos-proveedores'

/** `{"ok": True, "message": ...}` de los borrados y desvinculados. */
export interface ConfirmacionOk { ok: boolean; message?: string }

// ── ALM (app/core/serializers.py + app/services/alm_service.py) ──────────────

/** get_linked_clients_for_license / _for_contract. */
export interface AlmClienteVinculado { id: string; name: string }

/** VendorSerializer. No envia `tax_id` ni `support_url`. */
export interface AlmProveedor {
  id: string
  name: string
  category: string
  website: string | null
  support_email: string | null
  support_phone: string | null
  account_manager: string | null
  account_number: string | null
  country: string | null
  is_active: boolean
  notes: string | null
  contracts_count: number
}

/** ContractSerializer + `linked_clients` (serialize_contract). */
export interface AlmContrato {
  id: string
  title: string
  reference: string | null
  type: string
  status: string
  vendor_id: string | null
  start_date: string | null
  end_date: string | null
  renewal_date: string | null
  auto_renew: boolean
  notice_days: number | null
  total_value: number | null
  annual_value: number | null
  billing_cycle: string
  currency: string
  payment_method: string | null
  po_number: string | null
  cost_center_id: string | null
  owner_id: string | null
  project_id: string | null
  document_url: string | null
  notes: string | null
  /** CSV. */
  tags: string | null
  resolution_hours: number | null
  response_hours: number | null
  vendor_name: string | null
  owner_name: string | null
  days_to_renewal: number | null
  renewal_urgent: boolean
  licenses_count: number
  linked_clients: AlmClienteVinculado[]
}

/** LicenseSerializer + `linked_clients` (serialize_license). `status` ya viene calculado. */
export interface AlmLicencia {
  id: string
  name: string
  product_name: string | null
  version: string | null
  edition: string | null
  type: string
  platform: string
  status: string
  vendor_id: string | null
  contract_id: string | null
  total_seats: number | null
  expiry_date: string | null
  purchase_date: string | null
  purchase_price: number | null
  annual_cost: number | null
  cost_center_id: string | null
  project_id: string | null
  environment: string
  is_compliance_req: boolean
  notes: string | null
  vendor_name: string | null
  used_seats: number
  available_seats: number | null
  assignments_count: number
  days_to_expiry: number | null
  linked_clients: AlmClienteVinculado[]
  /** Fase 1 (16-11-2026): métrica, niveles, pico, amortización, refacturable y pista de la clave. */
  metric: 'named_user' | 'device' | 'concurrent' | 'volume' | 'site'
  sku: string | null
  tier: string | null
  tier_rank: number | null
  concurrent_peak: number | null
  concurrent_peak_at: string | null
  amortization_months: number | null
  rebillable: boolean
  license_key_hint: string | null
  has_key: boolean
  pending_count: number
}

/** AssetSerializer. */
export interface AlmActivo {
  id: string
  name: string
  type: string
  brand: string | null
  model: string | null
  serial_number: string | null
  asset_tag: string | null
  status: string
  condition: string
  assigned_to_id: string | null
  location: string | null
  department_id: string | null
  project_id: string | null
  vendor_id: string | null
  purchase_date: string | null
  purchase_price: number | null
  currency: string
  warranty_expiry: string | null
  depreciation_years: number | null
  ip_address: string | null
  hostname: string | null
  os: string | null
  cpu: string | null
  ram_gb: number | null
  storage_gb: number | null
  notes: string | null
  ci_id: string | null
  eol_date: string | null
  lease_expiry: string | null
  next_maintenance_date: string | null
  maintenance_contract: string | null
  refresh_ticket_id: string | null
  assigned_to_name: string | null
  vendor_name: string | null
  warranty_expired: boolean
  age_years: number | null
  book_value: number | null
  installed_licenses: number
  ci_name: string | null
  ci_code: string | null
  /** Fase 1 (16-11-2026): titular vigente (asignación), acciones del ciclo de vida, costes y baja. */
  cost_center_id: string | null
  residual_value: number | null
  lease_monthly_cost: number | null
  rebillable: boolean
  disposal_date: string | null
  disposal_reason: string | null
  disposal_method: string | null
  disposal_value: number | null
  current_assignment_id: string | null
  holder_type: 'user' | 'project' | 'department' | 'client' | 'asset' | null
  holder_id: string | null
  holder_name: string | null
  assignment_status: string | null
  assignment_mode: 'assignment' | 'loan' | null
  loan_due: string | null
  loan_overdue: boolean
  actions: string[]
}

/** list_cost_centers_records. */
export interface AlmCentroDeCoste {
  id: string
  code: string
  name: string
  budget_annual: number | null
  currency: string | null
  is_active: boolean
  description: string | null
}

/** create/update_cost_center_record. */
export interface AlmCentroDeCosteGuardado { id: string; code: string; name: string }

/** get_alm_dashboard → `kpis`. */
export interface AlmKpis {
  total_contracts: number
  expiring_soon: number
  total_licenses: number
  expired_licenses: number
  total_assets: number
  assets_in_use: number
  warranty_expiring_90d: number
  total_vendors: number
  annual_license_cost: number
  annual_contract_cost: number
  total_annual_cost: number
  pending_approvals: number
  loans_overdue: number
  acts_pending_signature: number
}

/** get_alm_dashboard. */
export interface AlmPanel { kpis: AlmKpis; upcoming_renewals: AlmContrato[] }

/** assign_license_record: la asignación creada (`Asignacion` de services/api/alm). */
export type AlmAsignacionDeLicencia = import('./alm').Asignacion

/** GET /alm/licenses/{id}: la licencia con sus asignaciones vigentes (y pendientes) e instalaciones. */
export interface AlmLicenciaDetalle extends AlmLicencia {
  assignments: import('./alm').Asignacion[]
  installs: Array<{ id: string; asset_id: string; asset_name: string | null; version: string | null; installed_at: string | null }>
  contract_title: string | null
}

/** GET /alm/assets/{id} (alm_service.get_asset_record): el activo con las licencias instaladas. */
export interface AlmActivoDetalle extends AlmActivo {
  licenses: Array<{ id: string; install_id: string; name: string | null; version: string | null }>
}

/** alm_ciclo_de_vida.historial. */
export interface AlmCambioDeActivo {
  id: string
  field: string
  old_value: string | null
  new_value: string | null
  note: string | null
  user_name: string | null
  changed_at: string | null
}

/** alm_ciclo_de_vida.proximos_vencimientos. */
export interface AlmVencimiento {
  asset_id: string
  name: string
  asset_tag: string | null
  type: string | null
  /** Columna que vence: warranty_expiry, eol_date, lease_expiry o next_maintenance_date. */
  expiry_type: string
  expiry_date: string
  days_remaining: number
  refresh_ticket_id: string | null
}

/** alm_ciclo_de_vida.abrir_ticket_de_renovacion. */
export interface AlmTicketDeRenovacion { ticket_id: string; number: string; created: boolean }

/** get_compliance_report → `issues[]`. */
export interface AlmIncidenciaDeCumplimiento {
  license_id: string
  name: string
  /** EXPIRED | OVERALLOCATED | OVER_PEAK | OVER_INSTALLED (la frase la arma la interfaz). */
  issue: string
  severity: string
  params: Record<string, string | number>
}

/** get_compliance_report. */
export interface AlmCumplimiento { issues: AlmIncidenciaDeCumplimiento[]; total: number; critical: number; warning: number }

// ── Subcontratistas (app/services/enterprise_service/subcontratas.py) ────────

/** serialize_subcontractor → `rates[]`. */
export interface SubTarifa {
  id: string
  description: string | null
  cost_rate: number | null
  sell_rate: number | null
  currency: string | null
  valid_from: string | null
  valid_until: string | null
}

/** serialize_subcontractor. */
export interface Subcontratista {
  id: string
  code: string
  name: string
  company: string | null
  email: string | null
  phone: string | null
  country: string | null
  vat_number: string | null
  currency: string | null
  is_active: boolean
  notes: string | null
  rates: SubTarifa[]
  assignment_count: number
  worker_count: number
  // Proveedores y externalización (19-11-2026, migración 189): `serializar.clasificacion`.
  // Opcionales: respuestas anteriores a la migración (y pruebas) no los traen; sin `kind` es empresa.
  kind?: ClasificacionDeProveedor['kind']
  engagement_modes?: ClasificacionDeProveedor['engagement_modes']
  lifecycle_status?: ClasificacionDeProveedor['lifecycle_status']
  freelancer_worker_id?: string | null
  alm_vendor_id?: string | null
  internal_owner_id?: string | null
  legal_name?: string | null
  website?: string | null
  address?: string | null
  training_enabled?: boolean
  data_access?: boolean
  data_categories?: string | null
  systems_access?: string | null
  risk_level?: ClasificacionDeProveedor['risk_level']
  risk_score?: number | null
  next_review_date?: string | null
  suspended_at?: string | null
  offboarded_at?: string | null
  offboarding_reason?: string | null
}

/** serialize_worker → `skills[]`. */
export interface SubSkillDeTrabajador {
  id: string
  skill_id: string
  skill_name: string | null
  skill_category: string | null
  level: string
  years_experience: number | null
  certified: boolean
  cert_name: string | null
  notes: string | null
}

/** serialize_worker. */
export interface SubTrabajador {
  id: string
  subcontractor_id: string
  user_id: string | null
  login_username: string | null
  name: string
  role: string | null
  email: string | null
  phone: string | null
  cost_rate: number | null
  sell_rate: number | null
  currency: string | null
  available_from: string | null
  available_until: string | null
  weekly_capacity_hours: number | null
  is_active: boolean
  notes: string | null
  skills: SubSkillDeTrabajador[]
  assignment_count: number
  /** Externo como interno: con usuario (login) o solo ficha. */
  has_access: boolean
  /** Fin del acceso (YYYY-MM-DD); por defecto, `available_until`. */
  access_until: string | null
  /** Migración 191: contacto del portal de su proveedor. */
  supplier_portal?: boolean
  /** Responsable interno (obligatorio en el alta). */
  internal_owner_id: string | null
  internal_owner_name: string | null
  /** Nombre del proveedor. */
  company_name: string | null
}

/** create_worker_with_user: el trabajador y la contraseña temporal de su usuario. */
export interface SubTrabajadorCreado extends SubTrabajador { temp_password: string }

/** get_subcontractor_assignments. */
export interface SubAsignacion {
  id: string
  project_id: string
  project_name: string | null
  project_code: string | null
  /** Persona del proveedor asignada (externos como internos). */
  worker_id?: string | null
  worker_name?: string | null
  rate_id?: string | null
  member_role?: string | null
  allocation_pct?: number | null
  rate: { description: string | null; cost_rate: number | null } | null
  /** Horas imputadas por el externo en la hoja de tiempo. */
  hours_imputed?: number | null
  /** Horas del parte manual (externos sin acceso). */
  hours_manual?: number | null
  cost_amount?: number | null
  /** % consumido de las horas contratadas; `alert` al pasar `threshold_pct`. */
  consumption_pct?: number | null
  alert?: boolean
  threshold_pct?: number | null
  is_active?: boolean
  ended_at?: string | null
  po_number: string | null
  po_amount: number | null
  hours_contracted: number | null
  hours_logged: number | null
  budget_used_pct: number | null
  start_date: string | null
  end_date: string | null
  notes: string | null
}

/** get_timelogs. */
export interface SubParteDeHoras {
  id: string
  log_date: string
  hours: number
  description: string | null
  task_reference: string | null
  cost_amount: number | null
  is_invoiced: boolean
  project_id: string | null
  project_name: string | null
  worker_id?: string | null
  worker_name?: string | null
}

/** Fila de `GET /enterprise/subcontractors/{sub_id}/reconciliation`: factura frente a lo imputado. */
export interface SubConciliacion {
  invoice_id: string
  invoice_number: string
  issue_date: string | null
  assignment_id: string | null
  project_name: string | null
  period_from: string | null
  period_to: string | null
  amount: number
  hours_imputed: number
  hours_manual: number
  expected_amount: number
  /** amount - expected_amount: positivo = la factura supera lo imputado. */
  difference: number
  difference_pct: number | null
  currency: string | null
}

/** get_sub_invoices. */
export interface SubFactura {
  id: string
  invoice_number: string
  issue_date: string
  due_date: string | null
  amount: number
  tax_pct: number | null
  total: number
  currency: string | null
  status: string
  paid_date: string | null
  description: string | null
}

/** get_subcontractors_dashboard. */
export interface SubPanel {
  total_active_subs: number
  active_assignments: number
  pending_invoices: number
  total_paid_cost: number
  pending_approval_cost: number
  total_hours_logged: number
}

/** create_subcontractor_assignment / add_worker_skill / create_timelog / create_sub_invoice. */
export interface SubAltaOk {
  ok: boolean
  id?: string
  /** add_worker_skill: la skill ya estaba y se actualizo. */
  updated?: boolean
  /** create_timelog. */
  cost_amount?: number
  /** create_sub_invoice. */
  total?: number
}

/** GET /skills/catalog (endpoints/skills.py get_catalog). */
export interface SkillDelCatalogo {
  id: string
  name: string
  category: string
  category_label: string
  description: string | null
  user_count: number
}

// ── Extensiones de cliente (app/services/client_service.py) ──────────────────

/** client_service.get_client_summary: listado, alta y edicion de `/clients`. */
export interface ClienteResumen {
  id: string
  name: string
  short_name: string | null
  tax_id: string | null
  industry: string | null
  status: string | null
  /** Teléfono y email generales de la EMPRESA. */
  phone: string | null
  email: string | null
  /** Contacto (persona) principal; null si no hay. */
  primary_contact_id: string | null
  /** Reflejo de solo lectura del contacto principal (persona), no datos de la empresa.
   *  `contact_role` es su cargo. */
  contact_name: string | null
  contact_email: string | null
  contact_phone: string | null
  contact_role: string | null
  website: string | null
  address: string | null
  city: string | null
  country: string | null
  account_manager_id: string | null
  account_manager_name: string | null
  payment_terms: string | null
  credit_limit: number | null
  currency: string | null
  notes: string | null
  is_active: boolean
  projects_count: number
  tickets_count: number
  invoices_count: number
  portal_users_count: number
  created_at: string
}

/** client_service.get_client_detail (GET /clients/{id}): el resumen con sus relaciones. */
export interface ClienteDetalle extends ClienteResumen {
  projects: Array<{ id: string; code: string; name: string; status: string; start_date: string | null; end_date: string | null }>
  contacts: Array<{ id: string; full_name: string; email: string | null; phone: string | null; job_title: string | null; role: string; is_primary: boolean }>
  licenses: Array<{ link_id: string; license_id: string; name: string; vendor: string | null; status: string; expiry_date: string | null; total_seats: number | null; notes: string | null }>
  contracts: Array<{ link_id: string; contract_id: string; reference: string | null; title: string | null; status: string; total_amount: number | null; start_date: string | null; end_date: string | null }>
  /** Los 20 más recientes. */
  tickets: Array<{ id: string; code: string; title: string; status: string; priority: string; created_at: string }>
  portal_users: Array<{ id: string; full_name: string; email: string; job_title: string | null; is_active: boolean; project_id: string | null; last_login: string | null }>
  /** _portal_config_out: la guardada o la de por defecto. */
  portal_config: { enabled_modules: string[]; sd_without_project: boolean; sla_tier: string | null; max_portal_users: number | null; max_open_tickets: number | null }
}

/** list_client_projects / list_available_projects. `status` es el valor plano
 *  del enum ("active"); hasta 2026-11 llegaba "ProjectStatus.active". */
export interface ClienteProyecto {
  id: string
  code: string | null
  name: string
  status: string
  client_id: string | null
  is_linked: boolean
  start_date: string | null
  end_date: string | null
}

/** link_project. */
export interface ClienteProyectoVinculado { ok: boolean; project_id: string; client_id: string }

/** add_contact (no envia `notes` ni `is_active`). */
export interface ClienteContactoCreado {
  id: string
  full_name: string
  email: string | null
  phone: string | null
  job_title: string | null
  role: string
  is_primary: boolean
}

/** list_client_licenses. */
export interface ClienteLicencia {
  link_id: string
  license_id: string
  name: string
  status: string
  expiry_date: string | null
  total_seats: number | null
  annual_cost: number | null
  notes: string | null
  linked_at: string
}

/** link_license. */
export interface ClienteLicenciaVinculada { link_id: string; license_id: string; notes: string | null }

/** list_client_contracts: los enlazados (`explicit`, con `link_id`) y los del propio cliente (`direct`, sin el). */
export interface ClienteContrato {
  link_id: string | null
  contract_id: string
  title: string | null
  reference: string | null
  status: string
  total_amount: number | null
  start_date: string | null
  end_date: string | null
  linked_at: string | null
  source: 'explicit' | 'direct'
}

/** link_contract. */
export interface ClienteContratoVinculado { link_id: string; contract_id: string }

/** get_portal_config (sin fila de configuracion solo trae las tres primeras claves). */
export interface ClientePortalConfig {
  client_id: string
  enabled_modules: string[]
  sd_without_project: boolean
  sla_tier?: string | null
  max_portal_users?: number | null
  max_open_tickets?: number | null
  logo_url?: string | null
  accent_color?: string | null
  default_language?: string
  allow_profile_edit?: boolean
  allow_pwd_change?: boolean
}

/** update_portal_config. */
export interface ClientePortalConfigGuardada { ok: boolean; enabled_modules: string[] }

// ── Portal, lado equipo (app/services/client_portal_service/*) ───────────────

/** clientes.list_clients. */
export interface PortalUsuario {
  id: string
  project_id: string | null
  project_ids: string[]
  project_name: string | null
  client_org_id: string | null
  full_name: string
  email: string
  job_title: string | null
  company: string | null
  phone: string | null
  is_active: boolean
  can_approve_deliverables: boolean
  can_request_changes: boolean
  can_view_budget: boolean
  can_view_team: boolean
  last_login: string | null
  created_at: string
  portal_url: string
}

/** clientes.create_client. */
export interface PortalUsuarioCreado { id: string; email: string; project_ids: string[]; portal_url: string; message: string; /** 23-11-2026: null si se dio la contraseña a mano (API). */ credenciales_enviadas?: boolean | null }

/** clientes.update_client. */
export interface PortalUsuarioActualizado { ok: boolean; project_ids: string[] }

/** GET /portal/translations (branding_service.traducciones_del_portal): idioma → clave → texto. */
export type PortalTraducciones = Record<string, Record<string, string>>

/** portal_conversation_service/politicas.py `_policy_out`. */
export interface PortalPoliticaDeConversacion {
  id: string
  organization_id: string
  topic_type: string
  is_active: boolean
  requires_client_message_approval: boolean
  requires_team_message_approval: boolean
  redact_sensitive_content: boolean
  allow_legacy_federation: boolean
  assignment_mode: string
  default_group_id: string | null
  default_role_key: string | null
  first_response_hours: number | null
  escalation_hours: number | null
  approval_role_key: string | null
  approval_user_id: string | null
  sensitive_keywords: string[]
}

/** portal_conversation_service/serializacion.py `_message_out` / `_legacy_message_out` (mismas claves). */
export interface PortalMensajeDeConversacion {
  id: string
  source: 'native' | 'legacy_client_message'
  conversation_id: string
  project_id: string | null
  parent_message_id: string | null
  sender_type: 'team' | 'client' | 'system'
  sender_name: string
  sender_user_id: string | null
  sender_client_id: string | null
  message_type: string
  body: string
  raw_body: string | null
  is_internal_note: boolean
  classification: string
  grc_status: string
  is_redacted: boolean
  moderation_notes: string | null
  approval_request_id: string | null
  legacy_message_id: string | null
  created_at: string
  delivered_at: string | null
  read_at: string | null
}

/** serializacion._uat_test_cases_out. */
export interface PortalCasoDePrueba {
  id: string
  title: string
  steps: string | null
  expected_result: string | null
  actual_result: string | null
  status: string
  notes: string | null
  order: number | null
}

/** serializacion._uat_issues_out. */
export interface PortalIncidenciaUat {
  id: string
  title: string
  description: string | null
  severity: string
  status: string
  steps_to_reproduce: string | null
}

/** serializacion.uat_out (+ `project_name` en uat.list_uat_team). */
export interface PortalSesionUat {
  id: string
  code: string
  project_id: string
  deliverable_id: string | null
  title: string
  description: string | null
  test_environment: string | null
  test_credentials: string | null
  test_guide_url: string | null
  status: string
  status_label: string
  status_color: string
  available_from: string | null
  deadline: string | null
  completed_at: string | null
  client_result: string | null
  client_notes: string | null
  test_cases: PortalCasoDePrueba[]
  issues: PortalIncidenciaUat[]
  issues_count: number
  stats: { total: number; passed: number; failed: number; pending: number }
  overdue: boolean | null
  /** Solo en el listado del equipo. */
  project_name?: string
}

/** serializacion.fr_out (+ `client_name` y el detalle de la CR en peticiones.list_all_feature_requests). */
export interface PortalPeticion {
  id: string
  code: string
  project_id: string
  project_name: string
  client_id: string | null
  title: string
  description: string | null
  business_justification: string | null
  affected_area: string | null
  priority: string
  priority_label: string
  priority_color: string
  status: string
  status_label: string
  status_color: string
  pm_response: string | null
  estimated_hours: number | null
  estimated_cost: number | null
  estimated_delivery_weeks: number | null
  client_approved: boolean | null
  client_approved_at: string | null
  submitted_at: string | null
  updated_at: string | null
  change_request_id: string | null
  cr_status: string | null
  cr_status_label: string | null
  cr_status_color: string | null
  // Solo en el listado del equipo:
  client_name?: string
  impact?: string | null
  impact_label?: string | null
  cost_impact?: number | null
  schedule_impact_days?: number | null
  resolution_notes?: string | null
  approved_at?: string | null
  implemented_at?: string | null
}

/** serializacion.doc_out. */
export interface PortalDocumento {
  id: string
  title: string
  description: string | null
  category: string
  category_label: string
  file_url: string | null
  file_name: string | null
  file_size_kb: number | null
  requires_signature: boolean
  signed_by_client: boolean
  is_visible_to_client: boolean
  signed_at: string | null
  created_at: string
}

/** panel.get_portal_stats (+ _portal_stats_survey_aggregates). */
export interface PortalEstadisticas {
  client_count: number
  unread_messages: number
  fr_pending_review: number
  uat_pending: number
  survey_count: number
  avg_nps: number | null
  avg_satisfaction: number | null
}

/** uat.add_test_case. */
export interface PortalCasoCreado { id: string; title: string }

// ── Otros ─────────────────────────────────────────────────────────────────────

/** deliverable_service.serialize_deliverable. */
export interface Entregable {
  id: string
  code: string
  project_id: string
  phase_id: string | null
  name: string
  description: string | null
  format: string | null
  status: string
  status_label: string
  status_color: string
  status_icon: string
  planned_date: string | null
  delivered_date: string | null
  accepted_date: string | null
  owner_id: string | null
  owner_name: string | null
  client_contact: string | null
  acceptance_criteria: string | null
  rejection_reason: string | null
  milestone_id: string | null
  document_url: string | null
  sort_order: number | null
  on_time: boolean | null
  overdue: boolean | null
}

/** GET /deliverables/{project_id} (endpoints/deliverables.py get_deliverables). */
export interface EntregablesDelProyecto {
  deliverables: Entregable[]
  summary: { total: number; accepted: number; delivered: number; overdue: number; completion_pct: number }
}

/** epics_service.list_wiki_spaces. */
export interface WikiEspacio {
  id: string
  name: string
  slug: string
  description: string | null
  project_id: string | null
  is_public: boolean
  page_count: number
  created_at: string | null
}

/** POST /epics/wiki/spaces (epics_service.create_wiki_space). */
export interface WikiEspacioCreado { id: string; name: string; slug: string; project_id: string | null }

/** Quién ve la página (`WikiPageVisibilityIn`). */
export type VisibilidadDeWiki = 'team' | 'portal' | 'public'

/** epics_service.serialize_page (también PATCH /wiki/pages/{id}/visibility). */
export interface WikiPaginaResumen {
  id: string
  space_id: string
  parent_id: string | null
  title: string
  slug: string
  is_published: boolean
  sort_order: number | null
  visibility: VisibilidadDeWiki
  created_by: string | null
  updated_by: string | null
  created_at: string | null
  updated_at: string | null
}

/** epics_service.build_page_tree (GET /wiki/spaces/{id}/pages): arbol con `children`. */
export interface WikiPaginaEnArbol extends WikiPaginaResumen {
  children: WikiPaginaEnArbol[]
}

/**
 * Bloque del editor. El backend guarda la lista tal cual (`WikiPageIn.content: List`)
 * y solo lee `content` de cada bloque para el texto buscable (blocks_to_text).
 */
export interface WikiBloque { type: string; content?: string }

/** epics_service.serialize_page_full: detalle, alta y edicion. */
export interface WikiPagina extends WikiPaginaResumen {
  content: WikiBloque[]
  content_text: string
}

/** epics_service.list_page_versions. */
export interface WikiVersion {
  id: string
  version_num: number
  title: string
  change_note: string | null
  created_by: string | null
  created_at: string | null
}

/** POST /wiki/pages/{id}/restore/{n} (epics_service.restore_wiki_version). */
export interface WikiRestauracion { restored: boolean; new_version: number }

/** GET /wiki/search (epics_service.search_wiki_pages). */
export interface WikiResultadoDeBusqueda {
  id: string
  title: string
  space_id: string
  slug: string
  updated_at: string | null
}

/** GET /cmdb/wiki-tags/{space} (cmdb_service.list_wiki_tags). */
export interface WikiEtiqueta { id: string; name: string; color: string; page_count: number }

/** POST/PATCH /cmdb/wiki-tags (cmdb_service.create_wiki_tag / update_wiki_tag). */
export interface WikiEtiquetaGuardada { id: string; name: string; color: string }

/** GET /ws/ticket (endpoints/ws.py get_ws_ticket). */
export interface TicketDeWebSocket { ticket: string; expires_in: number }

/** Factura de `GET /clients/{cid}/invoices` (client_service.list_client_invoices). El importe llega como `total_amount`. */
export interface FacturaDeCliente {
  id: string
  number: string | null
  status: 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled' | string
  issue_date: string | null
  due_date: string | null
  total_amount: number | null
  project_id: string | null
  project_name: string | null
  client_name: string | null
}
