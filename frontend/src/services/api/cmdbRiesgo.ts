/**
 * services/api/cmdbRiesgo.ts — Índice de riesgo y gestión de vulnerabilidades (22-11-2026).
 *
 * API `/cmdb/software/risk/*` (app/api/v1/endpoints/cmdb_riesgo.py). Diseño:
 * docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11. El interceptor de `_core` ya
 * desenvuelve `{ data, meta }` y `{ items, meta }`: `r.data` es el contenido y,
 * en listas paginadas, `r.meta.total` el total (mismo patrón que cmdbSoftware.ts).
 */
import api from './_core'
import type { Hallazgo, Severidad } from './cmdbSoftware'

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const L = <T,>(p: Promise<{ data: unknown; meta?: unknown }>) =>
  p.then(r => ({ items: (r.data ?? []) as T[], total: Number((r.meta as { total?: number } | undefined)?.total ?? (r.data as unknown[] | undefined)?.length ?? 0) }))

export type TipoDeAmbito = 'org' | 'client' | 'service' | 'machine' | 'application'
export type NivelDeRiesgo = 'critical' | 'high' | 'medium' | 'low'
export type Factor = 'vulnerabilities' | 'exploitation' | 'exposure' | 'configuration' | 'eol' | 'signals'
export type Superficie = 'internal' | 'internet' | 'container' | 'cloud_vm' | 'serverless'
export type FuenteDeTerceros = 'trendmicro' | 'defender' | 'qualys' | 'tenable' | 'rapid7' | 'file'
export type TipoDeInforme = 'cyber_risk' | 'vuln_management'
export type Frecuencia = 'daily' | 'weekly' | 'monthly'
export type AccionDeExplotacion = 'blocked' | 'detected' | 'allowed'
export type Exposicion = 'internet' | 'internal' | 'isolated'

export interface MetaRiesgo {
  scope_types: TipoDeAmbito[]; control_types: string[]; control_reductions: Record<string, number>
  surfaces: Superficie[]; sources: FuenteDeTerceros[]; connector_types: string[]; report_types: TipoDeInforme[]
  alert_kinds: string[]; factors: Factor[]; frequencies: Frecuencia[]; exploit_actions: AccionDeExplotacion[]
}

export interface Ambito { scope_type: TipoDeAmbito; scope_id?: string | null }

export interface FactorDeIndice { key: Factor; score: number; points: number; weight: number; saturation: number; contribution: number }
export interface IndiceDeRiesgo {
  scope_type: TipoDeAmbito; scope_id: string | null; scope_name: string | null
  score: number; level: NivelDeRiesgo; accepted_score: number; target: number
  factors: FactorDeIndice[]
  counts: {
    findings_live: number; findings_accepted: number; kev: number; exploited: number; internet_assets: number
    drift: number; violations: number; eol: number; exploit_events: number; controls_active: number
  }
  evaluated_at: string | null; delta_7d: number | null
}
export interface PuntoDeHistorico { day: string; score: number; accepted_score: number }
export interface FilaDeComparacion {
  scope_type: TipoDeAmbito; scope_id: string; name: string; is_internal: boolean
  score: number; level: NivelDeRiesgo; accepted_score: number; findings_live: number; evaluated_at: string | null
}

export type CodigoDeAccion = 'upgrade' | 'no_fix' | 'possible' | 'retire' | 'control'
export interface PasoDelPlan {
  finding: Hallazgo & { risk_points?: number | null }
  impact: number; score_after: number
  actions: { code: CodigoDeAccion; params: Record<string, string | number> }[]
  remediation: { ticket_id: string | null; change_id: string | null; problem_id: string | null; task_id: string | null }
}
export interface PlanDeReduccion { current: number; target: number; reached: boolean; final_score: number; steps: PasoDelPlan[] }

export type TipoDeEvento = 'finding' | 'drift' | 'violation' | 'eol' | 'exploit'
export interface EventoDeRiesgo {
  kind: TipoDeEvento; id: string; title: string | null; points: number; severity: Severidad | string | null
  ci_name: string | null; product_name: string | null; detail: string | null; occurred_at: string | null; finding_id: string | null
}

export interface MetricasDeVulnerabilidades {
  days: number; assets: number; assets_with_vulns: number; pct_assets_with_vulns: number | null
  internal_assets: number; internal_with_vulns: number; pct_internal_with_vulns: number | null
  machines: number; machines_with_vulns: number; pct_machines_with_vulns: number | null
  density_per_asset: number | null; density_per_machine: number | null
  mttp_days: number | null; mttp_sample: number; avg_age_unpatched_days: number | null; os_unsupported: number
  by_impact: { high: number; medium: number; low: number }; impact_ranges: { high_from: number; medium_from: number }
  by_state: { new: number; in_progress: number; resolved: number; accepted: number }
}

export type RecuentoDeSuperficie = { assets: number; findings: number; critical_high: number }
export type Superficies = Record<Superficie, RecuentoDeSuperficie>

export type Agrupacion = 'none' | 'cve' | 'asset'
export type HallazgoDeSuperficie = Hallazgo & { risk_points: number | null; surface: Superficie | null; detected_by: string[]; controls_active: number; exploit_attempts: number }
export interface GrupoPorCve {
  vulnerability_id: string; vuln_id: string | null; title: string | null; severity: Severidad; cvss_score: number | null
  epss_score: number | null; kev: boolean; assets: number; findings: number; max_risk: number | null; products: string[]
}
export interface GrupoPorActivo {
  ci_id: string; ci_name: string | null; ci_hostname: string | null; surface: Superficie | null; exposure: Exposicion | null
  findings: number; critical: number; high: number; max_risk: number | null
}
export interface FiltroDeSuperficie {
  surface?: string; group_by?: Agrupacion; severity?: string; status?: string; q?: string; kev?: boolean; page?: number; page_size?: number
}

export interface VistaGuardada {
  id: string; name: string; surface: string | null; group_by: Agrupacion | null; filters: Record<string, string>
  columns: string[]; shared: boolean; owner_user_id: string | null; mine: boolean
}
export type VistaGuardadaIn = Omit<VistaGuardada, 'id' | 'owner_user_id' | 'mine'>

export type EstadoDeControl = 'active' | 'expired' | 'revoked'
export interface ControlCompensatorio {
  id: string; finding_id: string; vuln_id: string | null; product_name: string | null; ci_name: string | null
  control_type: string; description: string; evidence: string | null; reduction: number; expires_at: string
  status: EstadoDeControl; created_by: string | null; created_by_name: string | null; created_at: string | null
  revoked_by: string | null; revoked_at: string | null; revoke_reason: string | null
}
export interface ControlCompensatorioIn { finding_ids: string[]; control_type: string; description: string; evidence?: string; reduction?: number; expires_at: string }

export interface IntentoDeExplotacion {
  id: string; source: string; vuln_id: string | null; ci_id: string | null; ci_name: string | null; host: string | null
  ip: string | null; observed_at: string | null; action: AccionDeExplotacion; count: number; finding_id: string | null
}
export interface ResultadoDeIntentos { rows: number; created: number; duplicates: number; matched: number; errors: { row: number; error: string }[] }

export interface ResultadoDeImportacionDeTerceros {
  source: string; detections: number; cis_created: number; products_created: number; instances_created: number
  findings_new: number; findings_updated: number; findings_resolved: number; unmatched_hosts: string[]; errors: { row: number; error: string }[]
}

export interface AjustesDeRiesgoBase {
  weights: Record<Factor, number>; saturation: Record<Factor, number>
  exposure: Record<Exposicion, number>; criticality: Record<NivelDeRiesgo, number>
  exploit: { w_kev: number; w_epss: number; w_attempts: number; epss_threshold: number }
  age: { w_age: number; age_cap_days: number }
  impact_ranges: { high_from: number; medium_from: number }
  target: number; history_days: number
  alerts: { kev_new: boolean; index_above: number | null; sla_due_days: number | null; roles: string[]; user_ids: string[]; email: boolean }
}
export interface AjustesDeRiesgo extends AjustesDeRiesgoBase { defaults: AjustesDeRiesgoBase }
export type AjustesDeRiesgoIn = Partial<AjustesDeRiesgoBase>

export interface InformeDeRiesgo {
  id: string; name: string; report_type: TipoDeInforme; scope_type: TipoDeAmbito; scope_id: string | null
  frequency: Frecuencia; send_hour: number; day_of_week: number | null; day_of_month: number | null
  recipients: string[]; is_active: boolean; last_run_at: string | null; last_status: string | null
  last_error: string | null; next_run_at: string | null
}
export type InformeDeRiesgoIn = Omit<InformeDeRiesgo, 'id' | 'last_run_at' | 'last_status' | 'last_error' | 'next_run_at'>

const B = '/cmdb/software/risk'

/** Parámetros de ámbito sin `scope_id` vacío (la empresa no lleva id). */
const ambito = (a: Ambito) => ({ scope_type: a.scope_type, scope_id: a.scope_id || undefined })

const multipart = (ruta: string, fichero: File, extra?: Record<string, string>) => {
  const fd = new FormData()
  fd.append('file', fichero)
  Object.entries(extra ?? {}).forEach(([k, v]) => fd.append(k, v))
  return api.post(ruta, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const cmdbRiesgoApi = {
  meta: () => D<MetaRiesgo>(api.get(`${B}/meta`)),

  // Índice, histórico, comparación y recálculo
  indice: (a: Ambito) => D<IndiceDeRiesgo>(api.get(`${B}/index`, { params: ambito(a) })),
  historico: (a: Ambito, days = 90) => D<PuntoDeHistorico[]>(api.get(`${B}/history`, { params: { ...ambito(a), days } })),
  comparar: (p: { scope_type: Exclude<TipoDeAmbito, 'org'>; internal?: boolean; limit?: number }) => D<FilaDeComparacion[]>(api.get(`${B}/compare`, { params: p })),
  recalcular: () => D<{ scopes: number; evaluated_at: string; org_score: number }>(api.post(`${B}/recalculate`)),

  // Plan de reducción y eventos
  plan: (a: Ambito, target?: number) => D<PlanDeReduccion>(api.get(`${B}/plan`, { params: { ...ambito(a), target } })),
  eventos: (a: Ambito, p?: { kind?: string; page?: number; page_size?: number }) => L<EventoDeRiesgo>(api.get(`${B}/events`, { params: { ...ambito(a), ...p } })),

  // Métricas y superficies
  metricas: (a: Ambito, days = 90) => D<MetricasDeVulnerabilidades>(api.get(`${B}/metrics`, { params: { ...ambito(a), days } })),
  superficies: () => D<Superficies>(api.get(`${B}/surfaces`)),
  hallazgos: (f: FiltroDeSuperficie & { group_by?: 'none' }) => L<HallazgoDeSuperficie>(api.get(`${B}/findings`, { params: f })),
  hallazgosPorCve: (f: FiltroDeSuperficie) => L<GrupoPorCve>(api.get(`${B}/findings`, { params: { ...f, group_by: 'cve' } })),
  hallazgosPorActivo: (f: FiltroDeSuperficie) => L<GrupoPorActivo>(api.get(`${B}/findings`, { params: { ...f, group_by: 'asset' } })),

  // Vistas guardadas
  vistas: () => D<VistaGuardada[]>(api.get(`${B}/views`)),
  crearVista: (d: VistaGuardadaIn) => D<VistaGuardada>(api.post(`${B}/views`, d)),
  editarVista: (id: string, d: Partial<VistaGuardadaIn>) => D<VistaGuardada>(api.patch(`${B}/views/${id}`, d)),
  borrarVista: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/views/${id}`)),

  // Exposición
  detectarExposicion: () => D<{ checked: number; set_internet: number; unchanged: number }>(api.post(`${B}/exposure/detect`)),
  marcarExposicionDeCi: (ciId: string, exposure: Exposicion | null) => D<Record<string, unknown>>(api.put(`${B}/exposure/ci/${ciId}`, { exposure })),

  // Controles compensatorios
  controles: (p?: { status?: string; finding_id?: string }) => D<ControlCompensatorio[]>(api.get(`${B}/controls`, { params: p })),
  crearControles: (d: ControlCompensatorioIn) => D<ControlCompensatorio[]>(api.post(`${B}/controls`, d)),
  revocarControl: (id: string, reason: string) => D<ControlCompensatorio>(api.post(`${B}/controls/${id}/revoke`, { reason })),

  // Intentos de explotación
  intentos: (p?: { days?: number; page?: number; page_size?: number }) => L<IntentoDeExplotacion>(api.get(`${B}/exploits`, { params: p })),
  importarIntentos: (fichero: File) => D<ResultadoDeIntentos>(multipart(`${B}/exploits/import`, fichero)),

  // Importación de terceros (fichero)
  importarFichero: (fichero: File, o: { source: string; create_cis: boolean; complete: boolean }) =>
    D<ResultadoDeImportacionDeTerceros>(multipart(`${B}/import/file`, fichero, { source: o.source, create_cis: String(o.create_cis), complete: String(o.complete) })),

  // Ajustes (Configuración → Software y vulnerabilidades)
  ajustes: () => D<AjustesDeRiesgo>(api.get(`${B}/settings`)),
  guardarAjustes: (d: AjustesDeRiesgoIn) => D<AjustesDeRiesgo>(api.put(`${B}/settings`, d)),

  // Informes programados
  informes: () => D<InformeDeRiesgo[]>(api.get(`${B}/reports`)),
  crearInforme: (d: InformeDeRiesgoIn) => D<InformeDeRiesgo>(api.post(`${B}/reports`, d)),
  editarInforme: (id: string, d: Partial<InformeDeRiesgoIn>) => D<InformeDeRiesgo>(api.patch(`${B}/reports/${id}`, d)),
  borrarInforme: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/reports/${id}`)),
  enviarInforme: (id: string) => D<{ ok: boolean; recipients: number | string[]; error?: string }>(api.post(`${B}/reports/${id}/run`)),
}
