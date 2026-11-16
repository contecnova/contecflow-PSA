/**
 * services/api/almUso.ts — licencias y hardware, fase 2: uso real (16-11-2026).
 * Prefijo `/alm/uso`. El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 */
import api from './_core'

export type EstadoDeUso = 'en_uso' | 'infrautilizada' | 'sin_uso' | 'sin_datos'
export type Fiabilidad = 'alta' | 'media' | 'baja'

export interface FuenteDeEvidencia {
  fuente: string; ultimo_uso: string | null; fiabilidad: Fiabilidad; leido_at: string | null
  frecuencia: number | null; periodo_dias: number | null; asignada_en_fuente: boolean | null; vista: boolean
  producto: string
}

export interface UsoDeAsignacion {
  assignment_id: string; license_id: string; holder_type: string; user_id: string | null; asset_id: string | null
  persona?: string | null; equipo?: string | null; licencia?: string | null; mode?: string; valid_from?: string | null
  estado: EstadoDeUso; motivo: string; ultimo_uso: string | null; dias_sin_uso: number | null
  dias_sin_uso_efectivos: number | null; dias_ausencia: number; en_ausencia: boolean; frecuencia: number | null
  periodo_dias: number | null; fuente: string | null; fiabilidad: Fiabilidad | null; leido_at: string | null
  datos_desactualizados: boolean; cuenta_desactivada: boolean; fuentes: FuenteDeEvidencia[]
  servicios: Record<string, string>
}

export interface UsoDeLicencia {
  license_id: string; nombre: string; metric: string; estado: EstadoDeUso; asignados: number; total: number | null
  en_uso: number; infrautilizadas: number; sin_uso: number; sin_datos: number; uso_sin_asignacion: number
  pico_concurrente: number | null; pico_medido_en: string | null; ultimo_uso: string | null
  fuente: string | null; fuentes: string[]; medido_en: string | null; asignaciones?: UsoDeAsignacion[]
}

export interface UsoDeEquipo {
  asset_id: string; nombre: string; serie: string | null; tipo: string; estado_activo: string
  asignado_a: string | null; asignado_a_nombre: string | null; usuario_en_fuente: string | null
  usuario_en_fuente_nombre: string | null; discrepancia_de_usuario: boolean; estado: EstadoDeUso; motivo: string
  ultimo_uso: string | null; dias_sin_uso: number | null; fuente: string | null; fiabilidad: Fiabilidad | null
  leido_at: string | null; datos_desactualizados: boolean
}

export interface PanelDeUso {
  asignados: number; en_uso: number; infrautilizadas: number; sin_uso: number; sin_datos: number
  licencias: number; licencias_sin_datos: number; coste_anual_sin_uso: number; moneda: string
  fuentes_activas: number; fuentes_con_error: number; ultima_lectura: string | null
  recuperaciones: { abiertas: number; pendientes_de_aprobacion: number; liberadas: number; ahorro_anual_liberado: number }
  ahorro_por_ajuste: number
}

export interface Sincronizacion {
  id: string; proveedor: string; origen: string; estado: 'en_curso' | 'ok' | 'parcial' | 'error'
  iniciada_at: string | null; terminada_at: string | null; leidos: number; nuevas: number; actualizadas: number
  sin_titular: number; sin_licencia: number; dispositivos: number
  errores: { codigo: string; mensaje: string }[]; avisos: { codigo: string; mensaje: string }[]
}

export interface CampoDeCredencial { clave: string; etiqueta: string; secreto: boolean; configurado: boolean; valor: string | null }

export interface Conexion {
  clave: string; etiqueta: string; credencial: string | null; obligatorias: string[]; fiabilidad: Fiabilidad
  tipo: 'externo' | 'interno' | 'agente'; permisos: string[]; aporta: string[]
  opciones: { clave: string; descripcion: string }[]
  conexion_id: string | null; activa: boolean; fiabilidad_efectiva: Fiabilidad; fiabilidad_propia: Fiabilidad | null
  configuracion: Record<string, unknown>; credenciales: CampoDeCredencial[]; faltan: string[]; lista: boolean
  ultima_sincronizacion_at: string | null; ultimo_estado: string; ultimo_error: string | null
  ultima: Sincronizacion | null
}

export interface ProductoDeFuente {
  fuente: string; producto: string; nombre: string; titulares: number; license_id: string | null
  licencia: string | null; mapeo: 'manual' | 'ignorado' | 'automatico' | null
  sugerencia: { license_id: string; nombre: string; parecido: number } | null
}

export interface Recuperacion {
  id: string; assignment_id: string; license_id: string; user_id: string | null; asset_id: string | null
  persona?: string | null; equipo?: string | null; licencia?: string | null
  estado: 'aviso_persona' | 'aviso_responsable' | 'pendiente_aprobacion' | 'liberada' | 'conservada' | 'cancelada' | 'rechazada'
  politica: string | null; dias_sin_uso: number | null; coste_anual: number | null
  iniciada_at: string | null; siguiente_paso_at: string | null; conservar_hasta: string | null
  cerrada_at: string | null; motivo: string | null
  historial: { at: string; paso: string; detalle: string; por: string | null }[]
}

export interface ListaDeRecuperaciones {
  items: Recuperacion[]
  kpis: { abiertas: number; pendientes_de_aprobacion: number; liberadas: number; ahorro_anual_liberado: number }
}

export interface Simulacion {
  resumen: { iniciaria: number; avanzaria: number; cerraria_por_uso: number; protegida: number; sin_politica: number
    ahorro_anual_potencial: number }
  items: { assignment_id: string; license_id: string; licencia: string; persona?: string | null; equipo?: string | null
    accion: 'iniciaria' | 'avanzaria' | 'cerraria_por_uso' | 'protegida' | 'sin_politica'; motivo: string | null
    estado_actual: string | null; estado_de_uso: EstadoDeUso; dias_sin_uso_efectivos: number | null
    fuente: string | null; fiabilidad: Fiabilidad | null; coste_anual: number | null; politica: string | null }[]
}

export interface PropuestaDeAjuste {
  nivel_id: string; assignment_id: string; user_id: string | null; asset_id: string | null
  persona?: string | null; equipo?: string | null; license_superior_id: string; superior: string
  license_inferior_id: string; inferior: string; servicios_que_justifican: string[]; servicios_usados: string[]
  ultimo_uso: string | null; fuente: string | null; fiabilidad: Fiabilidad | null; ahorro_anual: number | null
  moneda: string
}

export interface ReglaDeNivel {
  id: string; license_superior_id: string; superior: string | null; license_inferior_id: string
  inferior: string | null; servicios: string[]; activa: boolean; notas: string | null
}

export interface SugerenciaDeNivel {
  license_superior_id: string; superior: string; tier_superior: string | null
  license_inferior_id: string; inferior: string; tier_inferior: string | null
}

export interface PosicionDeLicencia {
  license_id: string; nombre: string; producto: string | null; edicion: string | null; sku: string | null
  metrica: string; tipo: string; derechos: number | null; comprados_segun_fuente: number | null; fuentes: string[]
  consumo: number; base_del_consumo: string; asignados: number; personas_en_fuente: number; equipos: number
  pico: number | null; posicion: number | null; estado: 'deficit' | 'excedente' | 'conforme' | 'sin_limite'
  coste_unitario_anual: number | null; moneda: string; exposicion: number | null; coste_ocioso: number | null
  caduca: string | null; requiere_cumplimiento: boolean; incidencias: string[]
}

export interface Cumplimiento {
  items: PosicionDeLicencia[]
  kpis: { licencias: number; deficit: number; excedente: number; conforme: number; con_incidencias: number
    exposicion: number; coste_ocioso: number }
}

export interface CandidatoNoControlado {
  id: string; nombre: string; clave: string
  origenes: Record<string, { usuarios: number; dispositivos: number; apariciones: number }>
  usuarios: number; dispositivos: number; apariciones: number; importe: number | null; moneda: string | null
  primera_vez: string | null; ultima_vez: string | null; estado: 'nuevo' | 'dado_de_alta' | 'descartado'
  license_id: string | null
  propuesta: { name: string; product_name: string; metric: string; type: string; total_seats: number | null
    annual_cost: number | null; notes: string }
}

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export const almUsoApi = {
  panel: () => D<PanelDeUso>(api.get('/alm/uso/panel')),
  licencias: (conAsignaciones = false) =>
    D<UsoDeLicencia[]>(api.get('/alm/uso/licencias', { params: { con_asignaciones: conAsignaciones } })),
  licencia: (id: string) => D<UsoDeLicencia>(api.get(`/alm/uso/licencias/${id}`)),
  asignacion: (id: string) => D<UsoDeAsignacion>(api.get(`/alm/uso/asignaciones/${id}`)),
  equipos: () => D<UsoDeEquipo[]>(api.get('/alm/uso/equipos')),

  conexiones: () => D<Conexion[]>(api.get('/alm/uso/conexiones')),
  guardarConexion: (clave: string, datos: { activa?: boolean; fiabilidad?: string | null
    configuracion?: Record<string, unknown>; credenciales?: Record<string, string> }) =>
    D<Conexion>(api.put(`/alm/uso/conexiones/${clave}`, datos)),
  probar: (clave: string) =>
    D<{ ok: boolean; codigo?: string; mensaje?: string } & Record<string, unknown>>(api.post(`/alm/uso/conexiones/${clave}/probar`)),
  sincronizar: (conexionId: string) => D<Sincronizacion>(api.post(`/alm/uso/conexiones/${conexionId}/sincronizar`)),
  sincronizaciones: (conexionId?: string) =>
    D<Sincronizacion[]>(api.get('/alm/uso/sincronizaciones', { params: { conexion_id: conexionId } })),
  productos: (soloSinLicencia = false) =>
    D<ProductoDeFuente[]>(api.get('/alm/uso/mapeos', { params: { solo_sin_licencia: soloSinLicencia } })),
  mapear: (datos: { fuente: string; producto: string; license_id: string | null; ignorar: boolean }) =>
    D<{ evidencias: number }>(api.put('/alm/uso/mapeos', datos)),

  recuperaciones: (estado?: string) =>
    D<ListaDeRecuperaciones>(api.get('/alm/uso/recuperaciones', { params: { estado } })),
  simulacion: () => D<Simulacion>(api.get('/alm/uso/recuperaciones/simulacion')),
  misRecuperaciones: () => D<ListaDeRecuperaciones>(api.get('/alm/uso/recuperaciones/mias')),
  conservar: (id: string, motivo: string) => D<Recuperacion>(api.post(`/alm/uso/recuperaciones/${id}/conservar`, { motivo })),
  decidir: (id: string, aprobar: boolean, nota?: string) =>
    D<Recuperacion>(api.post(`/alm/uso/recuperaciones/${id}/decidir`, { aprobar, nota })),
  liberar: (id: string, nota?: string) => D<Recuperacion>(api.post(`/alm/uso/recuperaciones/${id}/liberar`, { nota })),
  cancelar: (id: string, motivo?: string) => D<Recuperacion>(api.post(`/alm/uso/recuperaciones/${id}/cancelar`, { motivo })),

  propuestas: () => D<{ items: PropuestaDeAjuste[]; ahorro_anual_total: number; ventana_dias: number }>(
    api.get('/alm/uso/ajuste/propuestas')),
  decidirAjuste: (datos: { nivel_id: string; assignment_id: string; aceptar: boolean; motivo?: string }) =>
    D<{ decision: string; ahorro_anual: number | null }>(api.post('/alm/uso/ajuste/decidir', datos)),
  reglas: () => D<{ reglas: ReglaDeNivel[]; sugerencias: SugerenciaDeNivel[] }>(api.get('/alm/uso/ajuste/reglas')),
  guardarRegla: (datos: Partial<ReglaDeNivel>, id?: string) =>
    D<ReglaDeNivel>(id ? api.put(`/alm/uso/ajuste/reglas/${id}`, datos) : api.post('/alm/uso/ajuste/reglas', datos)),
  borrarRegla: (id: string) => D<{ ok: boolean }>(api.delete(`/alm/uso/ajuste/reglas/${id}`)),

  cumplimiento: () => D<Cumplimiento>(api.get('/alm/uso/cumplimiento')),
  exportarCumplimiento: (formato: 'csv' | 'xlsx', producto?: string) =>
    api.get('/alm/uso/cumplimiento/exportar', { params: { formato, producto }, responseType: 'blob' }),

  noControlado: (estado = 'nuevo') =>
    D<{ minimo: number; items: CandidatoNoControlado[]; importe_total: number; moneda: string }>(
      api.get('/alm/uso/no-controlado', { params: { estado } })),
  detectar: () => D<{ candidatos: number }>(api.post('/alm/uso/no-controlado/detectar')),
  alta: (id: string, datos: Record<string, unknown>) => D<CandidatoNoControlado>(api.post(`/alm/uso/no-controlado/${id}/alta`, datos)),
  descartar: (id: string, motivo?: string) =>
    D<CandidatoNoControlado>(api.post(`/alm/uso/no-controlado/${id}/descartar`, { motivo })),
  reabrir: (id: string) => D<CandidatoNoControlado>(api.post(`/alm/uso/no-controlado/${id}/reabrir`)),
}

/** El código de un error del backend de este módulo (`detail.code`), para traducirlo en la pantalla. */
export function codigoDeError(e: unknown): { codigo: string | null; mensaje: string | null } {
  const d = (e as { response?: { data?: { detail?: unknown } } } | null | undefined)?.response?.data?.detail
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const o = d as { code?: string; message?: string }
    return { codigo: o.code ?? null, mensaje: o.message ?? null }
  }
  return { codigo: null, mensaje: typeof d === 'string' ? d : null }
}
