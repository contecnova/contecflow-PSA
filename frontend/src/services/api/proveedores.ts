/**
 * services/api/proveedores.ts — `/suppliers` (proveedores y externalización, 19-11-2026).
 *
 * Contrato en docs/PROVEEDORES_Y_EXTERNALIZACION.md §9. Lectura: gestores;
 * escritura, finanzas y GRC: admin/PM. El interceptor de `_core` ya
 * desenvuelve `{ data, meta }`. El CRUD básico del proveedor, sus personas,
 * asignaciones, partes y facturas siguen en `/enterprise/subcontractors`
 * (`subcontractorsApi`, `enterpriseSubsApi`).
 */
import type { AxiosResponse } from 'axios'
import api from './_core'
import type { Subcontratista } from './tipos-alm'
import type {
  AccesoDeProveedor, AccesoIn, AltaDeFreelanceIn, ClasificacionIn, ConsumoDeProveedor, ConsumoIn, ContratoDeProveedor,
  ContratoIn, CumplimientoDeProveedor, DocumentoDeProveedor, DocumentoIn, EstadoDeCuenta, EvaluacionDeRiesgo, EvaluacionIn,
  ExternalizadoDelProyecto, FichaDeProveedor, FreelanceCreado, InformeDeProveedor, InformeIn, LineaDePrecio, LineaIn,
  MetaDeProveedores, PanoramaDeProveedores, PaqueteDeTrabajo, PaqueteIn, PrevisionDeContrato, ProveedorAsignable,
  PuntuacionDeProveedor, ServicioDeProveedor, ServicioIn, SlaDeServicio,
  ConfigDeMedicion, ConsumoDelPortal, ContactoDelPortal, FilaDeRecuento, FuenteDeMedicion, MedicionHecha, PortalYo,
  RecuentoIn, ReferenciasDeProveedores, ResultadoDeImportacionDeRecuentos, VistaPreviaDeMedicion,
} from './tipos-proveedores'

type R<T> = Promise<AxiosResponse<T>>
type Periodo = { desde?: string; hasta?: string }
const B = '/suppliers'

export const proveedoresApi = {
  // ── Ficha y clasificación ──────────────────────────────────────────────────
  meta: (): R<MetaDeProveedores> => api.get(`${B}/meta`),
  panorama: (): R<PanoramaDeProveedores> => api.get(`${B}/overview`),
  asignables: (projectId?: string | null): R<ProveedorAsignable[]> =>
    api.get(`${B}/assignable`, { params: projectId ? { project_id: projectId } : undefined }),
  altaFreelance: (d: AltaDeFreelanceIn): R<FreelanceCreado> => api.post(`${B}/freelance`, d),
  ficha: (id: string): R<FichaDeProveedor> => api.get(`${B}/${id}/profile`),
  clasificar: (id: string, d: ClasificacionIn): R<Subcontratista> => api.patch(`${B}/${id}/classification`, d),
  suspender: (id: string, reason?: string | null): R<Subcontratista> => api.post(`${B}/${id}/suspend`, { reason: reason || null }),
  reactivar: (id: string, reason?: string | null): R<Subcontratista> => api.post(`${B}/${id}/reactivate`, { reason: reason || null }),
  darDeBaja: (id: string, reason?: string | null): R<Subcontratista> => api.post(`${B}/${id}/offboard`, { reason: reason || null }),

  // ── Contratos, plantillas y líneas de precio ───────────────────────────────
  contratos: (id: string): R<ContratoDeProveedor[]> => api.get(`${B}/${id}/contracts`),
  crearContrato: (id: string, d: ContratoIn): R<ContratoDeProveedor> => api.post(`${B}/${id}/contracts`, d),
  editarContrato: (cid: string, d: ContratoIn): R<ContratoDeProveedor> => api.patch(`${B}/contracts/${cid}`, d),
  activarContrato: (cid: string): R<ContratoDeProveedor> => api.post(`${B}/contracts/${cid}/activate`),
  terminarContrato: (cid: string): R<ContratoDeProveedor> => api.post(`${B}/contracts/${cid}/terminate`),
  plantillas: (): R<ContratoDeProveedor[]> => api.get(`${B}/contract-templates`),
  crearPlantilla: (d: ContratoIn): R<ContratoDeProveedor> => api.post(`${B}/contract-templates`, d),
  editarPlantilla: (tid: string, d: ContratoIn): R<ContratoDeProveedor> => api.patch(`${B}/contract-templates/${tid}`, d),
  borrarPlantilla: (tid: string): R<unknown> => api.delete(`${B}/contract-templates/${tid}`),
  contratoDesdePlantilla: (id: string, tid: string): R<ContratoDeProveedor> => api.post(`${B}/${id}/contracts/from-template/${tid}`),
  crearLinea: (cid: string, d: LineaIn): R<LineaDePrecio> => api.post(`${B}/contracts/${cid}/pricing`, d),
  editarLinea: (lid: string, d: LineaIn): R<LineaDePrecio> => api.patch(`${B}/pricing/${lid}`, d),
  borrarLinea: (lid: string): R<unknown> => api.delete(`${B}/pricing/${lid}`),

  // ── Servicios gestionados ──────────────────────────────────────────────────
  servicios: (id: string): R<ServicioDeProveedor[]> => api.get(`${B}/${id}/services`),
  crearServicio: (id: string, d: ServicioIn): R<ServicioDeProveedor> => api.post(`${B}/${id}/services`, d),
  editarServicio: (sid: string, d: ServicioIn): R<ServicioDeProveedor> => api.patch(`${B}/services/${sid}`, d),
  terminarServicio: (sid: string): R<ServicioDeProveedor> => api.post(`${B}/services/${sid}/end`),
  slaDeServicio: (sid: string, p: Periodo = {}): R<SlaDeServicio> => api.get(`${B}/services/${sid}/sla`, { params: p }),

  // ── Paquetes de trabajo (outsourcing) e informes ───────────────────────────
  paquetes: (id: string): R<PaqueteDeTrabajo[]> => api.get(`${B}/${id}/work-packages`),
  crearPaquete: (id: string, d: PaqueteIn): R<PaqueteDeTrabajo> => api.post(`${B}/${id}/work-packages`, d),
  editarPaquete: (wid: string, d: PaqueteIn): R<PaqueteDeTrabajo> => api.patch(`${B}/work-packages/${wid}`, d),
  /** Ciclo del paquete: iniciar, entregar, aceptar o cancelar. */
  pasoDePaquete: (wid: string, paso: 'start' | 'deliver' | 'accept' | 'cancel'): R<PaqueteDeTrabajo> =>
    api.post(`${B}/work-packages/${wid}/${paso}`),
  rechazarPaquete: (wid: string, reason: string): R<PaqueteDeTrabajo> => api.post(`${B}/work-packages/${wid}/reject`, { reason }),
  tareasAlPaquete: (wid: string, taskIds: string[]): R<PaqueteDeTrabajo> => api.post(`${B}/work-packages/${wid}/tasks`, { task_ids: taskIds }),
  externalizadoDelProyecto: (projectId: string): R<ExternalizadoDelProyecto> => api.get(`${B}/by-project/${projectId}`),
  informes: (id: string): R<InformeDeProveedor[]> => api.get(`${B}/${id}/reports`),
  crearInforme: (id: string, d: InformeIn): R<InformeDeProveedor> => api.post(`${B}/${id}/reports`, d),
  revisarInforme: (rid: string, reviewNotes?: string | null): R<InformeDeProveedor> =>
    api.post(`${B}/reports/${rid}/review`, { review_notes: reviewNotes || null }),

  // ── Consumo, previsión y estados de cuenta ─────────────────────────────────
  consumos: (id: string): R<ConsumoDeProveedor[]> => api.get(`${B}/${id}/usage`),
  crearConsumo: (id: string, d: ConsumoIn): R<ConsumoDeProveedor> => api.post(`${B}/${id}/usage`, d),
  borrarConsumo: (uid: string): R<unknown> => api.delete(`${B}/usage/${uid}`),
  prevision: (cid: string, p: Periodo = {}): R<PrevisionDeContrato> => api.get(`${B}/contracts/${cid}/forecast`, { params: p }),
  cerrarPeriodo: (cid: string, periodStart: string, periodEnd: string): R<EstadoDeCuenta> =>
    api.post(`${B}/contracts/${cid}/statements`, { period_start: periodStart, period_end: periodEnd }),
  estadosDeCuenta: (id: string): R<EstadoDeCuenta[]> => api.get(`${B}/${id}/statements`),
  conciliar: (stid: string, invoiceId: string): R<EstadoDeCuenta> => api.post(`${B}/statements/${stid}/reconcile`, { invoice_id: invoiceId }),
  aprobarEstado: (stid: string): R<EstadoDeCuenta> => api.post(`${B}/statements/${stid}/approve`),
  disputarEstado: (stid: string, reason: string): R<EstadoDeCuenta> => api.post(`${B}/statements/${stid}/dispute`, { reason }),

  // ── GRC de terceros ────────────────────────────────────────────────────────
  cumplimiento: (id: string): R<CumplimientoDeProveedor> => api.get(`${B}/${id}/compliance`),
  crearDocumento: (id: string, d: DocumentoIn): R<DocumentoDeProveedor> => api.post(`${B}/${id}/documents`, d),
  editarDocumento: (did: string, d: DocumentoIn): R<DocumentoDeProveedor> => api.patch(`${B}/documents/${did}`, d),
  borrarDocumento: (did: string): R<unknown> => api.delete(`${B}/documents/${did}`),
  evaluaciones: (id: string): R<EvaluacionDeRiesgo[]> => api.get(`${B}/${id}/risk-assessments`),
  crearEvaluacion: (id: string, d: EvaluacionIn): R<EvaluacionDeRiesgo> => api.post(`${B}/${id}/risk-assessments`, d),
  crearAcceso: (id: string, d: AccesoIn): R<AccesoDeProveedor> => api.post(`${B}/${id}/access-grants`, d),
  revocarAcceso: (gid: string, reason?: string | null): R<AccesoDeProveedor> => api.post(`${B}/access-grants/${gid}/revoke`, { reason: reason || null }),

  // ── Rendimiento ────────────────────────────────────────────────────────────
  puntuacion: (id: string, p: Periodo = {}): R<PuntuacionDeProveedor> => api.get(`${B}/${id}/scorecard`, { params: p }),

  // ── Migración 191 ──────────────────────────────────────────────────────────
  /** Datos reales para los selectores (presupuestos, centros de coste, contratos ALM, catálogo SD, UAT, CMDB). */
  referencias: (p: { project_id?: string | null; sub_id?: string | null } = {}): R<ReferenciasDeProveedores> =>
    api.get(`${B}/references`, { params: Object.fromEntries(Object.entries(p).filter(([, v]) => !!v)) }),
  contactosDelPortal: (id: string): R<ContactoDelPortal[]> => api.get(`${B}/${id}/portal-contacts`),
  marcarContacto: (id: string, workerId: string, activo: boolean): R<ContactoDelPortal[]> =>
    api.put(`${B}/${id}/portal-contacts/${workerId}`, { supplier_portal: activo }),
  adjuntarAlInforme: (rid: string, fichero: File): R<InformeDeProveedor> => {
    const datos = new FormData()
    datos.append('file', fichero)
    return api.post(`${B}/reports/${rid}/attachments`, datos)
  },
  abrirAdjunto: (rid: string, docId: string): R<{ url: string; name: string; mime: string | null }> =>
    api.get(`${B}/reports/${rid}/attachments/${docId}/open`),
  medirAhora: (sid: string): R<MedicionHecha> => api.post(`${B}/services/${sid}/metering/measure`),
  ingerirRecuento: (sid: string, d: RecuentoIn): R<ConsumoDeProveedor> => api.post(`${B}/services/${sid}/metering/ingest`, d),
  importarRecuentos: (id: string, rows: FilaDeRecuento[]): R<ResultadoDeImportacionDeRecuentos> =>
    api.post(`${B}/${id}/metering/import`, { rows }),
  vistaPreviaDeMedicion: (fuente: FuenteDeMedicion, config: ConfigDeMedicion, unit?: string | null): R<VistaPreviaDeMedicion> =>
    api.post(`${B}/metering/preview`, { metering_source: fuente, metering_config: config, unit: unit || null }),
}

const P = '/supplier-portal'

/** Portal del proveedor (`/supplier-portal`): solo lo del proveedor de quien llama. */
export const portalProveedorApi = {
  yo: (): R<PortalYo> => api.get(`${P}/me`),
  paquetes: (): R<PaqueteDeTrabajo[]> => api.get(`${P}/work-packages`),
  servicios: (): R<ServicioDeProveedor[]> => api.get(`${P}/services`),
  sla: (sid: string, p: Periodo = {}): R<SlaDeServicio> => api.get(`${P}/services/${sid}/sla`, { params: p }),
  informes: (): R<InformeDeProveedor[]> => api.get(`${P}/reports`),
  crearInforme: (d: InformeIn): R<InformeDeProveedor> => api.post(`${P}/reports`, d),
  adjuntar: (rid: string, fichero: File): R<InformeDeProveedor> => {
    const datos = new FormData()
    datos.append('file', fichero)
    return api.post(`${P}/reports/${rid}/attachments`, datos)
  },
  abrirAdjunto: (rid: string, docId: string): R<{ url: string; name: string; mime: string | null }> =>
    api.get(`${P}/reports/${rid}/attachments/${docId}/open`),
  consumo: (p: Periodo = {}): R<ConsumoDelPortal> => api.get(`${P}/usage`, { params: p }),
  estadosDeCuenta: (): R<EstadoDeCuenta[]> => api.get(`${P}/statements`),
}
