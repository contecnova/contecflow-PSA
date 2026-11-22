/**
 * services/api/clientesInternos.ts — clientes internos (22-11-2026).
 *
 * Contrato en docs/CLIENTES_INTERNOS.md §10:
 * - Gestión `/internal-clients` (`interno.gestionar`; emitir, anular, exportar y
 *   servicios compartidos con `interno.cargos`).
 * - Portal `/internal-portal` (`interno.portal`): solo lo de las unidades de
 *   quien llama (lo acota el backend).
 *
 * El interceptor de `_core` ya desenvuelve `{ data, meta }` y `{ items, meta }`;
 * las listas pasan además por `unwrapList` por si llegan como `{ items, total }`.
 * Las funciones devuelven directamente los datos (no la respuesta de axios).
 */
import type { AxiosResponse } from 'axios'
import api, { unwrapList } from './_core'
import type { Tono } from '../../utils/umbrales'

// ── Enumeraciones ────────────────────────────────────────────────────────────
export type TipoDeCliente = 'externo' | 'interno'
export type SubtipoInterno = 'departamento' | 'unidad_negocio' | 'filial' | 'centro_coste'
export type ModoFinanciero = 'showback' | 'chargeback' | 'intercompania'
export type MetodoDeCoste = 'horas_coste' | 'tarifa_interna' | 'precio_cerrado' | 'catalogo'
export type RolEnUnidad = 'responsable' | 'finanzas' | 'usuario_clave' | 'miembro' | 'direccion'
export type RolDesignable = 'usuario_clave' | 'finanzas' | 'delegado'
export type EstadoDeCargo = 'borrador' | 'por_aprobar' | 'emitido' | 'exportado' | 'anulado'
export type FuenteDeCoste = 'horas' | 'precio_cerrado' | 'catalogo' | 'licencias' | 'activos' | 'software' | 'reparto'
export type TipoDeEncuesta = 'nps' | 'csat'
export type TipoDeAdopcion = 'formacion' | 'comunicacion' | 'soporte' | 'hito'
export type EstadoDeAdopcion = 'pendiente' | 'en_curso' | 'hecho'
export type TipoDeBeneficio = 'ahorro' | 'ingreso' | 'riesgo' | 'intangible'
export type CriterioDeReparto = 'usuarios' | 'tickets' | 'licencias' | 'software' | 'fijo'
export type AvisoInterno = 'interno_sin_responsable' | 'interno_sin_presupuesto' | 'interno_sin_tarifa' | 'interno_sin_cuenta_erp' | 'interno_sin_estructura' | 'interno_sin_cuenta_ti' | string

// ── Campos internos de la ficha del cliente (`/clients`) ─────────────────────
export interface CamposDeClienteInterno {
  kind?: TipoDeCliente
  internal_type?: SubtipoInterno | null
  department_id?: string | null
  area_id?: string | null
  cost_center_id?: string | null
  group_organization_id?: string | null
  business_owner_id?: string | null
  business_owner_name?: string | null
  finance_mode?: ModoFinanciero | null
  cost_method?: MetodoDeCoste | null
  internal_rate_table_id?: string | null
  transfer_markup_pct?: number | null
  erp_account?: string | null
  members_count?: number | null
}

/** `GET /internal-clients/options`: datos reales para los selectores de la ficha. */
export interface OpcionesInternas {
  departments: { id: string; name: string }[]
  areas: { id: string; name: string }[]
  cost_centers: { id: string; code: string; name: string }[]
  organizations: { id: string; name: string }[]
  rate_tables: { id: string; name: string }[]
  users: { id: string; full_name: string }[]
}

// ── Portal ───────────────────────────────────────────────────────────────────
export interface UnidadDelPortal {
  id: string
  name: string
  internal_type: SubtipoInterno | null
  role: RolEnUnidad
  can_see_costs: boolean
  can_sign: boolean
  can_sign_uat: boolean
}
export interface PortalInternoYo { enabled: boolean; is_direction: boolean; units: UnidadDelPortal[] }

export interface Presupuesto { year: number; budget: number; consumed: number; pct: number | null; tone: Tono | null; currency: string; budget_ids?: string[] }
export interface ResumenDeUnidad {
  unit: { id: string; name: string; internal_type: SubtipoInterno | null; finance_mode: ModoFinanciero | null; business_owner_name: string | null }
  role: RolEnUnidad
  projects_active: number
  milestones_pending: number
  uat_pending: number
  tickets_open: number
  sla: { pct: number | null; tone: Tono | null; total: number }
  satisfaction: { nps: number | null; csat: number | null; responses: number; tone: Tono | null }
  budget: Presupuesto | null
  warnings: AvisoInterno[]
}
export interface ProyectoDeUnidad { id: string; code: string | null; name: string; status: string; progress: number | null; start_date: string | null; end_date: string | null; milestones_pending: number }
export interface HitoDeUnidad { id: string; project_id: string; project_name: string; name: string; due_date: string | null; billing_status: string | null; approval_requested_at: string | null; can_sign: boolean }
export interface UatDeUnidad { id: string; code: string | null; project_id: string; project_name: string; title: string; status: string; deadline: string | null; test_environment: string | null; signed: boolean; can_sign: boolean }
export interface TicketDeUnidad { id: string; number: string | null; title: string; status: string; priority: string | null; created_at: string; resolved_at: string | null; sla_resolution_breached: boolean | null }
export interface SlaDeUnidad {
  from: string; to: string; total: number; resolved: number; on_time: number; pct: number | null; tone: Tono | null; ola_breached: number
  by_priority: { priority: string; total: number; on_time: number; pct: number | null }[]
}
export interface LineaDeCoste { source: FuenteDeCoste; description: string | null; project_id: string | null; project_name: string | null; quantity: number | null; unit_amount: number | null; amount: number; source_ref: string | null }
export interface CosteDeUnidad { from: string; to: string; currency: string; total: number; by_source: Partial<Record<FuenteDeCoste, number>>; lines: LineaDeCoste[]; budget?: Presupuesto | null }
export interface Cargo {
  id: string; number: string | null; client_id: string; client_name: string; period: string; mode: ModoFinanciero | null; status: EstadoDeCargo
  total: number; currency: string; invoice_id: string | null; erp_reference: string | null; created_at: string; issued_at: string | null
  exported_at: string | null; over_budget: boolean; can_approve: boolean
}
export interface LineaDeCargo { id?: string; source: FuenteDeCoste | string; description: string | null; project_name?: string | null; quantity: number | null; unit_amount: number | null; amount: number }
export interface CargoDetalle extends Cargo { lines: LineaDeCargo[] }
export interface Peticion { id: string; title: string; status: string; created_at: string }
export interface PeticionesDeUnidad { source: 'demanda' | 'cartera'; items: Peticion[] }
export interface PeticionIn { title: string; description: string; kind: 'proyecto' | 'servicio'; estimated_budget?: number | null; wanted_start?: string | null; wanted_end?: string | null }
export interface SatisfaccionIn { score: number; comment: string | null; survey_type: TipoDeEncuesta }
export interface Satisfaccion { nps: number | null; csat: number | null; responses: number; tone: Tono | null; items: { id: string; score: number; survey_type: TipoDeEncuesta; comment: string | null; created_at: string }[] }
export interface ElementoDeAdopcion {
  id: string; kind: TipoDeAdopcion; title: string; due_date: string | null; status: EstadoDeAdopcion; target_users: number | null; reached_users: number | null
  project_id: string | null; project_name: string | null; course_id: string | null
}
export type AdopcionIn = Partial<Omit<ElementoDeAdopcion, 'id' | 'project_name'>>
export interface Beneficio {
  id: string; project_id: string; project_name: string | null; name: string; kind: TipoDeBeneficio; unit: string | null
  baseline: number | null; target: number | null; actual: number | null; target_date: string | null; measured_at: string | null
  achievement_pct: number | null; owner_id: string | null; owner_name: string | null; notes: string | null
}
export type BeneficioIn = Partial<Omit<Beneficio, 'id' | 'project_id' | 'project_name' | 'achievement_pct' | 'owner_name'>>

// ── Gestión ──────────────────────────────────────────────────────────────────
export interface UnidadDelCuadro {
  id: string; name: string; internal_type: SubtipoInterno | null; finance_mode: ModoFinanciero | null; business_owner_name: string | null
  budget: number | null; cost: number; pct: number | null; tone: Tono | null; projects_active: number; requests_open: number; warnings: AvisoInterno[]
}
export interface CuadroDeDireccion {
  year: number; currency: string
  totals: { budget: number; cost: number; pct: number | null; tone: Tono | null }
  by_source: { source: FuenteDeCoste; amount: number }[]
  units: UnidadDelCuadro[]
  /** Avisos de la empresa (p. ej. `interno_sin_cuenta_ti`: chargeback sin cuenta de TI del asiento). */
  warnings?: AvisoInterno[]
}
export interface MiembroDeUnidad { user_id: string; full_name: string; email: string | null; department: string | null; job_title: string | null; role: RolEnUnidad | string; designations: { id: string; role: RolDesignable }[] }
export interface TcoDeUnidad { year: number; currency: string; items: { product_id: string; name: string; instances: number; licenses: number; hours: number; total: number }[] }
export interface ServicioCompartido {
  id: string; name: string; description: string | null; monthly_amount: number; currency: string; criterion: CriterioDeReparto
  fixed_shares: Record<string, number> | null; is_active: boolean
}
export type ServicioCompartidoIn = Omit<ServicioCompartido, 'id'>
export interface RepartoDeServicio { period: string; total: number; currency: string; shares: { client_id: string; client_name: string; driver: number | null; pct: number; amount: number }[] }

// ── Ayudas ───────────────────────────────────────────────────────────────────
const datos = <T>(p: Promise<AxiosResponse<unknown>>): Promise<T> => p.then(r => r.data as T)
const lista = <T>(p: Promise<AxiosResponse<unknown>>): Promise<T[]> => p.then(r => unwrapList(r) as T[])
/** Quita los parámetros vacíos de la consulta. */
const params = (p: Record<string, unknown>) => Object.fromEntries(Object.entries(p).filter(([, v]) => v !== undefined && v !== null && v !== ''))

const G = '/internal-clients'
const P = '/internal-portal'

/** Gestión de clientes internos. */
export const clientesInternosApi = {
  opciones: () => datos<OpcionesInternas>(api.get(`${G}/options`)),
  cuadro: (year: number) => datos<CuadroDeDireccion>(api.get(`${G}/overview`, { params: { year } })),
  miembros: (cid: string) => lista<MiembroDeUnidad>(api.get(`${G}/${cid}/members`)),
  designar: (cid: string, user_id: string, role: RolDesignable) => datos<unknown>(api.post(`${G}/${cid}/roles`, { user_id, role })),
  quitarDesignacion: (cid: string, rid: string) => datos<unknown>(api.delete(`${G}/${cid}/roles/${rid}`)),
  coste: (cid: string, desde?: string, hasta?: string) => datos<CosteDeUnidad>(api.get(`${G}/${cid}/cost`, { params: params({ desde, hasta }) })),
  tco: (cid: string, year: number) => datos<TcoDeUnidad>(api.get(`${G}/${cid}/tco`, { params: { year } })),
  presupuesto: (cid: string, year: number) => datos<Presupuesto>(api.get(`${G}/${cid}/budget`, { params: { year } })),
  sla: (cid: string, desde?: string, hasta?: string) => datos<SlaDeUnidad>(api.get(`${G}/${cid}/sla`, { params: params({ desde, hasta }) })),
  satisfaccion: (cid: string) => datos<Satisfaccion>(api.get(`${G}/${cid}/satisfaction`)),
  adopcion: (cid: string) => lista<ElementoDeAdopcion>(api.get(`${G}/${cid}/adoption`)),
  crearAdopcion: (cid: string, d: AdopcionIn) => datos<ElementoDeAdopcion>(api.post(`${G}/${cid}/adoption`, d)),
  editarAdopcion: (id: string, d: AdopcionIn) => datos<ElementoDeAdopcion>(api.patch(`${G}/adoption/${id}`, d)),
  borrarAdopcion: (id: string) => datos<unknown>(api.delete(`${G}/adoption/${id}`)),
  beneficios: (pid: string) => lista<Beneficio>(api.get(`${G}/projects/${pid}/benefits`)),
  crearBeneficio: (pid: string, d: BeneficioIn) => datos<Beneficio>(api.post(`${G}/projects/${pid}/benefits`, d)),
  editarBeneficio: (id: string, d: BeneficioIn) => datos<Beneficio>(api.patch(`${G}/benefits/${id}`, d)),
  borrarBeneficio: (id: string) => datos<unknown>(api.delete(`${G}/benefits/${id}`)),
  cargos: (f: { client_id?: string; period?: string; status?: string } = {}) => lista<Cargo>(api.get(`${G}/charges`, { params: params(f) })),
  generarCargo: (client_id: string, period: string) => datos<CargoDetalle>(api.post(`${G}/charges/generate`, { client_id, period })),
  cargo: (id: string) => datos<CargoDetalle>(api.get(`${G}/charges/${id}`)),
  emitirCargo: (id: string) => datos<CargoDetalle>(api.post(`${G}/charges/${id}/issue`)),
  aprobarCargo: (id: string, note: string | null) => datos<CargoDetalle>(api.post(`${G}/charges/${id}/approve`, { note })),
  rechazarCargo: (id: string, note: string | null) => datos<CargoDetalle>(api.post(`${G}/charges/${id}/reject`, { note })),
  anularCargo: (id: string, note: string | null) => datos<CargoDetalle>(api.post(`${G}/charges/${id}/cancel`, { note })),
  /** CSV de asientos del periodo (descarga). */
  exportarCargos: (period: string): Promise<Blob> =>
    api.get(`${G}/charges/export`, { params: { period }, responseType: 'blob' }).then(r => r.data as Blob),
  serviciosCompartidos: () => lista<ServicioCompartido>(api.get(`${G}/shared-costs`)),
  crearServicioCompartido: (d: ServicioCompartidoIn) => datos<ServicioCompartido>(api.post(`${G}/shared-costs`, d)),
  editarServicioCompartido: (id: string, d: Partial<ServicioCompartidoIn>) => datos<ServicioCompartido>(api.patch(`${G}/shared-costs/${id}`, d)),
  borrarServicioCompartido: (id: string) => datos<unknown>(api.delete(`${G}/shared-costs/${id}`)),
  reparto: (id: string, period: string) => datos<RepartoDeServicio>(api.get(`${G}/shared-costs/${id}/allocation`, { params: { period } })),
}

/** Portal interno: solo lo de las unidades de quien llama. */
export const portalInternoApi = {
  yo: () => datos<PortalInternoYo>(api.get(`${P}/me`)),
  resumen: (cid: string) => datos<ResumenDeUnidad>(api.get(`${P}/units/${cid}/summary`)),
  proyectos: (cid: string) => lista<ProyectoDeUnidad>(api.get(`${P}/units/${cid}/projects`)),
  hitos: (cid: string) => lista<HitoDeUnidad>(api.get(`${P}/units/${cid}/milestones`)),
  firmarHito: (mid: string, approve: boolean, note: string | null) => datos<unknown>(api.post(`${P}/milestones/${mid}/sign`, { approve, note })),
  uat: (cid: string) => lista<UatDeUnidad>(api.get(`${P}/units/${cid}/uat`)),
  firmarUat: (sid: string, result: 'passed' | 'failed', notes: string | null) => datos<unknown>(api.post(`${P}/uat/${sid}/sign`, { result, notes })),
  tickets: (cid: string) => lista<TicketDeUnidad>(api.get(`${P}/units/${cid}/tickets`)),
  sla: (cid: string) => datos<SlaDeUnidad>(api.get(`${P}/units/${cid}/sla`)),
  coste: (cid: string, year: number) => datos<CosteDeUnidad>(api.get(`${P}/units/${cid}/cost`, { params: { year } })),
  cargos: (cid: string) => lista<Cargo>(api.get(`${P}/units/${cid}/charges`)),
  peticiones: (cid: string) => datos<PeticionesDeUnidad>(api.get(`${P}/units/${cid}/requests`)),
  pedir: (cid: string, d: PeticionIn) => datos<unknown>(api.post(`${P}/units/${cid}/requests`, d)),
  valorar: (cid: string, d: SatisfaccionIn) => datos<unknown>(api.post(`${P}/units/${cid}/satisfaction`, d)),
  adopcion: (cid: string) => lista<ElementoDeAdopcion>(api.get(`${P}/units/${cid}/adoption`)),
  beneficios: (cid: string) => lista<Beneficio>(api.get(`${P}/units/${cid}/benefits`)),
}
