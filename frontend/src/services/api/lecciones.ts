/**
 * services/api/lecciones.ts — lecciones aprendidas (revisión 2026-11).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 */
import api from './_core'

export type OrigenLeccion = 'project' | 'ticket' | 'problem' | 'major_incident' | 'sprint' | 'security_incident' | 'manual'
export interface Hecho { etiqueta: string; valor: string | number | boolean | string[] }
export interface Leccion {
  id: string; codigo: string; titulo: string; tipo: 'evitar' | 'repetir'; categoria: string; severidad: 'baja' | 'media' | 'alta'
  que_paso: string; causa?: string | null; impacto?: string | null; recomendacion: string
  estado: 'borrador' | 'en_revision' | 'validada' | 'archivada'
  origen_tipo: OrigenLeccion; origen_id?: string | null; origen_ref?: string | null
  proyecto_id?: string | null; cliente_id?: string | null; tipo_proyecto?: string | null; etiquetas?: string | null
  autor_id?: string | null; validada_por?: string | null; validada_en?: string | null; created_at?: string | null
  usos: { util: number; aplicada: number; no_aplica: number }
  hechos?: Hecho[]; acciones?: Accion[]
  historial_usos?: { valor: string; contexto_tipo: string; contexto_id?: string | null; nota?: string | null; created_at?: string | null }[]
  puedo_editar?: boolean; puedo_validar?: boolean
}
export interface Accion {
  id: string; leccion_id: string; descripcion: string; responsable_id?: string | null; fecha_limite?: string | null
  estado: 'abierta' | 'en_curso' | 'hecha' | 'descartada'; resultado?: string | null; cerrada_en?: string | null; vencida: boolean
  leccion_codigo?: string; leccion_titulo?: string
}
export interface Borrador {
  origen_tipo: OrigenLeccion; origen_id: string; origen_ref: string; hechos: Hecho[]
  propuesta: Partial<Leccion> & { etiquetas?: string }; ia: boolean; aviso: string | null
}
export interface Recomendacion extends Leccion {
  puntuacion: number; frase: string; mi_valoracion?: string | null
  motivos: { clave: string; peso: number; detalle?: string[] }[]
}
export interface Pendiente { origen_tipo: OrigenLeccion; origen_id: string; ref: string; titulo: string; cerrado: string | null }

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export const leccionesApi = {
  config: () => D<{ categorias: string[]; puedo_validar: boolean }>(api.get('/lessons/config')),
  listar: (params: Record<string, unknown>) => D<{ items: Leccion[]; total: number }>(api.get('/lessons', { params })),
  detalle: (id: string) => D<Leccion>(api.get(`/lessons/${id}`)),
  borrador: (tipo: string, id: string) => D<Borrador>(api.get(`/lessons/borrador/${tipo}/${id}`)),
  crear: (body: Record<string, unknown>) => D<Leccion>(api.post('/lessons', body)),
  editar: (id: string, body: Record<string, unknown>) => D<Leccion>(api.patch(`/lessons/${id}`, body)),
  estado: (id: string, estado: string) => D<Leccion>(api.post(`/lessons/${id}/estado`, { estado })),
  borrar: (id: string) => api.delete(`/lessons/${id}`),
  pendientes: () => D<{ items: Pendiente[] }>(api.get('/lessons/pendientes')),
  indicadores: () => D<{
    por_estado: Record<string, number>; por_categoria: Record<string, number>; por_tipo: Record<string, number>
    valoraciones: Record<string, number>; valoraciones_total: number; efectividad_pct: number | null
    mas_utiles: { id: string; codigo: string; titulo: string; valoraciones_utiles: number }[]
    acciones_abiertas: number; acciones_vencidas: number; pendientes_de_capturar: number
  }>(api.get('/lessons/indicadores')),
  deOrigen: (tipo: string, id: string) => D<{ items: Leccion[] }>(api.get(`/lessons/de/${tipo}/${id}`)),
  recomendaciones: (tipo: 'project' | 'ticket', id: string) =>
    D<{ items: Recomendacion[]; evaluadas: number }>(api.get(`/lessons/recomendaciones/${tipo}/${id}`)),
  recomendacionesNuevo: (campos: Record<string, unknown>) =>
    D<{ items: Recomendacion[]; evaluadas: number }>(api.post('/lessons/recomendaciones/nuevo-proyecto', campos)),
  valorar: (id: string, body: { contexto_tipo: string; contexto_id?: string | null; valor: string }) =>
    D<Leccion>(api.post(`/lessons/${id}/valoracion`, body)),
  acciones: (params: { solo_mias?: boolean; solo_abiertas?: boolean }) => D<{ items: Accion[] }>(api.get('/lessons/acciones', { params })),
  crearAccion: (id: string, body: { descripcion: string; responsable_id?: string | null; fecha_limite?: string | null }) =>
    D<Accion>(api.post(`/lessons/${id}/acciones`, body)),
  editarAccion: (id: string, body: Record<string, unknown>) => D<Accion>(api.patch(`/lessons/acciones/${id}`, body)),
}
