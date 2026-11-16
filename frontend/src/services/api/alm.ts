/**
 * services/api/alm.ts — licencias y hardware, fases 1 y 3 (16-11-2026).
 *
 * Asignación universal (titular persona, proyecto, departamento, cliente o
 * equipo), historial inmutable, ciclo de vida y actas de los activos, coste por
 * titular y día, renovaciones y conciliación con facturas y gastos.
 * Los CRUD de siempre siguen en `_core.ts` (assetsApi, licensesApi, vendorsApi, almExtApi).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 * Los errores llegan como código `alm_*` (ver `errorAlm` en components/alm/almFases).
 */
import api from './_core'
import type { MetaDeLista } from './tipos-plataforma'

export type TipoDeTitular = 'user' | 'project' | 'department' | 'client' | 'asset'
export type ModoDeAsignacion = 'assignment' | 'loan' | 'pool'
export type EstadoDeAsignacion = 'pending' | 'active' | 'ended' | 'rejected' | 'cancelled'
export type Metrica = 'named_user' | 'device' | 'concurrent' | 'volume' | 'site'
export type Condicion = 'new' | 'good' | 'fair' | 'poor'

/** `alm_asignaciones.serializar`. */
export interface Asignacion {
  id: string
  resource_type: 'license' | 'asset'
  license_id: string | null
  asset_id: string | null
  resource_name: string | null
  holder_type: TipoDeTitular
  holder_id: string | null
  holder_name: string | null
  mode: ModoDeAsignacion
  parent_id: string | null
  quantity: number
  status: EstadoDeAsignacion
  valid_from: string | null
  valid_to: string | null
  ended_on: string | null
  end_kind: string | null
  end_reason: string | null
  reason: string | null
  source: string
  assigned_by: string | null
  assigned_by_name: string | null
  assigned_at: string | null
  approved_at: string | null
  charge_project_id: string | null
  charge_cost_center_id: string | null
  charge_client_id: string | null
  rebillable: boolean | null
  notes: string | null
  used_in_pool: number | null
  overdue: boolean
  days_to_due: number | null
}

/** Cuerpo de `POST /alm/licenses/{id}/assign` y `POST /alm/assets/{id}/assign`. */
export interface NuevaAsignacion {
  holder_type: TipoDeTitular
  holder_id: string
  quantity?: number
  valid_from?: string
  valid_to?: string
  reason?: string
  mode?: ModoDeAsignacion
  parent_id?: string
  charge_project_id?: string
  charge_cost_center_id?: string
  charge_client_id?: string
  rebillable?: boolean
  notes?: string
  checklist?: FilaDeChecklist[]
  condition?: Condicion
  observations?: string
  location?: string
}

/** `alm_asignaciones.historial`. */
export interface EventoAlm {
  id: string
  event: string
  resource_type: string
  license_id: string | null
  asset_id: string | null
  contract_id: string | null
  assignment_id: string | null
  holder_type: string | null
  holder_id: string | null
  holder_name: string | null
  actor_id: string | null
  actor_name: string | null
  reason: string | null
  data: Record<string, unknown> | null
  created_at: string | null
}

export interface FilaDeChecklist { item: string; ok: boolean; note?: string }

export interface Adjunto {
  id: string; kind: string; act_id: string | null; asset_id: string | null; invoice_id: string | null
  document_id: string; file_name: string | null; mime: string | null; url: string | null; created_at: string | null
}

/** `alm_actas.serializar`. */
export interface Acta {
  id: string
  kind: 'delivery' | 'return'
  status: 'pending_signature' | 'signed' | 'void' | 'unsigned'
  assignment_id: string
  asset_id: string
  asset_name: string | null
  holder_type: string | null
  holder_name: string | null
  signer_user_id: string | null
  signer_name: string | null
  checklist: FilaDeChecklist[]
  condition: Condicion | null
  observations: string | null
  document_id: string | null
  pdf_url: string | null
  esign_provider: string | null
  signed_at: string | null
  created_at: string | null
  attachments: Adjunto[]
}

export interface ConfigAlm {
  checklist: string[]
  acts_enabled: boolean
  loan_default_days: number
  rebill_markup_pct: number
  esign_provider: string
}

export interface UsoDeLicencia {
  assigned: number; total: number | null; in_use: number | null; underused: number | null; unused: number | null
  no_data: number | null; concurrent_peak: number | null; source: string; measured_at: string | null
}

export interface PicoConcurrente { id: string; peak: number; source: string; measured_at: string }

/** `alm_costes.resumen`. */
export type Agrupacion = 'holder' | 'project' | 'cost_center' | 'client' | 'resource' | 'kind'
export interface GrupoDeCoste { key: string; name: string | null; amount: number; idle: number; lines: number }
export interface LineaDeCoste {
  kind: 'license' | 'asset' | 'contract' | 'idle'
  resource_type: string; resource_id: string; resource_name: string; amount: number; days: number; currency: string
  assignment_id: string | null; holder_type: string | null; holder_id: string | null; holder_name: string | null
  project_id: string | null; project_name: string | null; cost_center_id: string | null; cost_center_name: string | null
  client_id: string | null; client_name: string | null; rebillable: boolean
}
export interface ResumenDeCostes {
  from: string; to: string; currency: string; group_by: Agrupacion; total: number; idle: number; rebillable: number
  groups: GrupoDeCoste[]; lines: LineaDeCoste[]
}
export interface Refacturable {
  from: string; to: string; currency: string; markup_pct: number; total_cost: number; total_to_bill: number
  clients: { client_id: string; client_name: string | null; cost: number; amount_to_bill: number; lines: LineaDeCoste[] }[]
}

/** `alm_renovaciones._fila`. */
export interface Renovacion {
  entity_type: 'contract' | 'license'
  id: string
  name: string
  vendor_name: string | null
  renewal_date: string | null
  notice_days: number
  notice_deadline: string | null
  days_to_renewal: number | null
  days_to_deadline: number | null
  auto_renew: boolean
  annual_cost: number | null
  total_seats: number | null
  billing_cycle: string | null
  owner_id: string | null
  decision: null | {
    id: string; decision: 'renew' | 'reduce' | 'cancel'; new_seats: number | null; new_annual_cost: number | null
    reason: string | null; decided_by_name: string | null; decided_at: string | null
  }
  usage: (UsoDeLicencia & Record<string, unknown>) | { licenses: (UsoDeLicencia & { license_id: string; name: string })[] } | null
}

/** `alm_conciliacion.serializar`. */
export interface FacturaDeProveedor {
  id: string; number: string; vendor_id: string | null; vendor_name: string | null
  contract_id: string | null; contract_title: string | null; license_id: string | null; license_name: string | null
  issue_date: string | null; period_from: string | null; period_to: string | null
  amount: number; tax_amount: number | null; currency: string | null
  expense_id: string | null
  expense: null | { id: string; code: string; amount: number; currency: string; status: string; expense_date: string | null }
  status: 'pending' | 'matched' | 'discrepancy' | 'accepted'
  expected_amount: number | null; difference: number | null; issues: string[]; notes: string | null
  reconciled_at: string | null
}
export interface GastoCandidato {
  id: string; code: string; description: string; amount: number; currency: string; expense_date: string | null
  status: string; category: string; project_id: string | null; days_from_invoice: number | null
}
export interface PeriodoSinFactura {
  contract_id: string; contract_title: string; vendor_name: string | null; period_from: string; period_to: string
  expected_amount: number | null; currency: string | null; billing_cycle: string
}

export type Paginada<T> = { items: T[]; total: number }
type RespuestaLista<T> = { data: T[]; meta?: MetaDeLista; headers?: Record<string, string> }
const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const P = <T,>(p: Promise<unknown>) => p.then(r => {
  const resp = r as RespuestaLista<T>
  return { items: resp.data ?? [], total: resp.meta?.total ?? Number(resp.headers?.['x-total-count'] ?? (resp.data ?? []).length) }
})

export const almApi = {
  config: () => D<ConfigAlm>(api.get('/alm/config')),

  // Asignaciones e historial
  asignarLicencia: (licenseId: string, data: NuevaAsignacion) => D<Asignacion>(api.post(`/alm/licenses/${licenseId}/assign`, data)),
  asignarActivo: (assetId: string, data: NuevaAsignacion) => D<unknown>(api.post(`/alm/assets/${assetId}/assign`, data)),
  asignaciones: (params: Record<string, unknown>) => P<Asignacion>(api.get('/alm/assignments', { params })),
  cerrar: (id: string, kind: 'released' | 'revoked', reason?: string) =>
    D<Asignacion>(api.post(`/alm/assignments/${id}/end`, { kind, reason })),
  devolver: (id: string, data: { reason?: string; checklist?: FilaDeChecklist[]; condition?: Condicion; observations?: string; to_repair?: boolean }) =>
    D<Asignacion>(api.post(`/alm/assignments/${id}/return`, data)),
  historial: (params: Record<string, unknown>) => P<EventoAlm>(api.get('/alm/history', { params })),

  // Licencias
  clave: (licenseId: string) => D<{ license_key: string | null }>(api.get(`/alm/licenses/${licenseId}/key`)),
  uso: (licenseId: string) => D<UsoDeLicencia>(api.get(`/alm/licenses/${licenseId}/usage`)),
  picos: (licenseId: string) => D<PicoConcurrente[]>(api.get(`/alm/licenses/${licenseId}/peaks`)),
  anotarPico: (licenseId: string, peak: number) => D<unknown>(api.post(`/alm/licenses/${licenseId}/peaks`, { peak })),

  // Activos: ciclo de vida, actas y adjuntos
  ciclo: (assetId: string, action: string, reason?: string, data?: Record<string, unknown>) =>
    D<unknown>(api.post(`/alm/assets/${assetId}/lifecycle`, { action, reason, data })),
  adjuntosDeActivo: (assetId: string) => D<Adjunto[]>(api.get(`/alm/assets/${assetId}/attachments`)),
  subirAdjuntoDeActivo: (assetId: string, file: File, kind = 'photo') => {
    const fd = new FormData(); fd.append('file', file); fd.append('kind', kind)
    return D<{ id: string }>(api.post(`/alm/assets/${assetId}/attachments`, fd))
  },
  actas: (params: Record<string, unknown>) => D<Acta[]>(api.get('/alm/acts', { params })),
  misActas: () => D<Acta[]>(api.get('/alm/me/acts')),
  acta: (id: string) => D<Acta>(api.get(`/alm/acts/${id}`)),
  firmarActa: (id: string) => D<Acta>(api.post(`/alm/acts/${id}/sign`)),
  regenerarActa: (id: string) => D<Acta>(api.post(`/alm/acts/${id}/regenerate`)),
  anularActa: (id: string, reason?: string) => D<Acta>(api.post(`/alm/acts/${id}/void`, { reason })),
  subirFotoDeActa: (id: string, file: File) => {
    const fd = new FormData(); fd.append('file', file); fd.append('kind', 'photo')
    return D<{ id: string }>(api.post(`/alm/acts/${id}/attachments`, fd))
  },
  instalar: (assetId: string, data: { license_id: string; version?: string; notes?: string }) =>
    D<unknown>(api.post(`/alm/assets/${assetId}/installs`, data)),
  desinstalar: (assetId: string, installId: string) => D<unknown>(api.delete(`/alm/assets/${assetId}/installs/${installId}`)),

  // Costes (fase 3)
  costes: (params: { from?: string; to?: string; group_by?: Agrupacion; project_id?: string; currency?: string }) =>
    D<ResumenDeCostes>(api.get('/alm/costs', { params })),
  refacturable: (params: { from?: string; to?: string; currency?: string }) =>
    D<Refacturable>(api.get('/alm/costs/rebillable', { params })),

  // Renovaciones (fase 3)
  renovaciones: (days: number) => D<Renovacion[]>(api.get('/alm/renewals', { params: { days } })),
  decidir: (data: { entity_type: string; entity_id: string; decision: string; new_seats?: number | null; new_annual_cost?: number | null; reason?: string }) =>
    D<Renovacion>(api.post('/alm/renewals', data)),

  // Conciliación (fase 3)
  facturas: (params: Record<string, unknown>) => P<FacturaDeProveedor>(api.get('/alm/invoices', { params })),
  facturasQueFaltan: (months = 12) => D<PeriodoSinFactura[]>(api.get('/alm/invoices/missing', { params: { months } })),
  crearFactura: (data: Record<string, unknown>) => D<FacturaDeProveedor>(api.post('/alm/invoices', data)),
  editarFactura: (id: string, data: Record<string, unknown>) => D<FacturaDeProveedor>(api.patch(`/alm/invoices/${id}`, data)),
  borrarFactura: (id: string) => D<unknown>(api.delete(`/alm/invoices/${id}`)),
  conciliar: (id: string) => D<FacturaDeProveedor>(api.post(`/alm/invoices/${id}/reconcile`)),
  candidatos: (id: string) => D<GastoCandidato[]>(api.get(`/alm/invoices/${id}/candidates`)),
  enlazarGasto: (id: string, expense_id: string | null) => D<FacturaDeProveedor>(api.post(`/alm/invoices/${id}/expense`, { expense_id })),
  aceptarFactura: (id: string, note: string) => D<FacturaDeProveedor>(api.post(`/alm/invoices/${id}/accept`, { note })),
  adjuntosDeFactura: (id: string) => D<Adjunto[]>(api.get(`/alm/invoices/${id}/attachments`)),
  subirPdfDeFactura: (id: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return D<{ id: string }>(api.post(`/alm/invoices/${id}/attachments`, fd))
  },
}
