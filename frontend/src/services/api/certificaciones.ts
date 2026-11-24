/**
 * services/api/certificaciones.ts — Certificaciones y cumplimiento continuo (migración 212,
 * docs/CERTIFICACIONES.md). API: `/certificaciones` (app/api/v1/endpoints/certificaciones.py).
 *
 * Capacidades: `certificaciones.ver`, `.gestionar`, `.auditar` (con segregación de funciones
 * en el servidor) y `.administrar`. El interceptor de `_core` desenvuelve `{ data, meta }`.
 * La vista pública del auditor (`/auditor/:token`) usa `certPublicoApi` sin sesión.
 */
import api from './_core'
import { apiPublica } from './clienteBase'

export type EstadoMatriz = 'cumple' | 'en_curso' | 'pendiente' | 'no_cumple' | 'caducado' | 'no_aplica'
export type EstadoFila = 'pendiente' | 'en_curso' | 'implantado'
export type Eficacia = 'sin_evaluar' | 'eficaz' | 'parcial' | 'no_eficaz'

export interface Marco {
  id: string; clave: string; nombre: string; version: string | null; version_anterior: string | null
  publico: boolean; niveles: string[]; descripcion: string | null; controles: number
}
export interface Correspondencia {
  id: string; marco: string | null; id_control: string; id_semilla: string | null; nivel: string | null
  texto_oficial: string | null; afectado_por_version: boolean
}
export interface Control {
  id: string; clave_comun: string; titulo: string; descripcion: string | null; dominio: string | null
  evidencia_sugerida: string[]; medible_por_plataforma: string | null; editado: boolean; activo: boolean
  correspondencias: Correspondencia[]
}
export interface ParametroPlantilla {
  clave: string; tipo: 'entero' | 'booleano' | 'opcion'; opciones: string[] | null; por_defecto: unknown
}
export interface Plantilla {
  clave: string; nombre: string; marcos: string[]; parametros: ParametroPlantilla[]; fases: number; tareas: number
  condicionales: number; riesgos: number; documentos: number
}
export interface Objetivo { marco: string; nivel: string | null; niveles: string[] | null; sl_objetivo: string | null }
export interface Programa {
  id: string; codigo: string; nombre: string; descripcion: string | null; estado: string
  alcance: Record<string, unknown[]>; objetivos: Objetivo[]; responsable_id: string | null; responsable: string | null
  patrocinador_id: string | null; patrocinador: string | null; fecha_inicio: string | null
  fecha_objetivo: string | null; project_id: string | null; plantilla_clave: string | null
  parametros: Record<string, unknown>; filas?: number
}
export interface FilaSoA {
  id: string; programa_id: string; control_id: string; control: string; titulo: string; dominio: string | null
  medible: string | null; marcos: { marco: string; id_control: string; nivel: string | null }[]
  sede: string; aplica: boolean; justificacion: string | null; estado: EstadoFila; eficacia: Eficacia
  responsable_id: string | null; implantado_por: string | null; implantado_en: string | null
  eficacia_por: string | null; eficacia_en: string | null; ultima_revision: string | null
  medicion: string | null; medicion_en: string | null; evidencias: number; evidencias_validas: number
  evidencias_caducadas: number; estado_matriz: EstadoMatriz
}
export interface Matriz {
  programa_id: string; marcos: string[]; sedes: string[]; estados: EstadoMatriz[]
  controles: { control_id: string; control: string; titulo: string; dominio: string | null; fila_id: string
    marcos: { marco: string; id_control: string }[]; sedes: Record<string, EstadoMatriz> }[]
  totales_por_marco: Record<string, Record<EstadoMatriz, number>>
  totales_por_sede: Record<string, Record<EstadoMatriz, number>>
}
export interface Prueba {
  id: string; tipo: 'diseno' | 'eficacia_operativa'; periodo_desde: string | null; periodo_hasta: string | null
  poblacion: number | null; muestra: number | null; metodo: string | null; resultado: string
  excepciones: string | null; probado: string | null; probado_en: string | null; notas: string | null
}
export interface Evidencia {
  id: string; titulo: string; tipo: string; origen: string; programa_id: string | null
  aplicabilidad_id: string | null; control_id: string; control: string | null; control_titulo: string | null
  document_id: string | null; task_id: string | null; uri: string | null; sha256: string | null
  valida_desde: string | null; caduca_el: string | null
  estado: 'valida' | 'caducada' | 'pendiente_aprobacion' | 'pendiente'; created_at: string | null
}
export interface Accion {
  id: string; hallazgo_id: string; analisis_causa: string | null; plan: string; responsable_id: string | null
  responsable: string | null; fecha_limite: string | null; estado: string; vencida: boolean
  tarea: { id: string; code: string; status: string; project_id: string } | null
  hecho: string | null; verificado: string | null; verificacion: string | null
}
export interface Hallazgo {
  id: string; codigo: string; auditoria_id: string; programa_id: string; tipo: string; control: string | null
  titulo: string; descripcion: string | null; estado: string; fecha_limite: string | null; vencido: boolean
  corregido: string | null; cerrado: string | null; acciones?: Accion[]
}
export interface Auditoria {
  id: string; codigo: string; programa_id: string; tipo: string; marco: string | null; estado: string
  fecha_inicio: string | null; fecha_fin: string | null; entidad_id: string | null; entidad: string | null
  auditor_id: string | null; auditor: string | null; responsable: string | null; plan: string | null
  agenda: unknown[]; muestras: unknown[]; resultado: string | null; conclusion: string | null
  hallazgos: number; hallazgos_abiertos: number
}
export interface Entidad {
  id: string; nombre: string; tipo: string; acreditaciones: string[]; subcontractor_id: string | null
  contacto_email: string | null; web: string | null; notas: string | null; activo: boolean
}
export interface Auditor {
  id: string; entidad_id: string | null; entidad: string | null; nombre: string; email: string | null
  cualificaciones: string[]; independencia_declarada: boolean; conflictos_interes: string | null
  nda_firmado_el: string | null; desde: string | null; hasta: string | null; activo: boolean; suprimido: boolean
}
export interface Acceso {
  id: string; auditor: string | null; programa: string | null; desde: string; hasta: string
  revocado_en: string | null; ultimo_uso_en: string | null; usos: number; vigente: boolean
  token?: string; url?: string
}
export interface Certificado {
  id: string; numero: string; programa_id: string | null; marco: string | null; entidad: string | null
  entidad_id: string | null; alcance: string | null; nivel: string | null; emitido_el: string | null
  valido_hasta: string | null; dias_para_vencer: number | null; estado: string; enx_id: string | null
  enx_ambito: string | null; proxima_auditoria: string | null; tipo_proxima: string | null
}
export interface Reloj { plazo: string; enviado: string | null; estado: string; segundos_restantes: number | null }
export interface Incidente {
  id: string; codigo: string; titulo: string; descripcion: string | null; programa_id: string | null
  ticket: { id: string; number: string; title: string } | null; detectado_en: string; significativo: boolean
  transfronterizo: boolean; impacto: string | null; estado: string; autoridad: string | null
  responsable: string | null; relojes: Record<'alerta' | 'notificacion' | 'informe_final', Reloj>
  comunicaciones?: { id: string; tipo: string; destinatario: string | null; asunto: string | null
    contenido: string | null; referencia: string | null; enviado_en: string; enviado_por: string | null }[]
}
export interface ProveedorCritico {
  id: string; programa_id: string | null; subcontractor_id: string | null; nombre: string; criticidad: string
  servicios: string | null; resultado: string; riesgo: string | null; evaluado_por: string | null
  evaluado_en: string | null; proxima_evaluacion: string | null; vencida: boolean; notas: string | null
}
export interface Panel {
  por_norma: Record<string, Record<EstadoMatriz, number> & { avance: number | null }>
  carencias: { programa: string; fila_id: string; control: string; titulo: string; estado: EstadoMatriz }[]
  cobertura_evidencias: { filas: number; con_evidencia_valida: number; porcentaje: number | null }
  hallazgos_abiertos: number; hallazgos_por_tipo: Record<string, number>; acciones_vencidas: Accion[]
  certificados_por_vencer: Certificado[]; incidentes_nis2_abiertos: Incidente[]
}
export interface ConfigCert {
  aviso_certificado_dias: number; aviso_auditoria_dias: number; caducidad_evidencia_dias: number
  aviso_evidencia_dias: number; exigir_evidencia_aprobada: boolean; acceso_auditor_max_dias: number
  autoridad_nis2: string | null; nis2_alerta_horas: number; nis2_notificacion_horas: number
  nis2_informe_final_dias: number; proyecto_capa_id: string | null
}
export interface Validacion {
  marcos: number; controles: number; plantillas: number; documentos: number; errores: string[]; avisos: string[]
}
export interface VistaAuditor {
  programa: Programa; declaracion_de_aplicabilidad: FilaSoA[]; matriz: Matriz; evidencias: Evidencia[]
  pruebas: Prueba[]; auditorias: Auditoria[]; hallazgos: Hallazgo[]; acciones: Accion[]; certificados: Certificado[]
  acceso: { auditor: string | null; hasta: string }
}

type Datos = Record<string, unknown>
const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const B = '/certificaciones'

export const CLAVES_CERT = {
  todo: ['cert'] as const,
  panel: (p?: string) => ['cert', 'panel', p] as const,
  programas: ['cert', 'programas'] as const,
  plantillas: ['cert', 'plantillas'] as const,
  marcos: ['cert', 'marcos'] as const,
  controles: (f: Datos) => ['cert', 'controles', f] as const,
  aplicabilidad: (p: string, f: Datos) => ['cert', 'soa', p, f] as const,
  matriz: (p: string) => ['cert', 'matriz', p] as const,
  fila: (id: string, que: string) => ['cert', 'fila', id, que] as const,
  evidencias: (f: Datos) => ['cert', 'evidencias', f] as const,
  auditorias: (p?: string) => ['cert', 'auditorias', p] as const,
  hallazgos: (p?: string) => ['cert', 'hallazgos', p] as const,
  entidades: ['cert', 'entidades'] as const,
  auditores: ['cert', 'auditores'] as const,
  accesos: (p?: string) => ['cert', 'accesos', p] as const,
  certificados: ['cert', 'certificados'] as const,
  incidentes: ['cert', 'incidentes'] as const,
  proveedores: ['cert', 'proveedores'] as const,
  config: ['cert', 'config'] as const,
  validacion: ['cert', 'validacion'] as const,
  paquetes: (p: string) => ['cert', 'paquetes', p] as const,
}

export const certApi = {
  panel: (programa_id?: string) => D<Panel>(api.get(`${B}/panel`, { params: { programa_id } })),
  config: () => D<ConfigCert>(api.get(`${B}/config`)),
  guardarConfig: (c: Partial<ConfigCert>) => D<ConfigCert>(api.put(`${B}/config`, c)),
  marcos: () => D<Marco[]>(api.get(`${B}/catalogo/marcos`)),
  controles: (f: Datos = {}) => D<Control[]>(api.get(`${B}/catalogo/controles`, { params: f })),
  editarControl: (id: string, d: Datos) => D<Control>(api.patch(`${B}/catalogo/controles/${id}`, d)),
  revisada: (id: string) => D<{ ok: boolean }>(api.post(`${B}/catalogo/correspondencias/${id}/revisada`)),
  sembrar: () => D<Record<string, number>>(api.post(`${B}/catalogo/sembrar`)),
  validacion: () => D<Validacion>(api.get(`${B}/catalogo/validacion`)),
  importarTexto: (filas: Datos[], licencia?: Datos) =>
    D<{ actualizados: number; renombrados: number; sin_casar: Datos[] }>(api.post(`${B}/catalogo/texto-oficial`, { filas, licencia })),
  plantillas: () => D<Plantilla[]>(api.get(`${B}/plantillas`)),
  programas: () => D<Programa[]>(api.get(`${B}/programas`)),
  crearPrograma: (d: Datos) => D<Programa>(api.post(`${B}/programas`, d)),
  desdePlantilla: (d: Datos) => D<{ programa: Programa; project_code: string; tareas: number; documentos: number
    enlaces_tarea_control: number }>(api.post(`${B}/programas/desde-plantilla`, d)),
  editarPrograma: (id: string, d: Datos) => D<Programa>(api.patch(`${B}/programas/${id}`, d)),
  aplicabilidad: (id: string, f: Datos = {}) => D<FilaSoA[]>(api.get(`${B}/programas/${id}/aplicabilidad`, { params: f })),
  matriz: (id: string) => D<Matriz>(api.get(`${B}/programas/${id}/matriz`)),
  medir: (id: string) => D<{ medidas: number; evidencias_sistema: number; evidencias_tarea: number }>(
    api.post(`${B}/programas/${id}/medir`)),
  editarFila: (id: string, d: Datos) => D<FilaSoA>(api.patch(`${B}/aplicabilidad/${id}`, d)),
  eficacia: (id: string, eficacia: Eficacia, comentario?: string) =>
    D<FilaSoA>(api.post(`${B}/aplicabilidad/${id}/eficacia`, { eficacia, comentario })),
  dividirSede: (id: string, sede: string) => D<FilaSoA>(api.post(`${B}/aplicabilidad/${id}/sedes`, { sede })),
  tareasDeFila: (id: string) => D<{ id: string; code: string; title: string; status: string }[]>(
    api.get(`${B}/aplicabilidad/${id}/tareas`)),
  pruebas: (id: string) => D<Prueba[]>(api.get(`${B}/aplicabilidad/${id}/pruebas`)),
  registrarPrueba: (id: string, d: Datos) => D<Prueba>(api.post(`${B}/aplicabilidad/${id}/pruebas`, d)),
  evidenciasDeFila: (id: string) => D<Evidencia[]>(api.get(`${B}/aplicabilidad/${id}/evidencias`)),
  evidencias: (f: Datos = {}) => D<Evidencia[]>(api.get(`${B}/evidencias`, { params: f })),
  crearEvidencia: (d: Datos) => D<Evidencia>(api.post(`${B}/evidencias`, d)),
  borrarEvidencia: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/evidencias/${id}`)),
  auditorias: (programa_id?: string) => D<Auditoria[]>(api.get(`${B}/auditorias`, { params: { programa_id } })),
  crearAuditoria: (d: Datos) => D<Auditoria>(api.post(`${B}/auditorias`, d)),
  editarAuditoria: (id: string, d: Datos) => D<Auditoria>(api.patch(`${B}/auditorias/${id}`, d)),
  hallazgos: (programa_id?: string) => D<Hallazgo[]>(api.get(`${B}/hallazgos`, { params: { programa_id } })),
  crearHallazgo: (auditoria: string, d: Datos) => D<Hallazgo>(api.post(`${B}/auditorias/${auditoria}/hallazgos`, d)),
  corregido: (id: string) => D<Hallazgo>(api.post(`${B}/hallazgos/${id}/corregido`)),
  cerrarHallazgo: (id: string, comentario?: string) => D<Hallazgo>(api.post(`${B}/hallazgos/${id}/cerrar`, { comentario })),
  crearAccion: (hallazgo: string, d: Datos) => D<Accion>(api.post(`${B}/hallazgos/${hallazgo}/acciones`, d)),
  accionHecha: (id: string) => D<Accion>(api.post(`${B}/acciones/${id}/hecha`)),
  verificar: (id: string, eficaz: boolean, verificacion?: string) =>
    D<Accion>(api.post(`${B}/acciones/${id}/verificar`, { eficaz, verificacion })),
  entidades: () => D<Entidad[]>(api.get(`${B}/entidades`)),
  guardarEntidad: (d: Datos, id?: string) => D<Entidad>(id ? api.patch(`${B}/entidades/${id}`, d) : api.post(`${B}/entidades`, d)),
  auditores: () => D<Auditor[]>(api.get(`${B}/auditores`)),
  guardarAuditor: (d: Datos, id?: string) => D<Auditor>(id ? api.patch(`${B}/auditores/${id}`, d) : api.post(`${B}/auditores`, d)),
  suprimirAuditor: (id: string) => D<{ ok: boolean }>(api.post(`${B}/auditores/${id}/suprimir`)),
  copiaAuditor: (id: string) => D<Datos>(api.get(`${B}/auditores/${id}/rgpd`)),
  accesos: (programa_id?: string) => D<Acceso[]>(api.get(`${B}/accesos`, { params: { programa_id } })),
  conceder: (d: Datos) => D<Acceso>(api.post(`${B}/accesos`, d)),
  revocar: (id: string) => D<Acceso>(api.post(`${B}/accesos/${id}/revocar`)),
  registroDeAcceso: (id: string) => D<{ recurso: string; detalle: string | null; ip: string | null; en: string }[]>(
    api.get(`${B}/accesos/${id}/registro`)),
  certificados: () => D<Certificado[]>(api.get(`${B}/certificados`)),
  guardarCertificado: (d: Datos, id?: string) =>
    D<Certificado>(id ? api.patch(`${B}/certificados/${id}`, d) : api.post(`${B}/certificados`, d)),
  incidentes: () => D<Incidente[]>(api.get(`${B}/incidentes`)),
  incidente: (id: string) => D<Incidente>(api.get(`${B}/incidentes/${id}`)),
  crearIncidente: (d: Datos) => D<Incidente>(api.post(`${B}/incidentes`, d)),
  editarIncidente: (id: string, d: Datos) => D<Incidente>(api.patch(`${B}/incidentes/${id}`, d)),
  comunicar: (id: string, d: Datos) => D<Incidente>(api.post(`${B}/incidentes/${id}/comunicaciones`, d)),
  plantillaNis2: (id: string, tipo: string, idioma?: string) =>
    D<{ asunto: string; contenido: string }>(api.get(`${B}/incidentes/${id}/plantilla/${tipo}`, { params: { idioma } })),
  proveedores: () => D<ProveedorCritico[]>(api.get(`${B}/proveedores`)),
  guardarProveedor: (d: Datos, id?: string) =>
    D<ProveedorCritico>(id ? api.patch(`${B}/proveedores/${id}`, d) : api.post(`${B}/proveedores`, d)),
  paquete: (id: string) => D<Datos & { package_sha256: string }>(api.post(`${B}/programas/${id}/paquete`)),
  paquetes: (id: string) => D<{ id: string; sha256: string; generado_en: string; generado_por: string | null
    por_auditor: boolean }[]>(api.get(`${B}/programas/${id}/paquetes`)),
}

/** Vista pública del auditor externo: sin sesión, con el token del enlace. */
export const certPublicoApi = {
  vista: (token: string) => apiPublica.get(`${B}/auditor/${encodeURIComponent(token)}`)
    .then(r => (r.data?.data ?? r.data) as VistaAuditor),
  paquete: (token: string) => apiPublica.get(`${B}/auditor/${encodeURIComponent(token)}/paquete`)
    .then(r => (r.data?.data ?? r.data) as Datos),
}
