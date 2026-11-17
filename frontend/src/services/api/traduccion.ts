/**
 * services/api/traduccion.ts — traducción en tiempo real operador ↔ cliente (16-11-2026).
 * Prefijo `/translation`. El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 *
 * Estados de una traducción (`status`): `translated`, `same_language` (nada que traducir),
 * `unavailable` (no se pudo: `reason` dice por qué; se muestra el original con aviso) y
 * `disabled` (la empresa o el canal no traducen). `origin`: `auto` (el servicio), `author`
 * (lo que escribió el operador cuando al cliente se le envió la traducción) o `system`
 * (texto del sistema pintado en el idioma de quien mira).
 */
import api from './_core'

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export type EstadoDeTraduccion = 'translated' | 'same_language' | 'unavailable' | 'disabled'
export type OrigenDeTraduccion = 'auto' | 'author' | 'system'
export type TipoDeMensaje = 'ticket_comment' | 'ticket' | 'channel_message' | 'chat_message'

export interface ConfigDeTraduccion {
  enabled: boolean
  provider: 'ai' | 'deepl' | 'azure'
  channels: string[]
  include_original: boolean
  outbound_auto: boolean
  /** Idioma de quien pregunta (sus preferencias o el de la empresa). */
  my_language: string
  /** Todos los idiomas a los que se puede traducir (códigos; el nombre lo pone `Intl.DisplayNames`). */
  languages: string[]
  operator_languages: string[]
  portal_languages: string[]
}

export interface MensajeTraducido {
  type: TipoDeMensaje
  id: string
  /** `body` (comentarios y mensajes) o `title` / `description` (ticket). */
  field: string
  status: EstadoDeTraduccion
  text: string | null
  source_language: string | null
  target_language: string
  origin?: OrigenDeTraduccion | null
  provider?: string | null
  reason?: string | null
}

export interface MensajesTraducidos { target_language: string; enabled: boolean; items: MensajeTraducido[] }

export interface TextoTraducido {
  status: EstadoDeTraduccion
  text: string | null
  source_language: string | null
  target_language: string
  provider: string | null
  reason: string | null
  cached: boolean
}

export interface VistaPrevia {
  status: EstadoDeTraduccion
  text: string | null
  source_language: string | null
  /** Idioma del cliente; null si no se sabe (`reason: unknown_client_language`). */
  target_language: string | null
  /** De dónde sale el idioma del cliente: contacto, portal, detectado o elegido a mano. */
  target_source: 'contact' | 'portal' | 'detected' | 'manual' | null
  enabled: boolean
  include_original: boolean
  provider?: string | null
  reason?: string | null
}

export interface TerminoDeGlosario {
  id: string
  term: string
  /** {idioma: texto}; vacío: el término no se traduce. */
  translations: Record<string, string>
  case_sensitive: boolean
  notes: string | null
  is_active: boolean
  updated_at: string | null
}

export interface UsoDeTraduccion {
  cache: { entries: number; characters: number; hits: number }
  messages_translated: number
  glossary_terms: number
  kb_versions_in_review: number
  today_cost_usd: number
  today_calls: number
  today_failures: number
  ai_spend_today_usd: number
  ai_daily_budget_usd: number
}

export interface PruebaDeTraduccion { ok: boolean; text?: string; source_language?: string | null; provider?: string; reason?: string }

export type EstadoDeVersionKb = 'draft' | 'in_review' | 'published' | 'rejected'

export interface VersionKb {
  id: string
  article_id: string
  language: string
  title: string
  summary: string | null
  body: string
  status: EstadoDeVersionKb
  provider: string | null
  /** El artículo original cambió después de generar esta versión. */
  outdated: boolean
  review_comment: string | null
  reviewed_at: string | null
  updated_at: string | null
}

export interface VersionesKb {
  article_id: string
  source_language: string | null
  languages: string[]
  enabled: boolean
  items: VersionKb[]
}

export interface GeneracionKb { generated: VersionKb[]; failed: { language: string; reason: string }[] }

/** Avisos y catálogo del portal con versiones revisables (17-11-2026). */
export type TipoDeContenidoDelPortal = 'announcement' | 'catalog_category' | 'catalog_service'

export interface VersionDeContenido {
  id: string
  content_type: TipoDeContenidoDelPortal
  content_id: string
  language: string
  fields: Record<string, string>
  status: EstadoDeVersionKb
  provider: string | null
  /** El original cambió después de generar o corregir esta versión. */
  outdated: boolean
  review_comment: string | null
  reviewed_at: string | null
  updated_at: string | null
}

export interface VersionesDeContenido {
  content_type: TipoDeContenidoDelPortal
  content_id: string
  label: string
  fields: string[]
  required_field: string
  original: Record<string, string>
  source_language: string | null
  languages: string[]
  enabled: boolean
  can_review: boolean
  items: VersionDeContenido[]
}

export interface FilaDeRevisionDeContenido {
  content_type: TipoDeContenidoDelPortal
  content_id: string
  label: string
  counts: Record<EstadoDeVersionKb, number>
  outdated: number
  languages: string[]
}

export interface ResumenDeContenidoDelPortal { can_review: boolean; enabled: boolean; items: FilaDeRevisionDeContenido[] }

export const traduccionApi = {
  config: () => D<ConfigDeTraduccion>(api.get('/translation/config')),
  mensajes: (items: { type: TipoDeMensaje; id: string }[], target_language?: string) =>
    D<MensajesTraducidos>(api.post('/translation/messages', { items, target_language })),
  texto: (d: { text: string; target_language: string; source_language?: string; channel?: 'editor' | 'internal_chat' | 'kb' }) =>
    D<TextoTraducido>(api.post('/translation/text', d)),
  vistaPrevia: (d: { context_type: 'ticket' | 'conversation'; context_id: string; text: string; target_language?: string }) =>
    D<VistaPrevia>(api.post('/translation/outbound/preview', d)),

  glosario: () => D<{ items: TerminoDeGlosario[] }>(api.get('/translation/glossary')),
  crearTermino: (d: Partial<Omit<TerminoDeGlosario, 'id' | 'updated_at'>>) => D<TerminoDeGlosario>(api.post('/translation/glossary', d)),
  cambiarTermino: (id: string, d: Partial<Omit<TerminoDeGlosario, 'id' | 'updated_at'>>) =>
    D<TerminoDeGlosario>(api.patch(`/translation/glossary/${id}`, d)),
  borrarTermino: (id: string) => D<{ ok: boolean }>(api.delete(`/translation/glossary/${id}`)),

  uso: () => D<UsoDeTraduccion>(api.get('/translation/usage')),
  probar: (d: { provider?: 'ai' | 'deepl' | 'azure'; target_language: string; text: string }) =>
    D<PruebaDeTraduccion>(api.post('/translation/test', d)),

  versionesKb: (articleId: string) => D<VersionesKb>(api.get(`/translation/kb/${articleId}`)),
  generarKb: (articleId: string, languages?: string[]) => D<GeneracionKb>(api.post(`/translation/kb/${articleId}/generate`, { languages })),
  editarKb: (articleId: string, language: string, d: { title?: string; summary?: string; body?: string }) =>
    D<VersionKb>(api.patch(`/translation/kb/${articleId}/${language}`, d)),
  revisarKb: (articleId: string, language: string, d: { publish: boolean; comment?: string }) =>
    D<VersionKb>(api.post(`/translation/kb/${articleId}/${language}/review`, d)),
  borrarKb: (articleId: string, language: string) => D<{ ok: boolean }>(api.delete(`/translation/kb/${articleId}/${language}`)),

  resumenDeContenido: () => D<ResumenDeContenidoDelPortal>(api.get('/translation/portal-content')),
  versionesDeContenido: (tipo: TipoDeContenidoDelPortal, id: string) => D<VersionesDeContenido>(api.get(`/translation/portal-content/${tipo}/${id}`)),
  generarContenido: (tipo: TipoDeContenidoDelPortal, id: string, languages?: string[]) =>
    D<{ generated: VersionDeContenido[]; failed: { language: string; reason: string }[] }>(api.post(`/translation/portal-content/${tipo}/${id}/generate`, { languages })),
  editarContenido: (tipo: TipoDeContenidoDelPortal, id: string, language: string, fields: Record<string, string>) =>
    D<VersionDeContenido>(api.patch(`/translation/portal-content/${tipo}/${id}/${language}`, { fields })),
  revisarContenido: (tipo: TipoDeContenidoDelPortal, id: string, language: string, d: { publish: boolean; comment?: string }) =>
    D<VersionDeContenido>(api.post(`/translation/portal-content/${tipo}/${id}/${language}/review`, d)),
  borrarContenido: (tipo: TipoDeContenidoDelPortal, id: string, language: string) =>
    D<{ ok: boolean }>(api.delete(`/translation/portal-content/${tipo}/${id}/${language}`)),
}
