// Tipos, constantes y traductor compartidos por las conversaciones gobernadas del portal. 23-11-2026: troceado de GovernedConversations sin cambio de comportamiento.
import type { AxiosInstance } from 'axios'
import type { PortalMensajeDeConversacion, PortalPoliticaDeConversacion } from '../../services/api/tipos-alm'
import { useLang } from '../../pages/portal-client/portalClientContext'
import { useAppLang } from '../../i18n/AppLangContext'

// Formas del backend: app/services/portal_conversation_service (serializacion.py, politicas.py).

export type ConversationPolicy = PortalPoliticaDeConversacion

export type Message = PortalMensajeDeConversacion

/** `_participant_out` (lo que se pinta). */
interface Participant {
  id: string
  display_name: string
}

/** `_conversation_out` / `_legacy_conversation_out`. */
export interface Conversation {
  id: string
  source: string
  title?: string | null
  topic_type?: string | null
  policy?: ConversationPolicy | null
  assigned_group_name?: string | null
  assigned_role_key?: string | null
  is_sla_breached?: boolean
  pending_review_count?: number
  created_at?: string | null
  last_message_at?: string | null
  participants?: Participant[]
  unread_for_team?: number
  unread_for_client?: number
  last_message?: Message | null
}

/** Borrador editable de una política (keywords como texto separado por comas). */
export interface PolicyDraft {
  requires_client_message_approval?: boolean
  requires_team_message_approval?: boolean
  redact_sensitive_content?: boolean
  allow_legacy_federation?: boolean
  assignment_mode?: string
  default_role_key?: string
  default_group_id?: string
  first_response_hours?: number
  escalation_hours?: number
  approval_role_key?: string
  sensitive_keywords?: string
}

type PolicyFlag = 'requires_client_message_approval' | 'requires_team_message_approval' | 'redact_sensitive_content' | 'allow_legacy_federation'

/** Lo que se envía al guardar una política. */
export interface PolicyPayload {
  requires_client_message_approval: boolean
  requires_team_message_approval: boolean
  redact_sensitive_content: boolean
  allow_legacy_federation: boolean
  assignment_mode?: string
  default_group_id: string | null
  default_role_key: string | null
  first_response_hours: number
  escalation_hours: number
  approval_role_key: string | null
  sensitive_keywords: string[]
}

export interface AgentGroup {
  id: string
  name: string
}

/** Cliente axios: el del backoffice o el del portal. */
export type ApiClient = Pick<AxiosInstance, 'get' | 'post' | 'put' | 'delete'>

export type Toast = { success: (m: string) => void; error: (m: string) => void }

export type Mode = 'team' | 'client'

export type ProjectOption = { id: string; name?: string; code?: string }

export type UserOption = { id: string; full_name?: string; email?: string }

type GrcLabel = { text: string; color: string }

// Portal en 8 idiomas (16-11-2026): la bandeja la comparten el portal de
// clientes (`mode="client"`, 8 idiomas: diccionarios `i18n/portal/*`) y la
// vista interna (`mode="team"`, idioma del operador: es/en/zh). Las claves se
// llaman igual en los dos sistemas (`governedconversations.*`); solo cambia el
// traductor. Se llaman los dos hooks siempre (reglas de hooks) y se elige uno.
type TraductorDeConversacion = (clave: string, vars?: Record<string, string | number>) => string

export function useTextoConversacion(mode: Mode): TraductorDeConversacion {
  const { t: operador } = useAppLang()
  const portal = useLang()
  return mode === 'client'
    ? (clave, vars) => portal(clave, vars)
    : (clave, vars) => (vars ? operador(clave, vars) : operador(clave))
}

// 16-11-2026 (pasada de diseño): los textos son claves `governedconversations.*`
// (antes, literales en español dentro del código).
export const TOPIC_OPTIONS = ['general', 'project', 'billing', 'security', 'governance']

/** Nombre visible del tema de una conversación o política (nunca el código). */
export function etiquetaDeTema(t: (k: string) => string, tema?: string | null): string {
  const codigo = tema || 'general'
  return TOPIC_OPTIONS.includes(codigo) ? t(`governedconversations.tema_${codigo}`) : codigo
}

export const SOURCE_KEY: Record<string, string> = {
  native: 'governedconversations.origen_gobernada',
  legacy_client_message: 'governedconversations.origen_anterior',
}

export const GRC_LABEL: Record<string, GrcLabel> = {
  allowed: { text: 'governedconversations.grc_allowed', color: 'var(--success)' },
  pending_review: { text: 'governedconversations.grc_pending_review', color: 'var(--warning)' },
  redacted: { text: 'governedconversations.grc_redacted', color: 'var(--accent)' },
  blocked: { text: 'governedconversations.grc_blocked', color: 'var(--danger)' },
}

export const EMPTY_LIST: never[] = []

export const POLICY_FLAGS: Array<[PolicyFlag, string]> = [
  ['requires_client_message_approval', 'governedconversations.flag_aprobacion_cliente'],
  ['requires_team_message_approval', 'governedconversations.flag_aprobacion_equipo'],
  ['redact_sensitive_content', 'governedconversations.flag_ocultar_sensible'],
  ['allow_legacy_federation', 'governedconversations.flag_chat_anterior'],
]
