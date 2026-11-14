/**
 * Tipos de respuesta de ALM, subcontratistas, extensiones de cliente y portal
 * (equipo). Comprobados contra los serializadores del backend que se citan en
 * cada uno. Las listas llegan ya desenvueltas por el interceptor de _core.ts.
 * Columnas con valor por defecto en el modelo se tipan sin `null`.
 */

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
}

/** get_alm_dashboard. */
export interface AlmPanel { kpis: AlmKpis; upcoming_renewals: AlmContrato[] }

/** assign_license_record. */
export interface AlmAsignacionDeLicencia { id: string; license_id: string; user_id: string | null }

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
  /** EXPIRED | OVERALLOCATED. */
  issue: string
  severity: string
  detail: string
}

/** get_compliance_report. */
export interface AlmCumplimiento { issues: AlmIncidenciaDeCumplimiento[]; total: number; critical: number }

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
}

/** create_worker_with_user: el trabajador y la contraseña temporal de su usuario. */
export interface SubTrabajadorCreado extends SubTrabajador { temp_password: string }

/** get_subcontractor_assignments. */
export interface SubAsignacion {
  id: string
  project_id: string
  project_name: string | null
  project_code: string | null
  rate: { description: string | null; cost_rate: number | null } | null
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
export interface PortalUsuarioCreado { id: string; email: string; project_ids: string[]; portal_url: string; message: string }

/** clientes.update_client. */
export interface PortalUsuarioActualizado { ok: boolean; project_ids: string[] }

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

/** epics_service.serialize_page dentro de build_page_tree (arbol: `children`). No envia `visibility`. */
export interface WikiPaginaEnArbol {
  id: string
  space_id: string
  parent_id: string | null
  title: string
  slug: string
  is_published: boolean
  sort_order: number | null
  created_by: string | null
  updated_by: string | null
  created_at: string | null
  updated_at: string | null
  children: WikiPaginaEnArbol[]
}

/** GET /ws/ticket (endpoints/ws.py get_ws_ticket). */
export interface TicketDeWebSocket { ticket: string; expires_in: number }
