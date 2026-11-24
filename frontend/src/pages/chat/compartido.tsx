/**
 * Tipos y utilidades compartidas del chat.
 * Troceado de ChatPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import type { ReactNode } from 'react'
import { formateadorDeFecha } from '../../utils/helpers'
import { IconButton, Pulsable } from '../../components/ui'

// ── Entity types ────────────────────────────────────────────────────────────
// The collaboration API client returns untyped data (`r.data` / `unknown[]`),
// so each query states the shape it reads. Fields come from the backend
// serializers in app/services/collaboration/** where they exist; the rest are
// what this page reads, optional. Type annotations only — no runtime effect.

/** Conversación (canal, directo o grupo). */
export interface Conv { id: string; kind?: string; title?: string | null; peer_user_id?: string | null; channel_type?: string | null }

/** Usuario o grupo (`@menciones`, miembros elegidos, usuario de la sesión). */
export interface UserLike { id: string; full_name?: string | null; username?: string | null; email?: string | null; is_group?: boolean }

export interface MentionSuggestions { users?: UserLike[]; groups?: UserLike[] }

export interface Reaction { emoji: string; user_id: string | null; client_user_id: string | null }

export interface Attachment {
  id: string; name: string; mime_type: string | null; size_bytes: number
  av_status?: string | null; dlp_status?: string | null; is_quarantined?: boolean
  // `getAttachment` los añade al pedir el detalle.
  download_url?: string | null; preview_url?: string | null
}

interface PollOption { label: string; votes?: number }

/** `metadata_json` de un mensaje de bot: la tarjeta que pinta y sus datos. */
export interface BotMeta {
  card?: string; task_id?: string; ticket?: { number?: string | number | null; id?: string; assignee?: string }
  hours?: number; project_id?: string; title?: string; text?: string; room?: string; actions?: unknown[]
  source?: string; question?: string; options?: PollOption[]
  // Acta del asistente de reuniones (card `meeting_minutes`, 19-11-2026)
  meeting_id?: string; document_id?: string | null; link?: string; status?: string
}

/** `_serialize_message` (app/services/collaboration/messages.py). */
export interface Msg {
  id: string; conversation_id: string; thread_id: string | null; parent_message_id: string | null
  user_id: string | null; client_user_id: string | null; bot_id: string | null
  author_name: string | null; author_avatar: string | null
  type: string; status: string; body: string | null; body_html: string | null
  metadata_json: BotMeta; has_attachments: boolean; attachments: Attachment[]; reactions: Reaction[]
  is_pinned: boolean; is_redacted: boolean; linked_task_id: string | null; linked_ticket_id: string | null
  // `_serialize_message` los envía desde la auditoría 2026-11 (antes no llegaban nunca).
  linked_deliverable_id?: string | null; linked_risk_id?: string | null
  edited_at: string | null; deleted_at: string | null; sent_at: string
  // 24-11-2026 (chat del portal): el mensaje al que responde.
  reply_to?: { id: string; author_name: string | null; body: string; is_deleted: boolean } | null
}

export interface Team { id: string; name: string }

export interface Channel { id: string; team_id: string; name: string; conversation_id: string }

export interface Presence { user_id: string; status: string; user_name?: string | null; is_in_call?: boolean }

export interface CollabNotification { id: string; is_read: boolean; title: string; body: string | null }

export interface ChatBot { id: string; name?: string }

export interface Member { id?: string; user_id: string; user_name?: string | null; role?: string | null; is_admin?: boolean }

export interface NotificationRule { scope: string; target_id: string | null; notify_messages: string }

export interface SearchHit { id: string; conversation_id: string; snippet: string; sent_at: string | null }

export interface LinkCandidate { id: string; label: string }

export interface SlashCommand { name: string; desc: string }

/** Fila con vista previa: fijados, menciones y guardados. */
export interface PreviewRow { id: string; preview: string }

export interface CallRow { id: string; kind: string; duration_seconds: number; status: string; has_summary?: boolean }

interface CalendarEvent { id: string; link?: string | null; title: string; source: string; start: string | null }

export interface CalendarData { events?: CalendarEvent[]; providers_connected?: string[] }

export interface Decision { id: string; text: string | null }

export type LinkPicker = { messageId: string; kind: string }

export type TypingDetail = { conversation_id?: string; payload?: { user_id?: string | null; client_user_id?: string | null; name?: string; active?: boolean } }

/** Título visible. El backend titula los canales "# nombre" y aquí el «#» ya lo
 *  pone el icono: se quita del texto (antes salía «# # General»). */
export function tituloConv(c: Pick<Conv, 'title'> | null | undefined): string {
  return (c?.title || '').replace(/^#\s*/, '').trim()
}

/** Hora corta (hh:mm) con el formateador de fechas de la app. */
const HORA: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' }

export function fmtHora(d: string | null | undefined): string {
  return d ? formateadorDeFecha(HORA).format(new Date(d)) : ''
}

/** Botón de icono 32×32. `title` sirve también de nombre accesible.
 *  ghost/danger = IconButton variante="caja" del kit (estándar de acciones de
 *  icono, 23-11-2026); primary = botón de envío relleno del compositor. */
export function IconBtn({ children, onClick, title, variant = 'ghost', expanded }: {
  children: ReactNode; onClick?: () => void; title?: string
  variant?: 'ghost' | 'primary' | 'danger'; expanded?: boolean
}) {
  if (variant !== 'primary') {
    return (
      <IconButton variante="caja" tono={variant === 'danger' ? 'peligro' : 'neutro'} onClick={onClick}
        ariaLabel={title ?? ''} aria-expanded={expanded}>{children}</IconButton>
    )
  }
  return (
    <Pulsable type="button" onClick={onClick} title={title} aria-label={title}
      aria-expanded={expanded}
      className="chat-enviar"
    >{children}</Pulsable>
  )
}
