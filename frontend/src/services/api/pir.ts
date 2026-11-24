/**
 * services/api/pir.ts — Revisión posterior a la implantación (PIR) de cambios y proyectos
 * (migración 206, docs/PIR.md). API: `/pir` (app/api/v1/endpoints/pir.py).
 *
 * Capacidades: `pir.ver` (leer y rellenar las propias), `pir.gestionar` (programar,
 * descartar, informes), `pir.aprobar` (aprobar, devolver, cerrar, reabrir) y
 * `pir.administrar` (configuración, plantillas, borrar). El interceptor de `_core`
 * desenvuelve `{ data, meta }`.
 */
import api from './_core'

export type OrigenPir = 'change' | 'project'
export type EstadoPir = 'programado' | 'en_curso' | 'enviado' | 'aprobado' | 'cerrado' | 'descartado'
export type ResultadoPir = 'exito' | 'exito_parcial' | 'fallo'
export type CumplimientoPir = 'si' | 'no' | 'parcial'
export type MotivoPir = 'implantacion' | 'cierre' | 'go_live' | 'manual' | 'migrada'

export interface CriterioPir { clave: string; texto: string; resultado: CumplimientoPir | null; comentario: string }
export interface PreguntaPir { clave: string; texto: string; respuesta: string }
export interface KpiPir { nombre: string; unidad: string; antes: number | null; despues: number | null; objetivo: number | null }
export interface BeneficioPir {
  benefit_id: string | null; nombre: string; unidad?: string | null; linea_base?: number | null
  previsto: number | null; conseguido: number | null; comentario: string; actualizar?: boolean
}
export interface SatisfaccionPir { interesado: string; rol: string; puntuacion: number | null; comentario: string }
export interface AccionPir {
  id: string; descripcion: string; responsable_id: string | null; responsable: string | null
  fecha_limite: string | null; estado: 'abierta' | 'hecha' | 'descartada'; project_id: string | null
  task_id: string | null; task_code: string | null; task_status: string | null; vencida: boolean
}
export interface LeccionDePir { id: string; codigo: string; titulo: string; estado: string; tipo: string }

/** `servicio.serializar` (lista). */
export interface Pir {
  id: string; codigo: string; titulo: string; origen_tipo: OrigenPir
  change_id: string | null; project_id: string | null; milestone_id: string | null
  origen_ref: string | null; origen_nombre: string | null; motivo: MotivoPir; tipo: string | null
  estado: EstadoPir; vencida: boolean; obligatorio: boolean
  fecha_prevista: string | null; fecha_real: string | null; dias_restantes: number | null
  responsable_id: string | null; responsable: string | null
  resultado: ResultadoPir | null; objetivos_cumplidos: CumplimientoPir | null; hubo_marcha_atras: boolean | null
  created_at: string | null
}

export interface PermisosPir {
  editar: boolean; enviar: boolean; aprobar: boolean; devolver: boolean; cerrar: boolean; reabrir: boolean
  descartar: boolean; borrar: boolean; acciones: boolean; segregacion: boolean
}

/** `servicio.serializar(detalle=True)`. */
export interface PirDetalle extends Pir {
  participantes: string[]; resumen: string | null
  criterios: CriterioPir[]; preguntas: PreguntaPir[]; kpis: KpiPir[]
  incidencias: { id: string; number: string | null; title: string | null; status: string | null }[]
  marcha_atras_detalle: string | null; beneficios: BeneficioPir[]; satisfaccion: SatisfaccionPir[]
  satisfaccion_media: number | null
  enviado_por: string | null; enviado_en: string | null; aprobado_por: string | null; aprobado_en: string | null
  comentario_aprobacion: string | null; cerrado_por: string | null; cerrado_en: string | null
  reaperturas: number; cuenta_en_modelo: boolean
  acciones: AccionPir[]; lecciones: LeccionDePir[]
  permisos?: PermisosPir
}

export type CambiosPir = Partial<Pick<PirDetalle, 'titulo' | 'fecha_prevista' | 'responsable_id' | 'participantes'
  | 'objetivos_cumplidos' | 'resultado' | 'resumen' | 'criterios' | 'preguntas' | 'kpis' | 'hubo_marcha_atras'
  | 'marcha_atras_detalle' | 'satisfaccion'>> & { incidencias?: string[]; beneficios?: BeneficioPir[] }

export interface ListaPir { items: Pir[]; total: number; page: number; page_size: number }
export interface FiltrosPir {
  origen_tipo?: OrigenPir; origen_id?: string; estado?: string; resultado?: string; solo_mias?: boolean
  solo_obligatorias?: boolean; q?: string; page?: number; page_size?: number
}

export interface VistaCabPir {
  desde: string; hasta: string; cambios_cerrados: number; cerrados_del_todo: number
  cerrados_con_pir_pendiente: number; pir_pendientes: number; pir_vencidas: number; pir_por_aprobar: number
  pendientes: Pir[]
}
export interface GrupoExito {
  ambito: OrigenPir; tipo: string | null; revisadas: number; exito: number; exito_parcial: number; fallo: number
  marcha_atras: number; tasa_exito: number | null; tasa_fallo: number | null
}
export interface InformeExito { desde: string; hasta: string; grupos: GrupoExito[] }
export interface InformeCumplimiento {
  desde: string; hasta: string; obligatorias: number; a_tiempo: number; tarde: number; en_plazo: number
  vencidas: number; tasa_cumplimiento: number | null; lista_vencidas: Pir[]
}

export interface ConfigPir {
  dias_cambio: number; dias_proyecto: number; aviso_dias_antes: number; segregacion: boolean
  momento_cambio: 'implantacion' | 'cierre'; momento_proyecto: 'go_live' | 'cierre' | 'ambos'
  obligatorio_normal: boolean; obligatorio_emergencia: boolean; obligatorio_estandar: boolean
  obligatorio_proyecto: boolean; proyecto_acciones_id: string | null
}
export interface ItemDePlantilla { clave: string; texto: string }
export interface PlantillaPir {
  id: string; nombre: string; ambito: OrigenPir; tipo: string | null; obligatorio: boolean | null
  dias: number | null; criterios: ItemDePlantilla[]; preguntas: ItemDePlantilla[]; activo: boolean
  updated_at: string | null
}
export type PlantillaPirIn = Partial<Omit<PlantillaPir, 'id' | 'updated_at'>>

export interface LeccionDePirIn {
  titulo: string; categoria: string; que_paso: string; recomendacion: string
  tipo?: 'evitar' | 'repetir'; severidad?: 'baja' | 'media' | 'alta'; causa?: string; impacto?: string
  etiquetas?: string; enviar_a_revision?: boolean
}

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const B = '/pir'

export const CLAVES_PIR = {
  todo: ['pir'] as const,
  lista: (f: FiltrosPir) => ['pir', 'lista', f] as const,
  mias: ['pir', 'mias'] as const,
  detalle: (id: string) => ['pir', 'detalle', id] as const,
  cab: ['pir', 'cab'] as const,
  config: ['pir', 'config'] as const,
  plantillas: ['pir', 'plantillas'] as const,
  informes: (tipo: string, desde?: string, hasta?: string) => ['pir', 'informe', tipo, desde, hasta] as const,
}

export const pirApi = {
  listar: (f: FiltrosPir = {}) => D<ListaPir>(api.get(B, { params: f })),
  mias: () => D<Pir[]>(api.get(`${B}/mias`)),
  cab: () => D<VistaCabPir>(api.get(`${B}/cab`)),
  exito: (desde?: string, hasta?: string) => D<InformeExito>(api.get(`${B}/informes/exito`, { params: { desde, hasta } })),
  cumplimiento: (desde?: string, hasta?: string) =>
    D<InformeCumplimiento>(api.get(`${B}/informes/cumplimiento`, { params: { desde, hasta } })),
  detalle: (id: string) => D<PirDetalle>(api.get(`${B}/${id}`)),
  programar: (datos: { origen_tipo: OrigenPir; origen_id: string; milestone_id?: string | null; fecha_prevista?: string | null; responsable_id?: string | null }) =>
    D<PirDetalle>(api.post(B, datos)),
  guardar: (id: string, datos: CambiosPir) => D<PirDetalle>(api.patch(`${B}/${id}`, datos)),
  enviar: (id: string) => D<PirDetalle>(api.post(`${B}/${id}/enviar`)),
  aprobar: (id: string, comentario?: string) => D<PirDetalle>(api.post(`${B}/${id}/aprobar`, { comentario })),
  devolver: (id: string, comentario: string) => D<PirDetalle>(api.post(`${B}/${id}/devolver`, { comentario })),
  cerrar: (id: string) => D<PirDetalle>(api.post(`${B}/${id}/cerrar`)),
  reabrir: (id: string, motivo: string) => D<PirDetalle>(api.post(`${B}/${id}/reabrir`, { motivo })),
  descartar: (id: string, motivo: string) => D<PirDetalle>(api.post(`${B}/${id}/descartar`, { motivo })),
  borrar: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/${id}`)),
  crearAccion: (id: string, datos: { descripcion: string; responsable_id?: string | null; fecha_limite?: string | null; project_id?: string | null }) =>
    D<{ accion: AccionPir; sin_tarea: boolean }>(api.post(`${B}/${id}/acciones`, datos)),
  editarAccion: (id: string, accionId: string, datos: { estado?: AccionPir['estado']; responsable_id?: string | null; fecha_limite?: string | null }) =>
    D<AccionPir>(api.patch(`${B}/${id}/acciones/${accionId}`, datos)),
  crearLeccion: (id: string, datos: LeccionDePirIn) => D<{ id: string; codigo: string }>(api.post(`${B}/${id}/lecciones`, datos)),
  config: () => D<ConfigPir>(api.get(`${B}/config`)),
  guardarConfig: (datos: Partial<ConfigPir>) => D<ConfigPir>(api.put(`${B}/config`, datos)),
  plantillas: () => D<PlantillaPir[]>(api.get(`${B}/plantillas`)),
  deFabrica: (ambito: OrigenPir, idioma: string) =>
    D<{ criterios: ItemDePlantilla[]; preguntas: ItemDePlantilla[] }>(api.get(`${B}/plantillas/fabrica`, { params: { ambito, idioma } })),
  crearPlantilla: (datos: PlantillaPirIn) => D<PlantillaPir>(api.post(`${B}/plantillas`, datos)),
  editarPlantilla: (id: string, datos: PlantillaPirIn) => D<PlantillaPir>(api.put(`${B}/plantillas/${id}`, datos)),
  borrarPlantilla: (id: string) => D<{ ok: boolean }>(api.delete(`${B}/plantillas/${id}`)),
}
