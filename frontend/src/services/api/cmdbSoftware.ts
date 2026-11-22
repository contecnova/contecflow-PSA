/**
 * services/api/cmdbSoftware.ts — CMDB de software, composición y vulnerabilidades (19-11-2026).
 *
 * API `/cmdb/software/*` (app/api/v1/endpoints/cmdb_software.py). Diseño:
 * docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md. El interceptor de `_core` ya
 * desenvuelve `{ data, meta }` y `{ items, meta }`: `r.data` es el contenido
 * y, en listas, `r.meta.total` el total.
 */
import api from './_core'

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const L = <T,>(p: Promise<{ data: unknown; meta?: unknown }>) =>
  p.then(r => ({ items: (r.data ?? []) as T[], total: Number((r.meta as { total?: number } | undefined)?.total ?? (r.data as unknown[] | undefined)?.length ?? 0) }))

export type Severidad = 'critical' | 'high' | 'medium' | 'low' | 'none' | 'unknown'
export type EstadoHallazgo = 'open' | 'triaged' | 'in_progress' | 'mitigated' | 'resolved' | 'false_positive' | 'accepted'
export type CicloDeVidaEstado = 'eol' | 'unsupported' | 'soon' | null

export interface MetaSoftware {
  categories: string[]; origins: string[]; criticalities: string[]; lifecycles: string[]; distributions: string[]
  environments: string[]; instance_statuses: string[]; exposures: string[]; relations: string[]
  component_relations: string[]; scopes: string[]; baseline_ops: string[]; config_formats: string[]
  sbom_formats: string[]; license_families: string[]; finding_statuses: EstadoHallazgo[]; severities: Severidad[]
  sources: string[]; csv_columns: string[]
}

export interface ProductoSw {
  id: string; name: string; category: string; origin: string; vendor_name: string | null; alm_vendor_id: string | null
  description: string | null; purl_type: string | null; purl_namespace: string | null; purl_name: string | null
  purl: string | null; cpe_vendor: string | null; cpe_product: string | null; cpe: string | null; match_key: string
  aliases: string[]; license_spdx: string | null; homepage: string | null; repository_url: string | null
  owner_user_id: string | null; owner_name?: string | null; project_id: string | null; service_ci_id: string | null
  criticality: string; distribution: string | null; lifecycle_status: string; tags: string[]; notes: string | null
  is_active: boolean; created_at: string | null; updated_at: string | null
  // En el listado
  versions_count?: number; instances_count?: number; machines_count?: number; used_in_count?: number
  open_findings?: number; worst_severity?: Severidad | null
}
export type ProductoSwIn = Partial<Omit<ProductoSw, 'id' | 'purl' | 'cpe' | 'match_key'>> & { purl?: string | null; cpe?: string | null }

export interface CicloDeVida { lifecycle: CicloDeVidaEstado; eol_date: string | null; support_end: string | null; cycle: string | null }

export interface VersionSw extends Partial<CicloDeVida> {
  id: string; product_id: string; version: string; cycle: string | null; release_date: string | null
  support_end: string | null; eol_date: string | null; extended_support_end: string | null; is_latest: boolean
  lifecycle_source: string | null; notes: string | null; is_eol: boolean; is_unsupported: boolean
  instances_count?: number; components_count?: number; open_findings?: number
}

export interface InstanciaSw extends Partial<CicloDeVida> {
  id: string; product_id: string; product_name: string | null; product_category: string | null
  version_id: string | null; version: string | null; name: string | null
  ci_id: string | null; ci_name: string | null; ci_hostname: string | null; ci_ip: string | null; ci_type: string | null
  own_ci_id: string | null; environment: string; status: string; install_path: string | null; config_path: string | null
  ports: number[]; exposure: string; criticality: string | null; owner_user_id: string | null; client_id: string | null
  service_ci_id: string | null; license_id: string | null; alm_install_id: string | null
  config_format: string | null; config: Record<string, unknown> | null; config_hash: string | null
  baseline_approved_at: string | null; drift_detected_at: string | null; source: string; last_seen_at: string | null
  notes: string | null; is_active: boolean; created_at: string | null
  open_findings?: number; worst_severity?: Severidad | null; components_count?: number
  baseline_violations?: ViolacionDeLineaBase[]; config_summary?: Record<string, unknown>
  relations?: RelacionSw[]; config_history?: FotoDeConfiguracion[]
}
export type InstanciaSwIn = Partial<Pick<InstanciaSw, 'product_id' | 'version_id' | 'version' | 'name' | 'ci_id' | 'own_ci_id' | 'environment' | 'status' | 'install_path' | 'config_path' | 'ports' | 'exposure' | 'criticality' | 'owner_user_id' | 'client_id' | 'service_ci_id' | 'license_id' | 'alm_install_id' | 'config_format' | 'notes'>> & {
  config?: Record<string, unknown> | null; config_text?: string | null
}

export interface RelacionSw { id: string; source_instance_id: string; target_instance_id: string | null; target_ci_id: string | null; relation_type: string; details: string | null }
export interface FotoDeConfiguracion { id: string; config: Record<string, unknown> | null; config_hash: string | null; version: string | null; changed_keys: string[]; source: string; created_by: string | null; created_at: string | null }
export interface ViolacionDeLineaBase { key: string; op: string; expected: unknown; actual: unknown; severity: string; description?: string | null }
export interface ReglaDeLineaBase { key: string; op: string; value?: unknown; severity: string; description?: string | null }
export interface LineaBase { id: string; product_id: string; name: string; rules: ReglaDeLineaBase[]; environment: string | null; is_active: boolean; approved_by: string | null; approved_at: string | null }

export interface ComponenteSw {
  id: string; parent_version_id: string; component_product_id: string; component_name: string | null
  component_category: string | null; component_version: string | null; relation: string; scope: string; direct: boolean
  via_component_id: string | null; purl: string | null; license_spdx: string | null; source: string; notes: string | null
}

export interface LicenciaAlm { id: string; name: string; product_name: string | null; version: string | null; edition: string | null; type: string; status: string; total_seats: number | null; expiry_date: string | null; vendor_id: string | null; contract_id: string | null }

export interface FichaSw {
  product: ProductoSw
  versions: VersionSw[]
  instances: InstanciaSw[]
  used_in: ({ product_id: string; product_name: string; version_id: string; version: string; component_version: string | null; direct: boolean; relation: string } & CicloDeVida)[]
  licenses: LicenciaAlm[]
  baselines: LineaBase[]
  findings_by_severity: Partial<Record<Severidad, number>>
}

export interface NodoDeArbol extends CicloDeVida {
  id: string; product_id: string; name: string | null; category: string | null; version: string | null; relation: string
  scope: string; direct: boolean; purl: string | null; license: string | null; license_family: string
  license_issue: { level: 'conflict' | 'warning'; reason: string; family: string } | null
  open_findings: number; worst_severity: Severidad | null; children: NodoDeArbol[]
}
export interface ArbolSw { product: ProductoSw | null; version: VersionSw; tree: NodoDeArbol[]; summary: { components: number; direct: number; transitive: number }; deployed_on: InstanciaSw[] }

export interface CiBreve { id: string; code: string; name: string; ci_type: string; hostname: string | null; ip_address: string | null; environment: string | null; criticality: string | null; owner_user_id: string | null; status: string; instance_id?: string }

export interface DondeSeUsa {
  query: string; op: string; version: string | null
  products: { id: string; name: string; category: string; match_key: string }[]
  instances: InstanciaSw[]
  software: { product_id: string; product_name: string; origin: string; version_id: string; version: string; components: ({ component_id: string; name: string | null; version: string | null; direct: boolean; relation: string } & CicloDeVida)[]; machines: (CiBreve & { environment?: string })[] }[]
  machines: CiBreve[]
  versions: Record<string, number>
  summary: { instances: number; software: number; machines: number; components: number }
}

export interface Impacto {
  software: { product_id: string; product_name: string; version_id: string; version: string }[]
  affected_products: { id: string; name: string }[]
  instances: InstanciaSw[]; machines: CiBreve[]; impacted_cis: CiBreve[]; services: CiBreve[]
  clients: { id: string; name: string }[]; owners: { id: string; name: string }[]
  summary: { software: number; instances: number; machines: number; services: number; clients: number; findings: number }
}

export interface Hallazgo {
  id: string; status: EstadoHallazgo; severity: Severidad; priority_score: number | null
  score_detail: Record<string, unknown> | null; vulnerability_id: string; vuln_id: string | null; title: string | null
  cvss_score: number | null; epss_score: number | null; kev: boolean; aliases: string[]
  product_id: string; product_name: string | null; affected_version: string | null; fixed_version: string | null
  instance_id: string | null; instance_name: string | null; ci_id: string | null; ci_name: string | null
  parent_version_id: string | null; parent_product_id: string | null; parent_product_name: string | null; parent_version: string | null
  environment: string | null; exposure: string | null; first_seen_at: string | null; last_seen_at: string | null
  sla_due_at: string | null; sla_days_left: number | null; sla_tone: 'success' | 'warning' | 'danger' | null; sla_breached: boolean
  assignee_user_id: string | null; ticket_id: string | null; change_id: string | null; problem_id: string | null; task_id: string | null
  notes: string | null; resolution: string | null; closed_at: string | null; verified_at: string | null
  /** Versión desconocida: «posible afectado» (prioridad a la mitad y sin SLA). */
  possible?: boolean
}
export interface ExcepcionSw { id: string; finding_id: string; reason: string; compensating_controls: string | null; expires_at: string; status: 'pending' | 'approved' | 'rejected' | 'expired' | 'revoked'; requested_by: string | null; decided_by: string | null; decided_at: string | null; decision_note: string | null; approval_request_id: string | null; created_at: string | null; finding?: Hallazgo }
export interface DetalleDeHallazgo extends Hallazgo {
  vulnerability: { description: string | null; cvss_vector: string | null; cvss_version: string | null; epss_percentile: number | null; kev_added: string | null; cwe: string[]; references: string[]; published_at: string | null; source: string }
  impact: Impacto
  exceptions: ExcepcionSw[]
}
export interface FiltroDeHallazgos { status?: string; severity?: string; product_id?: string; ci_id?: string; kev?: boolean; out_of_sla?: boolean; possible?: boolean; q?: string; environment?: string; page?: number; page_size?: number }

export interface AvisoSw { id: string; vuln_id: string; aliases: string[]; source: string; title: string | null; severity: Severidad; cvss_score: number | null; cvss_vector: string | null; epss_score: number | null; epss_percentile: number | null; kev: boolean; published_at: string | null; modified_at: string | null }

export interface CuadroDeMando {
  products: number; applications: number; versions: number; instances: number; components: number; machines: number
  findings_live: number; findings_by_severity: Partial<Record<Severidad, number>>; findings_by_status: Partial<Record<EstadoHallazgo, number>>
  findings_out_of_sla: number; findings_kev: number
  top_products: { product_id: string; name: string | null; findings: number; max_priority: number | null }[]
  eol: { eol: number; unsupported: number; soon: number }; eol_in_production: number
  drift: { drift: number; violations: number; instances_with_violations: number }
  licenses: { conflicts: number; warnings: number }; products_without_owner: number
  exceptions: Partial<Record<ExcepcionSw['status'], number>>; last_sync_at: string | null; last_sync_status: string | null
  findings_possible?: number
  /** Fuentes de avisos activas (osv, nvd, ghsa, epss, kev, eol). */
  sources_active?: string[]
  scanners?: { total: number; active: number; last_run_at: string | null; with_errors: number }
}

export interface Maquina {
  ci: CiBreve; instances: InstanciaSw[]; relations: RelacionSw[]
  assets: { id: string; name: string; type: string; serial_number: string | null; asset_tag: string | null; status: string; os: string | null; warranty_expiry: string | null; eol_date: string | null }[]
  licenses: { id: string; name: string; status: string; expiry_date: string | null }[]
  open_tickets: number; software_history: { field: string; old_value: string | null; new_value: string | null; summary: string | null; created_at: string | null }[]
  findings_by_severity: Partial<Record<Severidad, number>>
}

export interface FinDeVida { instances: (InstanciaSw & CicloDeVida)[]; components: ({ component_id: string; name: string | null; version: string | null; parent_product_id: string | null; parent_product_name: string | null; parent_version: string | null } & CicloDeVida)[]; summary: { eol: number; unsupported: number; soon: number } }
export interface Deriva { drift: (InstanciaSw & { changed_keys: string[] })[]; violations: { instance_id: string; instance_name: string | null; product_name: string | null; ci_name: string | null; environment: string; baseline_id: string; baseline_name: string; baseline_approved: boolean; violations: ViolacionDeLineaBase[] }[]; summary: { drift: number; violations: number; instances_with_violations: number } }
export interface AnalisisDeLicencias { by_family: Record<string, number>; issues: { component_id: string; name: string | null; version: string | null; license: string | null; level: 'conflict' | 'warning'; reason: string; family: string; parent_product_id: string | null; parent_product_name: string | null; parent_version: string | null; parent_distribution: string | null }[]; summary: { conflicts: number; warnings: number } }

export interface GrafoSw { nodes: { id: string; name: string; ci_type: string; is_center?: boolean; status?: string; criticality?: string | null; hostname?: string | null; kind: 'ci' | 'instance' | 'product' | 'component'; ref_id: string }[]; edges: { source: string; target: string; rel_type: string }[] }

export interface ResultadoDeImportacion { import_id?: string; format?: string; total?: number; created?: number; updated?: number; removed?: number; new_products?: number; vulnerabilities?: { created: number; updated: number }; ignored?: string[]; unknown_version?: number; [k: string]: unknown }
export interface EjecucionDeSync { id: string; source: string; status: string; started_at: string | null; finished_at: string | null; queries: number; vulnerabilities: number; findings_new: number; findings_resolved: number; error: string | null; triggered_by: string }

export interface ConfigSoftware {
  osv_enabled: boolean; osv_url: string | null; nvd_enabled: boolean; nvd_url: string | null
  ghsa_enabled: boolean; ghsa_url: string | null; epss_enabled: boolean; epss_url: string | null
  kev_enabled: boolean; kev_url: string | null; eol_enabled: boolean; eol_url: string | null; auto_sync: boolean
  max_queries: number; timeout_seconds: number
  sla_days_critical: number; sla_days_high: number; sla_days_medium: number; sla_days_low: number; sla_days_kev: number
  exception_max_days: number; eol_warning_days: number
  licenses_allowed: string | null; licenses_denied: string | null; auto_ticket_min_severity: Severidad | null
  osv_url_effective: string; nvd_url_effective: string; ghsa_url_effective: string; epss_url_effective: string; kev_url_effective: string; eol_url_effective: string
  nvd_api_key_set: boolean; ghsa_token_set: boolean; last_sync_at: string | null; last_sync_status: string | null
}
/** Al guardar: `nvd_api_key`/`ghsa_token` vacíos = no cambian; `'__borrar__'` = quitar. */
export type ConfigSoftwareIn = Partial<Omit<ConfigSoftware, `${string}_effective` | 'nvd_api_key_set' | 'ghsa_token_set' | 'last_sync_at' | 'last_sync_status'>> & { nvd_api_key?: string; ghsa_token?: string }

export type TipoDeConexion = 'sw_ssh' | 'sw_winrm' | 'sw_api'
  // Índice de riesgo (22-11-2026, §11.9): vulnerabilidades de terceros e intentos de explotación (SIEM).
  | 'sw_vm_trendmicro' | 'sw_vm_defender' | 'sw_vm_qualys' | 'sw_vm_tenable' | 'sw_vm_rapid7' | 'sw_siem'
export interface ConexionDeEscaneo {
  id: string; name: string; type: TipoDeConexion; is_active: boolean; scan_interval_minutes: number
  /** Sin secretos: los puestos vienen en `secrets_set`. */
  config: Record<string, unknown>; secrets_set: string[]
  last_run_at: string | null; last_run_status: string | null; next_run_at: string | null
}
export interface ConexionDeEscaneoIn { name: string; type: TipoDeConexion; config: Record<string, unknown>; scan_interval_minutes: number; is_active: boolean }
export interface ResultadoDeEscaneo {
  job_id: string; status: string; hosts: number; created: number; updated: number; stopped: number; components: number
  cis_created: number; without_ci: number; errors: { target: string; error: string }[]; findings_new: number; findings_resolved: number
}
export interface EjecucionDeEscaneo { id: string; status: string; triggered_by: string | null; started_at: string | null; finished_at: string | null; error: string | null; summary: Record<string, unknown> | null }

const B = '/cmdb/software'

const subir = (ruta: string, fichero: File | File[], extra?: Record<string, string | boolean | undefined>) => {
  const fd = new FormData()
  // Uno: `file`. Varios (pom.xml con su padre, requirements.txt con su lock, un zip…): `files` repetido.
  if (Array.isArray(fichero)) fichero.forEach(f => fd.append('files', f))
  else fd.append('file', fichero)
  Object.entries(extra ?? {}).forEach(([k, v]) => { if (v !== undefined) fd.append(k, String(v)) })
  return D<ResultadoDeImportacion>(api.post(ruta, fd, { headers: { 'Content-Type': 'multipart/form-data' } }))
}

export const cmdbSoftwareApi = {
  meta: () => D<MetaSoftware>(api.get(`${B}/meta`)),
  cuadroDeMando: () => D<CuadroDeMando>(api.get(`${B}/dashboard`)),

  // Catálogo
  productos: (p?: { q?: string; category?: string; origin?: string; lifecycle?: string; include_retired?: boolean; apps_only?: boolean; page?: number; page_size?: number }) =>
    L<ProductoSw>(api.get(`${B}/products`, { params: p })),
  crearProducto: (d: ProductoSwIn) => D<ProductoSw>(api.post(`${B}/products`, d)),
  ficha: (id: string) => D<FichaSw>(api.get(`${B}/products/${id}`)),
  editarProducto: (id: string, d: ProductoSwIn) => D<ProductoSw>(api.patch(`${B}/products/${id}`, d)),
  retirarProducto: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/products/${id}`)),
  crearVersion: (productId: string, d: Partial<VersionSw>) => D<VersionSw>(api.post(`${B}/products/${productId}/versions`, d)),
  editarVersion: (id: string, d: Partial<VersionSw>) => D<VersionSw>(api.patch(`${B}/versions/${id}`, d)),
  borrarVersion: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/versions/${id}`)),
  /** Ciclos de vida por rama, formato endoflife.date: [{cycle, releaseDate, support, eol, extendedSupport}] */
  importarCiclos: (productId: string, ciclos: Record<string, unknown>[]) => D<{ cycles: number }>(api.post(`${B}/products/${productId}/lifecycle`, ciclos)),
  vincularLicencia: (productId: string, licenseId: string) => D<LicenciaAlm[]>(api.post(`${B}/products/${productId}/licenses`, { license_id: licenseId })),
  desvincularLicencia: (productId: string, licenseId: string) => D<LicenciaAlm[]>(api.delete(`${B}/products/${productId}/licenses/${licenseId}`)),
  lineasBase: (productId: string) => D<LineaBase[]>(api.get(`${B}/products/${productId}/baselines`)),
  crearLineaBase: (productId: string, d: { name: string; rules: ReglaDeLineaBase[]; environment?: string | null; is_active?: boolean }) =>
    D<LineaBase>(api.post(`${B}/products/${productId}/baselines`, d)),
  editarLineaBase: (id: string, d: { name: string; rules: ReglaDeLineaBase[]; environment?: string | null; is_active?: boolean }) => D<LineaBase>(api.patch(`${B}/baselines/${id}`, d)),
  aprobarLineaBase: (id: string) => D<LineaBase>(api.post(`${B}/baselines/${id}/approve`)),
  borrarLineaBase: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/baselines/${id}`)),

  // Composición
  arbol: (versionId: string) => D<ArbolSw>(api.get(`${B}/versions/${versionId}/tree`)),
  anadirComponente: (versionId: string, d: { name?: string; purl?: string; cpe?: string; component_product_id?: string; component_version?: string; relation?: string; scope?: string; direct?: boolean; via_component_id?: string; license_spdx?: string; category?: string }) =>
    D<ComponenteSw>(api.post(`${B}/versions/${versionId}/components`, d)),
  quitarComponente: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/components/${id}`)),
  /** SBOM (CycloneDX/SPDX), lock de dependencias o informe de Trivy/Grype. */
  importarComponentes: (versionId: string, fichero: File | File[], opciones?: { format?: string; replace?: boolean }) =>
    subir(`${B}/versions/${versionId}/import`, fichero, opciones),

  // Instancias y relaciones
  instancias: (p?: { product_id?: string; ci_id?: string; environment?: string; include_retired?: boolean }) => D<InstanciaSw[]>(api.get(`${B}/instances`, { params: p })),
  instancia: (id: string) => D<InstanciaSw>(api.get(`${B}/instances/${id}`)),
  crearInstancia: (d: InstanciaSwIn) => D<InstanciaSw>(api.post(`${B}/instances`, d)),
  editarInstancia: (id: string, d: InstanciaSwIn) => D<InstanciaSw>(api.patch(`${B}/instances/${id}`, d)),
  retirarInstancia: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/instances/${id}`)),
  historialDeConfiguracion: (id: string) => D<FotoDeConfiguracion[]>(api.get(`${B}/instances/${id}/config-history`)),
  aprobarConfiguracion: (id: string) => D<InstanciaSw>(api.post(`${B}/instances/${id}/approve-baseline`)),
  crearRelacion: (d: { source_instance_id: string; target_instance_id?: string; target_ci_id?: string; relation_type: string; details?: string }) => D<RelacionSw>(api.post(`${B}/relations`, d)),
  quitarRelacion: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/relations/${id}`)),

  // Análisis
  dondeSeUsa: (p: { q: string; op?: string; version?: string; environment?: string; exact?: boolean }) => D<DondeSeUsa>(api.get(`${B}/where-used`, { params: p })),
  impacto: (p: { product_id?: string; instance_id?: string; vulnerability_id?: string; finding_id?: string }) => D<Impacto>(api.get(`${B}/impact`, { params: p })),
  finDeVida: (p?: { days?: number; prod_only?: boolean }) => D<FinDeVida>(api.get(`${B}/analysis/eol`, { params: p })),
  deriva: () => D<Deriva>(api.get(`${B}/analysis/drift`)),
  licencias: () => D<AnalisisDeLicencias>(api.get(`${B}/analysis/licenses`)),
  maquina: (ciId: string) => D<Maquina>(api.get(`${B}/machines/${ciId}`)),
  grafo: (p: { product_id?: string; instance_id?: string; ci_id?: string }) => D<GrafoSw>(api.get(`${B}/graph`, { params: p })),

  // Conciliación e importación
  duplicados: () => D<{ reason: string; products: { id: string; name: string; match_key: string; category: string }[] }[]>(api.get(`${B}/reconciliation/duplicates`)),
  fusionar: (sourceId: string, targetId: string) => D<Record<string, number>>(api.post(`${B}/reconciliation/merge`, { source_id: sourceId, target_id: targetId })),
  importarCsv: (fichero: File) => subir(`${B}/import/csv`, fichero),
  importarDesdeActivos: () => D<Record<string, number>>(api.post(`${B}/import/alm`)),
  importarInventario: (ciId: string, inventario: Record<string, unknown>) => D<Record<string, number>>(api.post(`${B}/import/inventory`, { ci_id: ciId, inventory: inventario })),

  // Hallazgos y excepciones
  hallazgos: (f?: FiltroDeHallazgos) => L<Hallazgo>(api.get(`${B}/findings`, { params: f })),
  hallazgo: (id: string) => D<DetalleDeHallazgo>(api.get(`${B}/findings/${id}`)),
  cambiarHallazgo: (id: string, d: { status?: EstadoHallazgo; assignee_user_id?: string | null; notes?: string | null }) => D<Hallazgo>(api.patch(`${B}/findings/${id}`, d)),
  remediar: (id: string, d: { type: 'ticket' | 'problem' | 'change' | 'task'; project_id?: string; implementation_plan?: string; rollback_plan?: string; planned_start?: string; planned_end?: string }) =>
    D<{ type: string; id: string; finding: Hallazgo }>(api.post(`${B}/findings/${id}/remediate`, d)),
  pedirExcepcion: (id: string, d: { reason: string; compensating_controls?: string; expires_at: string }) => D<ExcepcionSw>(api.post(`${B}/findings/${id}/exceptions`, d)),
  excepciones: (status?: string) => D<ExcepcionSw[]>(api.get(`${B}/exceptions`, { params: { status } })),
  aprobarExcepcion: (id: string, note?: string) => D<ExcepcionSw>(api.post(`${B}/exceptions/${id}/approve`, { note })),
  rechazarExcepcion: (id: string, note?: string) => D<ExcepcionSw>(api.post(`${B}/exceptions/${id}/reject`, { note })),
  revocarExcepcion: (id: string) => D<ExcepcionSw>(api.post(`${B}/exceptions/${id}/revoke`)),

  // Avisos y sincronización
  avisos: (p?: { q?: string; severity?: string; kev?: boolean; page?: number; page_size?: number }) => L<AvisoSw>(api.get(`${B}/vulnerabilities`, { params: p })),
  aviso: (id: string) => D<AvisoSw & { description: string | null; references: string[]; cwe: string[]; affects: Record<string, unknown>[]; impact: Impacto }>(api.get(`${B}/vulnerabilities/${id}`)),
  crearAviso: (d: Record<string, unknown>) => D<{ created: number; updated: number; findings_new: number }>(api.post(`${B}/vulnerabilities`, d)),
  importarAvisos: (fichero: File) => subir(`${B}/vulnerabilities/import`, fichero),
  reevaluar: () => D<Record<string, number>>(api.post(`${B}/reevaluate`)),
  sincronizar: (sources?: string[]) => D<{ sources: { source: string; status: string; queries: number; vulnerabilities: number; error: string | null }[]; findings_new: number; findings_resolved: number }>(api.post(`${B}/sync`, { sources })),
  ejecuciones: () => D<EjecucionDeSync[]>(api.get(`${B}/sync/runs`)),

  // Configuración (Configuración → Software y vulnerabilidades)
  config: () => D<ConfigSoftware>(api.get(`${B}/config`)),
  guardarConfig: (d: ConfigSoftwareIn) => D<ConfigSoftware>(api.put(`${B}/config`, d)),
  probarFuente: (source: string) => D<{ ok: boolean; error?: string }>(api.post(`${B}/config/test/${source}`)),

  // Conexiones de escaneo (SSH, WinRM, API de EDR/RMM). Alta, cambio y prueba: admin; escanear: software.gestionar.
  conexiones: () => D<ConexionDeEscaneo[]>(api.get(`${B}/scanners`)),
  camposDeConexion: () => D<Record<TipoDeConexion, { key: string; secret: boolean }[]>>(api.get(`${B}/scanners/fields`)),
  crearConexion: (d: ConexionDeEscaneoIn) => D<ConexionDeEscaneo>(api.post(`${B}/scanners`, d)),
  /** Secreto vacío = no cambia; `'__borrar__'` = quitar. */
  editarConexion: (id: string, d: Partial<ConexionDeEscaneoIn>) => D<ConexionDeEscaneo>(api.patch(`${B}/scanners/${id}`, d)),
  borrarConexion: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/scanners/${id}`)),
  probarConexion: (id: string) => D<{ ok: boolean; host?: string; output?: string; devices?: number; error?: string }>(api.post(`${B}/scanners/${id}/test`)),
  escanear: (id: string, hosts?: string[]) => D<ResultadoDeEscaneo>(api.post(`${B}/scanners/${id}/run`, hosts ? { hosts } : {})),
  ejecucionesDeConexion: (id: string) => D<EjecucionDeEscaneo[]>(api.get(`${B}/scanners/${id}/runs`)),

  // Exportación (descarga como blob)
  exportarHallazgos: () => api.get(`${B}/export/findings.csv`, { responseType: 'blob' }),
  exportarInventario: () => api.get(`${B}/export/inventory.csv`, { responseType: 'blob' }),
}
