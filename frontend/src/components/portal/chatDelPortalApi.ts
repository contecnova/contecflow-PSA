/**
 * Llamadas a la API del chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).
 *
 * Las mismas operaciones para los dos lados; cambia el prefijo (`/team` para el
 * equipo) y el cliente HTTP (el del backoffice o el del portal). Backend:
 * app/api/v1/endpoints/portal_conversations.py.
 */
import type { AxiosInstance } from 'axios'
import type { PortalAjustesDelChat, PortalLlamada, PortalMensajeDeConversacion } from '../../services/api/tipos-alm'

export type ClienteHttp = Pick<AxiosInstance, 'get' | 'post' | 'put' | 'delete'>
export type Lado = 'team' | 'client'

export interface VersionDeMensaje {
  id: string
  change_type: 'edit' | 'delete'
  body: string | null
  raw_body: string | null
  edited_at: string | null
}

export function chatDelPortalApi(http: ClienteHttp, lado: Lado) {
  const base = lado === 'team' ? '/portal/conversations/team' : '/portal/conversations'
  const conv = (id: string) => `${base}/${encodeURIComponent(id)}`
  return {
    ajustes: () => http.get<PortalAjustesDelChat>(`${base}/settings`).then(r => r.data),
    subir: (convId: string, fichero: File, extra: { caption?: string; parentId?: string | null; nota?: boolean }) => {
      const fd = new FormData()
      fd.append('file', fichero, fichero.name)
      if (extra.caption) fd.append('caption', extra.caption)
      if (extra.parentId) fd.append('parent_message_id', extra.parentId)
      if (lado === 'team' && extra.nota) fd.append('is_internal_note', 'true')
      return http.post<PortalMensajeDeConversacion>(`${conv(convId)}/attachments`, fd).then(r => r.data)
    },
    /** El fichero como blob (vista previa de imagen o descarga): la API comprueba que participas. */
    adjunto: (convId: string, adjuntoId: string) =>
      http.get<Blob>(`${conv(convId)}/attachments/${encodeURIComponent(adjuntoId)}`, { responseType: 'blob' }).then(r => r.data),
    editar: (convId: string, msgId: string, body: string) =>
      http.put<PortalMensajeDeConversacion>(`${conv(convId)}/messages/${encodeURIComponent(msgId)}`, { body }).then(r => r.data),
    borrar: (convId: string, msgId: string) =>
      http.delete<PortalMensajeDeConversacion>(`${conv(convId)}/messages/${encodeURIComponent(msgId)}`).then(r => r.data),
    reaccionar: (convId: string, msgId: string, emoji: string) =>
      http.post(`${conv(convId)}/messages/${encodeURIComponent(msgId)}/reactions`, { emoji }).then(r => r.data),
    versiones: (convId: string, msgId: string) =>
      http.get<VersionDeMensaje[]>(`${conv(convId)}/messages/${encodeURIComponent(msgId)}/versions`).then(r => r.data),
    llamadas: (convId: string) => http.get<PortalLlamada[]>(`${conv(convId)}/calls`).then(r => r.data),
    // Equipo: llamar, entrar y colgar.
    llamar: (convId: string, kind: 'audio' | 'video') =>
      http.post<PortalLlamada>(`${conv(convId)}/calls`, { kind }).then(r => r.data),
    unirse: (convId: string, callId: string) =>
      http.post<PortalLlamada>(`${conv(convId)}/calls/${encodeURIComponent(callId)}/join`).then(r => r.data),
    colgar: (convId: string, callId: string) =>
      http.post<PortalLlamada>(`${conv(convId)}/calls/${encodeURIComponent(callId)}/end`).then(r => r.data),
    // Cliente: aceptar o rechazar (nunca iniciar).
    aceptar: (convId: string, callId: string) =>
      http.post<PortalLlamada>(`${conv(convId)}/calls/${encodeURIComponent(callId)}/accept`).then(r => r.data),
    rechazar: (convId: string, callId: string) =>
      http.post<PortalLlamada>(`${conv(convId)}/calls/${encodeURIComponent(callId)}/decline`).then(r => r.data),
    sonando: () => http.get<PortalLlamada[]>(`${base}/calls/ringing`).then(r => r.data),
  }
}

export type ChatDelPortalApi = ReturnType<typeof chatDelPortalApi>

/** Tamaño legible (KB/MB) de un adjunto. */
export function tamanoLegible(bytes: number): string {
  if (!bytes) return '0 KB'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
