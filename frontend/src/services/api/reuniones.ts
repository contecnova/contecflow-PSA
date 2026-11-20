/**
 * services/api/reuniones.ts — asistente de reuniones (19-11-2026).
 *
 * Teams, Zoom, Meet (recogida al terminar), bot invitado y grabación propia
 * desde el navegador. Diseño en docs/ASISTENTE_DE_REUNIONES.md.
 * Base `/meeting-assistant`. El interceptor de `_core` ya desenvuelve
 * `{ ok, data }`: `r.data` es el contenido.
 */
import api from './_core'

export type EstadoReunion = 'programada' | 'bot_unido' | 'grabando' | 'procesando' | 'esperando_consentimiento' | 'lista' | 'error'
export type OrigenReunion = 'transcript' | 'upload' | 'recording' | 'bot' | 'teams' | 'zoom' | 'meet' | 'chat_call'
export type PlataformaImportable = 'teams' | 'zoom' | 'meet'
export type ConectorReuniones = 'teams' | 'zoom' | 'meet' | 'bots'
export type FormatoTranscripcion = 'txt' | 'vtt' | 'json'
export type MetodoConsentimiento = 'self' | 'verbal' | 'written'
export type RolParticipante = 'organizador' | 'asistente' | 'hablante'

export const ESTADOS_REUNION: EstadoReunion[] = ['programada', 'bot_unido', 'grabando', 'procesando', 'esperando_consentimiento', 'lista', 'error']
export const ORIGENES_REUNION: OrigenReunion[] = ['transcript', 'upload', 'recording', 'bot', 'teams', 'zoom', 'meet', 'chat_call']
/** Estados en los que la reunión aún cambia sola: la pantalla refresca cada pocos segundos. */
export const ESTADOS_EN_CURSO: EstadoReunion[] = ['programada', 'bot_unido', 'grabando', 'procesando']

export interface ReunionResumen {
  id: string
  title: string
  status: EstadoReunion
  origin: OrigenReunion
  platform: string | null
  project_id: string | null
  project_name: string | null
  client_id: string | null
  client_name: string | null
  meeting_date: string | null
  duration_min: number | null
  actions_count: number
  created_actions: number
  has_audio: boolean
  consent_pending: boolean
  bot_status: string | null
  error_code: string | null
  created_at: string
  can_manage: boolean
  /** Llamada del chat interno de la que sale (origen `chat_call`). */
  call_id?: string | null
  conversation_id?: string | null
}

export interface ParticipanteReunion {
  id: string
  user_id: string | null
  name: string
  email: string | null
  role: RolParticipante
  consent: boolean | null
  consent_method: string | null
  consent_at: string | null
  language: string | null
}

export interface SegmentoReunion {
  id: string
  order: number
  speaker: string | null
  user_id: string | null
  participant_id: string | null
  start_ms: number | null
  end_ms: number | null
  text: string
  language: string | null
}

export interface AccionReunion {
  id: string
  description: string
  assignee_name: string | null
  assignee_id: string | null
  due_date: string | null
  due_date_text: string | null
  is_created: boolean
  task_id: string | null
  ticket_id: string | null
}

export interface EventoReunion {
  type: string
  at: string
  actor: string | null
  data: Record<string, unknown> | null
}

export interface ReunionDetalle extends ReunionResumen {
  summary: string | null
  decisions: string[]
  risks: string[]
  open_questions: string[]
  original_language: string | null
  display_language: string | null
  translation: { status: 'original' | 'translated' | 'disabled' | 'unavailable'; reason?: string | null }
  participants: ParticipanteReunion[]
  segments: SegmentoReunion[]
  actions: AccionReunion[]
  minutes_document_id: string | null
  audio: { chunks: number; bytes: number; expires_at: string | null } | null
  transcript_expires_at: string | null
  transcript_purged: boolean
  join_url: string | null
  bot: { provider: string; status: string | null; bot_id: string | null } | null
  consent: { required: boolean; notice_confirmed_by: string | null; notice_confirmed_at: string | null; complete: boolean }
  permissions: { manage: boolean; listen: boolean }
  legal_hold: boolean
  events: EventoReunion[]
}

export interface ParticipanteIn { name: string; email?: string | null; user_id?: string | null }

export interface ReunionIn {
  title: string
  origin: 'recording' | 'transcript' | 'upload'
  source?: 'microphone' | 'tab'
  transcript?: string
  platform?: string | null
  project_id?: string | null
  client_id?: string | null
  meeting_date?: string | null
  participants?: ParticipanteIn[]
  notice_confirmed?: boolean
}

export interface TrozoDeAudio { id: string; seq: number; offset_ms: number; bytes: number; mime: string; expires_at: string | null }
export interface TrozoSubido { chunk_id: string; seq: number; segments_added: number }

export interface ResultadoDeBusqueda {
  meeting_id: string
  title: string
  meeting_date: string | null
  snippet: string
  segment_id: string | null
  start_ms: number | null
}

export interface PreferenciasReuniones {
  collect_teams: boolean
  collect_meet: boolean
  bot_for_my_calendar: boolean
  language: string | null
}
export interface PreferenciasReunionesLeidas extends PreferenciasReuniones {
  /** Lo que la empresa tiene activado (sin ello la preferencia no hace nada). */
  available: { teams: boolean; meet: boolean; bots: boolean }
}

export interface ConfigReuniones {
  consent: { notice_required: boolean; require_consent: boolean; notice_text: string; bot_message: string }
  retention: { audio_days: number; transcript_days: number }
  translation: { per_person: boolean }
  linking: { auto: boolean }
  transcription: { allow_external_stt: boolean; external_stt_contract: string; stt_providers: string[]; stt_effective: string | null }
  teams: {
    enabled: boolean; tenant_id: string; client_id: string; secret_set: boolean; mode: 'polling' | 'subscription'
    client_state_set: boolean; subscription_id: string | null; subscription_expires_at: string | null; webhook_url: string
  }
  zoom: { enabled: boolean; account_id: string; client_id: string; secret_set: boolean; webhook_secret_set: boolean; webhook_url: string }
  meet: { enabled: boolean; service_account_email: string; key_set: boolean }
  bots: {
    enabled: boolean; provider: string; providers: string[]; region: string; api_key_set: boolean; webhook_secret_set: boolean
    bot_name: string; contract_reference: string; contract_accepted_by: string | null; contract_accepted_at: string | null; webhook_url: string
  }
}

/** PUT /config: objeto anidado parcial; los secretos van en claro y vacíos no cambian. */
export interface ConfigReunionesIn {
  consent?: Partial<ConfigReuniones['consent']>
  retention?: Partial<ConfigReuniones['retention']>
  translation?: Partial<ConfigReuniones['translation']>
  linking?: Partial<ConfigReuniones['linking']>
  transcription?: { allow_external_stt?: boolean; external_stt_contract?: string }
  teams?: { enabled?: boolean; tenant_id?: string; client_id?: string; mode?: 'polling' | 'subscription'; client_secret?: string; client_state?: string }
  zoom?: { enabled?: boolean; account_id?: string; client_id?: string; client_secret?: string; webhook_secret?: string }
  meet?: { enabled?: boolean; service_account_email?: string; service_account_key?: string }
  bots?: { enabled?: boolean; provider?: string; region?: string; bot_name?: string; contract_reference?: string; api_key?: string; webhook_secret?: string }
}

export interface PruebaDeConector { ok: boolean; detail: string | null }

/** Asistente en una llamada del chat interno (cuarta vía, 19-11-2026). */
export interface AsistenteDeLlamada {
  call_id: string
  active: boolean
  meeting_id: string | null
  status: EstadoReunion | null
  notice_required: boolean
  notice_text: string | null
  require_consent: boolean
  my_participant_id: string | null
  my_consent: boolean | null
  /** Si quien mira puede pararlo (quien lo activó o gestiona la reunión); sin el campo se intenta y el servidor decide. */
  can_stop?: boolean
}

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
/** Quita los filtros vacíos para no mandar `status=`. */
const limpio = <T extends object>(o: T) =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== null && v !== undefined))

const B = '/meeting-assistant'
const R = (id: string) => `${B}/meetings/${id}`

export const reunionesApi = {
  listar: (f: { status?: string; project_id?: string; q?: string } = {}) =>
    D<ReunionResumen[]>(api.get(`${B}/meetings`, { params: limpio(f) })),
  crear: (r: ReunionIn) => D<ReunionDetalle>(api.post(`${B}/meetings`, r)),
  detalle: (id: string, language?: string) =>
    D<ReunionDetalle>(api.get(R(id), { params: limpio({ language }) })),
  editar: (id: string, c: { title?: string; project_id?: string | null; client_id?: string | null }) =>
    D<ReunionDetalle>(api.patch(R(id), c)),
  borrar: (id: string) => D<unknown>(api.delete(R(id))),

  // Grabación propia: trozos de ~30 s
  subirTrozo: (id: string, trozo: Blob, seq: number, offsetMs: number) => {
    const fd = new FormData()
    fd.append('file', trozo, `trozo-${seq}.webm`)
    fd.append('seq', String(seq))
    fd.append('offset_ms', String(Math.round(offsetMs)))
    return D<TrozoSubido>(api.post(`${R(id)}/audio`, fd))
  },
  terminar: (id: string) => D<ReunionDetalle>(api.post(`${R(id)}/finish`)),
  reprocesar: (id: string) => D<ReunionDetalle>(api.post(`${R(id)}/reprocess`)),

  // Audio (cada escucha y descarga queda auditada en el servidor)
  audio: (id: string) => D<TrozoDeAudio[]>(api.get(`${R(id)}/audio`)),
  trozo: (id: string, chunkId: string, descargar = false) =>
    D<Blob>(api.get(`${R(id)}/audio/${chunkId}`, { params: { download: descargar ? 1 : 0 }, responseType: 'blob' })),
  borrarAudio: (id: string) => D<unknown>(api.delete(`${R(id)}/audio`)),
  transcripcion: (id: string, format: FormatoTranscripcion) =>
    D<Blob>(api.get(`${R(id)}/transcript`, { params: { format }, responseType: 'blob' })),

  editarSegmento: (id: string, sid: string, c: { speaker?: string; user_id?: string | null }) =>
    D<unknown>(api.patch(`${R(id)}/segments/${sid}`, c)),

  anadirParticipante: (id: string, p: ParticipanteIn) => D<unknown>(api.post(`${R(id)}/participants`, p)),
  quitarParticipante: (id: string, pid: string) => D<unknown>(api.delete(`${R(id)}/participants/${pid}`)),
  consentir: (id: string, c: { participant_id?: string; consents: boolean; method?: MetodoConsentimiento }) =>
    D<ReunionDetalle>(api.post(`${R(id)}/consent`, c)),

  editarAccion: (id: string, aid: string, c: { description?: string; assignee_id?: string | null; due_date?: string | null }) =>
    D<unknown>(api.patch(`${R(id)}/actions/${aid}`, c)),
  crearTarea: (id: string, aid: string, projectId?: string | null) =>
    D<{ task_id: string }>(api.post(`${R(id)}/actions/${aid}/task`, limpio({ project_id: projectId }))),
  crearTicket: (id: string, aid: string) =>
    D<{ ticket_id: string; number: string }>(api.post(`${R(id)}/actions/${aid}/ticket`)),
  crearTareas: (id: string, c: { action_ids?: string[]; project_id?: string | null } = {}) =>
    D<{ tasks_created: number; tasks: unknown[] }>(api.post(`${R(id)}/actions/tasks`, limpio(c))),
  generarActa: (id: string) => D<{ document_id: string }>(api.post(`${R(id)}/minutes`)),

  preguntar: (id: string, question: string) => D<{ answer: string }>(api.post(`${R(id)}/ask`, { question })),
  buscar: (q: string) => D<ResultadoDeBusqueda[]>(api.get(`${B}/search`, { params: { q } })),

  invitarBot: (b: { meeting_url: string; title?: string; join_at?: string | null; project_id?: string | null }) =>
    D<ReunionDetalle>(api.post(`${B}/bots`, limpio(b))),
  sacarBot: (id: string) => D<ReunionDetalle>(api.post(`${R(id)}/bot/leave`)),
  importar: (platform: PlataformaImportable, reference: string) =>
    D<ReunionDetalle>(api.post(`${B}/import`, { platform, reference })),

  preferencias: () => D<PreferenciasReunionesLeidas>(api.get(`${B}/me/preferences`)),
  guardarPreferencias: (p: PreferenciasReuniones) => D<PreferenciasReunionesLeidas>(api.put(`${B}/me/preferences`, p)),

  config: () => D<ConfigReuniones>(api.get(`${B}/config`)),
  guardarConfig: (c: ConfigReunionesIn) => D<ConfigReuniones>(api.put(`${B}/config`, c)),
  probar: (conector: ConectorReuniones) => D<PruebaDeConector>(api.post(`${B}/config/test/${conector}`)),
  suscripcionTeams: () => D<{ id: string; expires_at: string }>(api.post(`${B}/config/teams/subscription`)),

  copiaRgpd: (q: { email?: string; user_id?: string }) => D<unknown>(api.get(`${B}/gdpr/person`, { params: limpio(q) })),
  suprimirRgpd: (q: { email?: string; user_id?: string }) => D<unknown>(api.post(`${B}/gdpr/person/erase`, limpio(q))),

  // Llamadas del chat interno
  llamada: (callId: string) => D<AsistenteDeLlamada>(api.get(`${B}/calls/${callId}`)),
  activarEnLlamada: (callId: string) =>
    D<AsistenteDeLlamada>(api.post(`${B}/calls/${callId}/activate`, { notice_confirmed: true })),
  pararEnLlamada: (callId: string) => D<AsistenteDeLlamada>(api.post(`${B}/calls/${callId}/stop`)),
}
