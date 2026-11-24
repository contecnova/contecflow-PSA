/**
 * services/api/cuaderno.ts — «Mi cuaderno» (migración 202, docs/CUADERNO.md).
 *
 * Base `/notebook`. El interceptor de `_core` ya desenvuelve `{ data }`.
 * El guardado automático (`PUT /pages/{id}/content`) y la resolución de chips
 * no refrescan el resto de pantallas (`refrescoTrasEscritura.SIN_REFRESCO`).
 */
import api from './_core'

export type Permiso = 'owner' | 'edit' | 'read'
export type TipoDeObjeto = 'task' | 'ticket' | 'project' | 'client' | 'demand' | 'proposal' | 'event' | 'user'
export type TipoDeAccion = 'task' | 'ticket' | 'demand' | 'proposal' | 'event'
export type Formato = 'md' | 'pdf'
export type TipoExportable = 'page' | 'section' | 'notebook'
export type DocJSON = { type: string; content?: DocJSON[]; attrs?: Record<string, unknown>; text?: string; marks?: { type: string; attrs?: Record<string, unknown> }[] }

export interface PaginaCorta { id: string; title: string; parent_id: string | null; sort_order: number; updated_at: string | null; created_at: string | null }
export interface Seccion { id: string; notebook_id: string; title: string; color: string | null; sort_order: number; permission: Permiso; pages: PaginaCorta[] }
export interface Cuaderno {
  id: string; title: string; color: string | null; sort_order: number; is_quick: boolean; permission: Permiso
  owner_id: string; owner_name: string | null; shared: boolean; transferred_from: string | null; sections: Seccion[]
}
export interface Etiqueta { key: string; label: string; color: string | null; icon: string | null; scope: 'org' | 'mine'; id?: string }
export interface Arbol {
  notebooks: Cuaderno[]; trash_count: number; tags: Etiqueta[]
  features: { ai: boolean; voice: boolean; sharing: { users: boolean; teams: boolean; departments: boolean } }
}
export interface Adjunto { id: string; kind: 'file' | 'image' | 'drawing' | 'audio'; file_name: string; mime_type: string | null; size_bytes: number; url: string; created_at: string | null }
export interface Pagina {
  id: string; title: string; section_id: string; notebook_id: string; parent_id: string | null
  section_title: string | null; notebook_title: string | null; section_color: string | null
  content: DocJSON; version: number; permission: Permiso; shared: boolean; owner_id: string
  created_at: string | null; updated_at: string | null; updated_by_name: string | null; deleted_at: string | null
  attachments: Adjunto[]
}
export interface Guardado { id: string; version: number; updated_at: string | null }
// `agents` (23-11-2026): los agentes de código del propio dueño por MCP (solo lectura).
export interface Comparticion { id: string; notebook_id: string; section_id: string | null; target_type: 'user' | 'team' | 'department' | 'agents'; target_id: string; target_name: string; permission: 'read' | 'edit'; created_at: string | null }
export interface ElementoDeCuaderno {
  id: string; kind: 'todo' | 'tag'; tag_key: string | null; text: string; checked: boolean; due_date: string | null
  remind_at: string | null; block_id: string | null; page_id: string; page_title: string | null
  section_title: string | null; notebook_title: string | null
}
export interface ResultadoDeBusqueda { id: string; title: string; section_id: string; notebook_id: string; section_title: string | null; notebook_title: string | null; snippet: string; updated_at: string | null }
export interface Candidato { type: TipoDeObjeto; id: string; label: string; status: string | null; subtitle: string | null }
export interface Chip { type: TipoDeObjeto; id: string; hidden: boolean; label?: string; status?: string | null; url?: string | null; due_date?: string | null }
export interface EnPapelera { kind: 'notebook' | 'section' | 'page'; id: string; title: string; deleted_at: string | null }
export interface Plantilla { id: string | null; key: string; name: string; description: string | null; is_active: boolean; sort_order: number; builtin: boolean; custom: boolean; content?: DocJSON }
export interface Rapidas { notebook_id: string; section_id: string; quick: RapidaCorta[]; recent: RapidaCorta[] }
export interface RapidaCorta { id: string; title: string; snippet: string; updated_at: string | null }
export interface Trazo { color: string; width: number; points: [number, number][]; erase?: boolean }
export interface Dibujo { width: number; height: number; strokes: Trazo[] }
export interface ConfigCuaderno {
  tags: { key: string; label: string; color: string; icon: string }[]
  offboarding: 'transfer' | 'trash' | 'keep'; trash_days: number; ai_enabled: boolean; voice_enabled: boolean
  sharing: { users: boolean; teams: boolean; departments: boolean }
}
export interface AccionIn {
  kind: TipoDeAccion; text?: string; title?: string; project_id?: string; due_date?: string; start?: string
  end?: string; duration_min?: number; type_key?: string; block_id?: string
}
export interface ContenidoIn { content?: DocJSON; title?: string; base_version?: number; collab?: boolean; yjs_state?: string }

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const B = '/notebook'

export const cuadernoApi = {
  arbol: () => D<Arbol>(api.get(`${B}/tree`)),
  crearCuaderno: (c: { title: string; color?: string; section_title?: string }) => D<{ id: string; title: string }>(api.post(`${B}/notebooks`, c)),
  editarCuaderno: (id: string, c: { title?: string; color?: string }) => D<unknown>(api.patch(`${B}/notebooks/${id}`, c)),
  borrarCuaderno: (id: string) => D<unknown>(api.delete(`${B}/notebooks/${id}`)),
  crearSeccion: (nb: string, c: { title: string; color?: string }) => D<{ id: string }>(api.post(`${B}/notebooks/${nb}/sections`, c)),
  editarSeccion: (id: string, c: { title?: string; color?: string; notebook_id?: string }) => D<unknown>(api.patch(`${B}/sections/${id}`, c)),
  borrarSeccion: (id: string) => D<unknown>(api.delete(`${B}/sections/${id}`)),
  reordenar: (kind: 'notebook' | 'section' | 'page', ids: string[]) => D<unknown>(api.post(`${B}/reorder`, { kind, ids })),

  crearPagina: (sec: string, c: { title?: string; parent_id?: string; template_key?: string; content?: DocJSON }) =>
    D<Pagina>(api.post(`${B}/sections/${sec}/pages`, c)),
  pagina: (id: string) => D<Pagina>(api.get(`${B}/pages/${id}`)),
  guardar: (id: string, c: ContenidoIn) => D<Guardado>(api.put(`${B}/pages/${id}/content`, c)),
  estadoColaborativo: (id: string) => D<{ state: string | null }>(api.get(`${B}/pages/${id}/collab`)),
  moverPagina: (id: string, c: { title?: string; section_id?: string; parent_id?: string | null; sort_order?: number; detach?: boolean }) =>
    D<unknown>(api.patch(`${B}/pages/${id}`, c)),
  borrarPagina: (id: string) => D<unknown>(api.delete(`${B}/pages/${id}`)),

  rapidas: () => D<Rapidas>(api.get(`${B}/quick`)),
  nuevaRapida: (c: { title?: string; text?: string } = {}) => D<Pagina>(api.post(`${B}/quick`, c)),

  papelera: () => D<EnPapelera[]>(api.get(`${B}/trash`)),
  restaurar: (kind: string, id: string) => D<unknown>(api.post(`${B}/trash/${kind}/${id}/restore`)),
  purgar: (kind: string, id: string) => D<unknown>(api.delete(`${B}/trash/${kind}/${id}`)),
  vaciarPapelera: () => D<{ deleted: number }>(api.delete(`${B}/trash`)),

  buscar: (q: string, notebook_id?: string) => D<ResultadoDeBusqueda[]>(api.get(`${B}/search`, { params: { q, ...(notebook_id ? { notebook_id } : {}) } })),
  elementos: (f: { kind?: 'todo' | 'tag'; status?: 'open' | 'done' | 'all'; tag?: string } = {}) =>
    D<ElementoDeCuaderno[]>(api.get(`${B}/items`, { params: f })),
  marcar: (id: string, checked: boolean) => D<{ id: string; checked: boolean; page_id: string; version: number }>(api.patch(`${B}/items/${id}`, { checked })),
  etiquetas: () => D<Etiqueta[]>(api.get(`${B}/tags`)),
  crearEtiqueta: (c: { label: string; color?: string; icon?: string }) => D<Etiqueta>(api.post(`${B}/tags`, c)),
  borrarEtiqueta: (id: string) => D<unknown>(api.delete(`${B}/tags/${id}`)),
  plantillas: () => D<Plantilla[]>(api.get(`${B}/templates`)),

  comparticiones: (nb: string) => D<Comparticion[]>(api.get(`${B}/notebooks/${nb}/shares`)),
  compartir: (nb: string, c: { target_type: string; target_id: string; permission: string; section_id?: string | null }) =>
    D<Comparticion>(api.post(`${B}/notebooks/${nb}/shares`, c)),
  cambiarPermiso: (id: string, permission: 'read' | 'edit') => D<Comparticion>(api.patch(`${B}/shares/${id}`, { permission })),
  dejarDeCompartir: (id: string) => D<unknown>(api.delete(`${B}/shares/${id}`)),
  destinos: (q = '') => D<{ teams: string[]; departments: string[] }>(api.get(`${B}/share-targets`, { params: { q } })),

  referencias: (q: string, types: string) => D<Candidato[]>(api.get(`${B}/refs`, { params: { q, types } })),
  resolverChips: (refs: { type: string; id: string }[]) => D<Chip[]>(api.post(`${B}/chips/resolve`, { refs })),
  convertir: (page: string, c: AccionIn) => D<Chip & { label: string }>(api.post(`${B}/pages/${page}/actions`, c)),
  vinculos: (type: string, id: string) => D<{ page_id: string; page_title: string; relation: string; url: string }[]>(api.get(`${B}/backlinks`, { params: { type, id } })),

  subir: (page: string, fichero: File | Blob, nombre?: string) => {
    const fd = new FormData()
    fd.append('file', fichero, nombre || (fichero as File).name || 'adjunto')
    return D<Adjunto>(api.post(`${B}/pages/${page}/attachments`, fd))
  },
  borrarAdjunto: (id: string) => D<unknown>(api.delete(`${B}/attachments/${id}`)),
  nuevoDibujo: (page: string, d: Dibujo) => D<Adjunto & { drawing: Dibujo }>(api.post(`${B}/pages/${page}/drawings`, d)),
  dibujo: (id: string) => D<Adjunto & { drawing: Dibujo }>(api.get(`${B}/drawings/${id}`)),
  cambiarDibujo: (id: string, d: Dibujo) => D<Adjunto & { drawing: Dibujo }>(api.put(`${B}/drawings/${id}`, d)),
  transcribir: (page: string, audio: Blob, guardarAudio = false, idioma?: string) => {
    const fd = new FormData()
    fd.append('file', audio, 'nota.webm')
    fd.append('keep_audio', guardarAudio ? 'true' : 'false')
    if (idioma) fd.append('language', idioma)
    return D<{ text: string; provider: string | null; attachment: Adjunto | null }>(api.post(`${B}/pages/${page}/transcribe`, fd))
  },
  ia: (page: string, action: 'summarize' | 'extract_tasks' | 'organize') =>
    D<{ action: string; text: string | null; tasks: { text: string; due_date: string | null }[] }>(api.post(`${B}/pages/${page}/ai`, { action })),

  exportar: (kind: TipoExportable, id: string, format: Formato) =>
    D<Blob>(api.get(`${B}/export/${kind}/${id}`, { params: { format }, responseType: 'blob' })),
  desdeReunion: (meetingId: string, section_id?: string) =>
    D<{ page_id: string; section_id: string; notebook_id: string; title: string }>(api.post(`${B}/from-meeting/${meetingId}`, section_id ? { section_id } : {})),

  config: () => D<ConfigCuaderno>(api.get(`${B}/config`)),
  guardarConfig: (c: Partial<ConfigCuaderno>) => D<ConfigCuaderno>(api.put(`${B}/config`, c)),
  todasLasPlantillas: () => D<Plantilla[]>(api.get(`${B}/config/templates`)),
  guardarPlantilla: (p: { key: string; name: string; description?: string | null; content?: DocJSON; is_active: boolean; sort_order: number }) =>
    D<Plantilla>(api.put(`${B}/config/templates`, p)),
  borrarPlantilla: (key: string) => D<unknown>(api.delete(`${B}/config/templates/${key}`)),
  accesoExcepcional: (userId: string, c: { legal_hold_id?: string; gdpr_request_id?: string; justification: string; format: Formato }) =>
    D<Blob>(api.post(`${B}/admin/exceptional-access/${userId}`, c, { responseType: 'blob' })),
}

/** Claves de react-query del cuaderno. */
export const CLAVES_CUADERNO = {
  arbol: ['cuaderno', 'arbol'] as const,
  pagina: (id: string) => ['cuaderno', 'pagina', id] as const,
  rapidas: ['cuaderno', 'rapidas'] as const,
  elementos: (f: object) => ['cuaderno', 'elementos', f] as const,
  papelera: ['cuaderno', 'papelera'] as const,
  config: ['cuaderno', 'config'] as const,
  plantillas: ['cuaderno', 'plantillas'] as const,
}
