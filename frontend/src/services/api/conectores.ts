/**
 * services/api/conectores.ts — contecmind (documentos) y contecintelligence (analítica) (revisión 2026-11).
 *
 * Todo pasa por contecflow: el navegador nunca ve la credencial de la
 * aplicación. Un fallo del conector llega con su código en la cabecera
 * `X-Conector-Codigo` y un mensaje que se puede enseñar tal cual.
 */
import api from './_core'

export type Ficha = 'ticket' | 'contract' | 'project' | 'kb_article' | 'lesson' | 'expense' | 'budget'

export interface DocHit { document_id: string; title: string; snippet: string; score?: number; media_kind?: string }
export interface Enlace {
  id: string; document_id: string; title: string; mime_type?: string; size_bytes?: number
  origen: 'subido' | 'enlazado' | 'sugerido'; nota?: string; created_at?: string
}
export interface DocDetalle {
  id: string; title: string; mime_type?: string; size_bytes?: number; status?: string; media_kind?: string
  created_at?: string; updated_at?: string; review_deadline?: string | null; locked_by?: string | null
  lock_note?: string | null; chunk_count?: number; metadata?: Record<string, unknown>; error?: string | null
  extracto?: string; extracto_recortado?: boolean
}
export interface Aprobacion {
  document_id: string; title: string; control_state?: string; current_version_no?: number; requires_approval?: boolean
  versions?: { version_no: number; state: string; filename: string; change_note?: string | null; created_at: string; published_at?: string | null }[]
  solicitud?: { id: string; status: string; current_step?: number; final_decision?: string | null } | null
  puedo_pedir?: boolean
}
export interface RespuestaCarpeta { answer: string; citations: { document_id: string; title?: string; text: string; page?: number | null }[] }
export interface EstadoProducto {
  producto: 'contecmind' | 'contecintelligence'; configurado: boolean; llamadas: number; fallos: number
  p50_ms: number | null; p95_ms: number | null; ultima_llamada: string | null
  ultimo_error: { cuando: string; operacion: string; estado_http: number | null; error: string } | null
  operaciones: { operacion: string; llamadas: number; fallos: number; p50_ms: number | null; p95_ms: number | null }[]
}
export interface Prueba { ok: boolean; codigo: string; detail: string; ms?: number }
export interface Fuente { id: string; name: string; source_type?: string; status?: string; puedes_preguntar?: boolean }
export interface Metrica { id: string; name: string; label: string; description: string; source_id: string; dimensions: string[]; grain?: string }
export interface RespuestaCI {
  text: string; payload?: unknown; receipt_id?: string | null; receipt_signed?: boolean
  conversation_id?: string | null; source_id: string
}

// El interceptor de `_core` ya desenvuelve el sobre `{ data, meta }`: `r.data` es el contenido.
const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export const conectoresApi = {
  estado: () => D<{ ventana_horas: number; productos: EstadoProducto[] }>(api.get('/conectores/estado')),
  probar: (producto: 'contecmind' | 'contecintelligence') =>
    D<{ ok: boolean; aplicacion: Prueba; empresa: Prueba | null }>(api.post(`/conectores/${producto}/probar`)),

  // contecmind
  cmDisponible: () => D<{ configurado: boolean; puede_escribir: boolean }>(api.get('/conectores/contecmind/disponible')),
  buscar: (q: string, limit?: number) => D<{ items: DocHit[] }>(api.get('/conectores/contecmind/buscar', { params: { q, limit } })),
  documento: (id: string) => D<DocDetalle>(api.get(`/conectores/contecmind/documentos/${id}`)),
  original: (id: string) => api.get(`/conectores/contecmind/documentos/${id}/original`, { responseType: 'blob' }),
  aprobacion: (id: string) => D<Aprobacion>(api.get(`/conectores/contecmind/documentos/${id}/aprobacion`)),
  pedirAprobacion: (id: string, version_no?: number) =>
    D<unknown>(api.post(`/conectores/contecmind/documentos/${id}/aprobacion`, null, { params: { version_no } })),
  enlaces: (f: Ficha, id: string) => D<{ items: Enlace[] }>(api.get(`/conectores/contecmind/fichas/${f}/${id}/documentos`)),
  sugerencias: (f: Ficha, id: string) => D<{ items: DocHit[] }>(api.get(`/conectores/contecmind/fichas/${f}/${id}/sugerencias`)),
  enlazar: (f: Ficha, id: string, document_id: string, nota?: string) =>
    D<Enlace>(api.post(`/conectores/contecmind/fichas/${f}/${id}/documentos`, { document_id, nota })),
  subir: (f: Ficha, id: string, file: File, titulo?: string, nota?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (titulo) fd.append('titulo', titulo)
    if (nota) fd.append('nota', nota)
    return D<Enlace>(api.post(`/conectores/contecmind/fichas/${f}/${id}/subir`, fd))
  },
  desenlazar: (f: Ficha, id: string, enlaceId: string) => api.delete(`/conectores/contecmind/fichas/${f}/${id}/documentos/${enlaceId}`),
  preguntarCarpeta: (f: Ficha, id: string, pregunta: string) =>
    D<RespuestaCarpeta>(api.post(`/conectores/contecmind/fichas/${f}/${id}/preguntar`, { pregunta })),

  // contecintelligence
  ciDisponible: () => D<{ configurado: boolean; analista: boolean; fuente_por_defecto: string | null; pasar_preguntas: boolean }>(
    api.get('/conectores/contecintelligence/disponible')),
  fuentes: () => D<{ items: Fuente[] }>(api.get('/conectores/contecintelligence/fuentes')),
  metricas: (source_id?: string) => D<{ items: Metrica[] }>(api.get('/conectores/contecintelligence/metricas', { params: { source_id } })),
  consultar: (source_id: string, query: Record<string, unknown>) =>
    D<{ metric: string; label: string; columns: string[]; rows: unknown[][]; row_count: number; executed_sql?: string; governed?: boolean }>(
      api.post('/conectores/contecintelligence/metricas/consultar', { source_id, query })),
  explicar: (body: { source_id: string; metric: string; actual: { column: string; start: string; end: string }; anterior: { column: string; start: string; end: string }; dimensions?: string[] }) =>
    D<Record<string, unknown>>(api.post('/conectores/contecintelligence/metricas/explicar', body)),
  verificarRecibo: (id: string) => D<{ valid: boolean; reason?: string }>(api.get(`/conectores/contecintelligence/recibos/${id}/verificar`)),
}

/** Mensaje de un fallo del conector, tal y como lo manda el servidor. */
export function mensajeDeConector(e: unknown, porDefecto: string): string {
  const r = (e as { response?: { data?: { detail?: unknown } } })?.response
  const d = r?.data?.detail
  return typeof d === 'string' && d ? d : porDefecto
}
