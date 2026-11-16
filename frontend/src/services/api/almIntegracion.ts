/**
 * services/api/almIntegracion.ts — licencias y hardware, fase 4: integración (16-11-2026).
 * Prefijo `/alm/integracion`. El interceptor de `_core` ya desenvuelve `{ data, meta }`.
 * Los errores llegan con un código `almint_*` o `alm_*`: la interfaz los traduce.
 */
import api from './_core'
import type { ParamsPeriodoApi } from '../../utils/periodo'

export interface TicketEnlazado {
  id: string; number: string; title: string; status: string; ticket_type: string
  approval_status?: string | null; created_at?: string | null
}
export interface ActaResumen {
  id: string; kind: 'delivery' | 'return'; status: string; asset_id: string; asset_name?: string | null
  assignment_id: string; condition?: string | null; envelope_id?: string | null; document_id?: string | null
  signed_at?: string | null; created_at?: string | null
}
export interface Devolucion {
  id: string; baja_id?: string | null; asset_id: string; asset_name?: string | null; asset_tag?: string | null
  user_id?: string | null; user_name?: string | null; origen: string; estado: string; condicion?: string | null
  notas?: string | null; fecha_limite?: string | null; vencida: boolean; ticket?: TicketEnlazado | null
  acta?: ActaResumen | null; created_at?: string | null; recibida_en?: string | null; cerrada_en?: string | null
}
export interface MiLicencia {
  assignment_id: string; license_id: string; name?: string | null; product_name?: string | null; edition?: string | null
  status: string; mode: string; from_pool: boolean; valid_from?: string | null; valid_to?: string | null; source?: string | null
}
export interface MiEquipo {
  assignment_id: string; asset_id: string; name?: string | null; type?: string | null; brand?: string | null
  model?: string | null; asset_tag?: string | null; serial_number?: string | null; mode: string
  valid_from?: string | null; valid_to?: string | null; overdue: boolean; days_to_due?: number | null
  devolucion?: Devolucion | null; averias_abiertas: TicketEnlazado[]; acta_entrega?: ActaResumen | null
}
export interface Peticion {
  id: string; tipo: 'licencia' | 'equipo'; estado: string; aprobacion?: string | null
  license_id?: string | null; license_name?: string | null; asset_type?: string | null; asset_id?: string | null
  project_id?: string | null; motivo?: string | null; beneficiario_id?: string | null; beneficiario_name?: string | null
  ticket?: TicketEnlazado | null; compra?: TicketEnlazado | null; error?: string | null
  created_at?: string | null; cumplida_en?: string | null
}
export interface HistorialPropio {
  assignment_id: string; name?: string | null; status: string; mode: string; end_kind?: string | null
  valid_from?: string | null; ended_on?: string | null
}
export interface MisRecursos {
  licencias: MiLicencia[]; equipos: MiEquipo[]; actas_pendientes: ActaResumen[]
  peticiones: Peticion[]; devoluciones: Devolucion[]; historial: HistorialPropio[]
}
export interface OpcionesDePeticion {
  puede_pedir_licencia: boolean; puede_pedir_equipo: boolean
  licencias: { id: string; name: string; product_name?: string | null }[]; tipos_de_equipo: string[]
}
export interface Baja {
  id: string; user_id: string; user_name?: string | null; motivo: string; estado: string
  fecha_efectiva?: string | null; licencias_liberar_en?: string | null; licencias_liberadas_en?: string | null
  licencias_liberadas: number; confirmada_con_pendientes: boolean
  devoluciones_total: number; devoluciones_pendientes: number; notas?: string | null
  created_at?: string | null; cerrada_en?: string | null
  devoluciones?: Devolucion[]; licencias_vigentes?: { assignment_id: string; license_id: string; name?: string | null }[]
}
export interface PreviaDeBaja {
  user_id: string; user_name: string; politica: 'avisar' | 'confirmar' | 'bloquear'; dias_para_liberar: number
  licencias: { assignment_id: string; license_id: string; name?: string | null; status: string }[]
  equipos: { assignment_id: string; asset_id: string; name?: string | null; asset_tag?: string | null; mode: string; valid_to?: string | null; devolucion_abierta: boolean }[]
  baja_abierta?: Baja | null
}
export interface ElementoDeKit {
  clave?: string; tipo: 'licencia' | 'equipo'; license_id?: string | null; license_name?: string | null
  asset_type?: string | null; cantidad: number; notas?: string | null
  disponible?: boolean; libres?: number | null; bolsa?: boolean
  resultado?: string; assignment_id?: string; asset_id?: string; asset_name?: string; ticket_id?: string; ticket_number?: string; codigo?: string
}
export interface Kit {
  id: string; nombre: string; descripcion?: string | null; criterio: string; valor?: string | null
  is_active: boolean; elementos: ElementoDeKit[]
}
export interface PropuestaDeKit {
  id: string; user_id: string; user_name?: string | null; user_job_title?: string | null; user_department?: string | null
  responsable_id?: string | null; responsable_name?: string | null; estado: string
  kits: { id: string; nombre: string }[]; elementos: ElementoDeKit[]; resultado?: ElementoDeKit[] | { motivo?: string } | null
  puedo_decidir?: boolean | null; created_at?: string | null; decidida_en?: string | null
}
export interface ItemDeCatalogoAlm {
  id: string; service_item_id: string; service_item_name?: string | null; service_item_active: boolean
  requires_catalog_approval: boolean; approval: 'none' | 'single' | 'engine'; tipo: 'licencia' | 'equipo'
  license_id?: string | null; license_name?: string | null; asset_type?: string | null
}
export interface AsignacionAlm {
  id: string; resource_type: 'license' | 'asset'; license_id?: string | null; asset_id?: string | null
  resource_name?: string | null; holder_type: string; holder_id?: string | null; holder_name?: string | null
  mode: string; parent_id?: string | null; quantity: number; status: string
  valid_from?: string | null; valid_to?: string | null; used_in_pool?: number | null; overdue?: boolean
  asset_tag?: string | null; asset_type?: string | null
}
export interface CosteAgrupado {
  resource_type: string; resource_id: string; resource_name: string; kind: string; amount: number; days: number; currency: string
}
export interface RecursosDelProyecto {
  project_id: string; desde: string; hasta: string; puedo_gestionar: boolean
  licencias_del_proyecto: { id: string; name: string; total_seats?: number | null }[]
  bolsas: (AsignacionAlm & { hijas: AsignacionAlm[] })[]
  asignaciones: AsignacionAlm[]
  equipo: { user_id: string; user_name: string; licencias: AsignacionAlm[]; equipos: AsignacionAlm[] }[]
  coste: null | {
    moneda?: string | null; imputado: number; del_equipo_fuera: number; ocioso: number; rebillable: number
    por_recurso: CosteAgrupado[]; del_equipo_por_recurso: CosteAgrupado[]
  }
}

export interface RecursoEnlazado {
  tipo: 'asset' | 'license'; id: string; name: string; asset_tag?: string | null; serial_number?: string | null
  status?: string | null; type?: string | null; holder_name?: string | null; product_name?: string | null
}

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const B = '/alm/integracion'

export const almIntegracionApi = {
  // Autoservicio
  mio: () => D<MisRecursos>(api.get(`${B}/mio`)),
  opciones: () => D<OpcionesDePeticion>(api.get(`${B}/mio/opciones`)),
  pedir: (datos: { tipo: 'licencia' | 'equipo'; license_id?: string; asset_type?: string; project_id?: string; motivo?: string; hasta?: string }) =>
    D<Peticion>(api.post(`${B}/mio/peticiones`, datos)),
  devolver: (aid: string, motivo?: string) => D<Devolucion>(api.post(`${B}/mio/asignaciones/${aid}/devolver`, { motivo })),
  dejar: (aid: string, motivo?: string) => D<{ ok: boolean }>(api.post(`${B}/mio/asignaciones/${aid}/dejar`, { motivo })),
  averia: (aid: string, descripcion: string, urgencia: string) =>
    D<TicketEnlazado>(api.post(`${B}/mio/asignaciones/${aid}/averia`, { descripcion, urgencia })),
  verActa: (id: string) => D<ActaResumen & { pdf_url?: string | null; checklist?: { item: string; ok: boolean; note?: string }[]; observations?: string | null; esign_provider?: string | null }>(api.get(`${B}/mio/actas/${id}`)),
  firmarActa: (id: string) => D<ActaResumen>(api.post(`${B}/mio/actas/${id}/firmar`)),
  // Bajas y devoluciones
  bajas: (estado?: string) => D<Baja[]>(api.get(`${B}/bajas`, { params: estado ? { estado } : {} })),
  baja: (id: string) => D<Baja>(api.get(`${B}/bajas/${id}`)),
  programarBaja: (datos: { user_id: string; fecha: string; notas?: string }) => D<Baja>(api.post(`${B}/bajas/programar`, datos)),
  anularBaja: (id: string) => D<Baja>(api.post(`${B}/bajas/${id}/anular`)),
  previaDeBaja: (userId: string) => D<PreviaDeBaja>(api.get(`${B}/personas/${userId}/previa-baja`)),
  devoluciones: (estado?: string) => D<Devolucion[]>(api.get(`${B}/devoluciones`, { params: estado ? { estado } : {} })),
  recibir: (id: string, datos: { condition?: string; observations?: string; a_reparar?: boolean }) =>
    D<Devolucion>(api.post(`${B}/devoluciones/${id}/recibir`, datos)),
  perdida: (id: string, motivo: string) => D<Devolucion>(api.post(`${B}/devoluciones/${id}/perdida`, { motivo })),
  // Kits
  kits: () => D<Kit[]>(api.get(`${B}/kits`)),
  crearKit: (datos: Omit<Kit, 'id' | 'is_active'>) => D<Kit>(api.post(`${B}/kits`, datos)),
  cambiarKit: (id: string, datos: Omit<Kit, 'id' | 'is_active'>) => D<Kit>(api.put(`${B}/kits/${id}`, datos)),
  borrarKit: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/kits/${id}`)),
  propuestas: (estado?: string) => D<PropuestaDeKit[]>(api.get(`${B}/propuestas`, { params: estado ? { estado } : {} })),
  confirmarPropuesta: (id: string, claves?: string[]) => D<PropuestaDeKit>(api.post(`${B}/propuestas/${id}/confirmar`, { claves })),
  descartarPropuesta: (id: string, motivo?: string) => D<PropuestaDeKit>(api.post(`${B}/propuestas/${id}/descartar`, { motivo })),
  proponerKit: (userId: string) => D<PropuestaDeKit | null>(api.post(`${B}/personas/${userId}/proponer-kit`)),
  // Catálogo
  itemsDeCatalogo: () => D<ItemDeCatalogoAlm[]>(api.get(`${B}/catalogo/items`)),
  guardarItem: (datos: { service_item_id: string; tipo: string; license_id?: string | null; asset_type?: string | null }) =>
    D<ItemDeCatalogoAlm>(api.post(`${B}/catalogo/items`, datos)),
  crearItems: (category_id: string, nombres: { licencia: string; equipo: string }) =>
    D<ItemDeCatalogoAlm[]>(api.post(`${B}/catalogo/items/crear`, { category_id, nombres })),
  borrarItem: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/catalogo/items/${id}`)),
  peticiones: (estado?: string) => D<Peticion[]>(api.get(`${B}/peticiones`, { params: estado ? { estado } : {} })),
  reintentar: (id: string) => D<Peticion>(api.post(`${B}/peticiones/${id}/reintentar`)),
  // Proyecto
  /** Periodo libre (16-11-2026): `params` de `usePeriodo` (`hasta` exclusivo; el coste es por día). */
  recursosDelProyecto: (projectId: string, params?: ParamsPeriodoApi) =>
    D<RecursosDelProyecto>(api.get(`${B}/proyectos/${projectId}/recursos`, { params: params ?? {} })),
  asignarAlProyecto: (projectId: string, datos: { holder_type: 'project' | 'user'; holder_id?: string; license_id?: string; asset_id?: string; mode?: 'loan'; quantity?: number; parent_id?: string; valid_to?: string; reason?: string }) =>
    D<AsignacionAlm>(api.post(`${B}/proyectos/${projectId}/asignar`, datos)),
  liberarDelProyecto: (projectId: string, aid: string, motivo?: string) =>
    D<AsignacionAlm>(api.post(`${B}/proyectos/${projectId}/asignaciones/${aid}/liberar`, { motivo })),
  // Ticket ↔ recurso
  ticketsDelRecurso: (tipo: 'asset' | 'license', id: string) => D<TicketEnlazado[]>(api.get(`${B}/recursos/${tipo}/${id}/tickets`)),
  recursoDelTicket: (ticketId: string) => D<RecursoEnlazado | null>(api.get(`${B}/tickets/${ticketId}/recurso`)),
}
