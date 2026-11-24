/**
 * Llamadas a la API del chat en vivo de Soporte (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md §10).
 *
 * Las mismas operaciones para los dos lados; cambia la ruta y el cliente HTTP:
 * el operador va por `/sd/channels/conversations/{id}/…` (bandeja de canales) y
 * el cliente por `/sd/channels/livechat/{id}/…` (portal). Backend:
 * app/api/v1/endpoints/service_desk/canales.py y
 * app/services/service_desk/chat_en_vivo.py.
 *
 * El cliente NO tiene `llamar`: solo aceptar, rechazar y colgar (el servidor
 * responde 403 `portal_llamada_solo_operador` si lo intenta igualmente).
 */
import type { AxiosInstance } from 'axios'
import type { PortalAjustesDelChat, PortalLlamada } from '../../services/api/tipos-alm'
import type { VersionDeMensaje } from './chatDelPortalApi'

export type ClienteHttp = Pick<AxiosInstance, 'get' | 'post' | 'put' | 'delete'>
export type LadoDelChatEnVivo = 'team' | 'client'

const datos = <T,>(r: { data: unknown }) => r.data as T

export function chatEnVivoApi(http: ClienteHttp, lado: LadoDelChatEnVivo) {
  const conv = (id: string) => lado === 'team'
    ? `/sd/channels/conversations/${encodeURIComponent(id)}`
    : `/sd/channels/livechat/${encodeURIComponent(id)}`
  const ficheros = lado === 'team' ? 'files' : 'attachments'
  return {
    ajustes: () => http.get(lado === 'team' ? '/sd/channels/chat-settings' : '/sd/channels/livechat/settings').then(datos<PortalAjustesDelChat>),
    subir: (convId: string, fichero: File, extra: { caption?: string; replyTo?: string | null }) => {
      const fd = new FormData()
      fd.append('file', fichero, fichero.name)
      if (extra.caption) fd.append('caption', extra.caption)
      if (extra.replyTo) fd.append('reply_to_message_id', extra.replyTo)
      return http.post(`${conv(convId)}/${ficheros}`, fd).then(r => r.data)
    },
    /** El fichero como blob (vista previa o descarga): la API comprueba empresa y conversación. */
    adjunto: (convId: string, adjuntoId: string) =>
      http.get(`${conv(convId)}/${ficheros}/${encodeURIComponent(adjuntoId)}`, { responseType: 'blob' }).then(r => r.data as Blob),
    editar: (convId: string, msgId: string, body: string) =>
      http.put(`${conv(convId)}/messages/${encodeURIComponent(msgId)}`, { body }).then(r => r.data),
    borrar: (convId: string, msgId: string) =>
      http.delete(`${conv(convId)}/messages/${encodeURIComponent(msgId)}`).then(r => r.data),
    reaccionar: (convId: string, msgId: string, emoji: string) =>
      http.post(`${conv(convId)}/messages/${encodeURIComponent(msgId)}/reactions`, { emoji }).then(r => r.data),
    /** Rastro de ediciones y borrados (solo el operador). */
    versiones: (convId: string, msgId: string) =>
      http.get(`${conv(convId)}/messages/${encodeURIComponent(msgId)}/versions`).then(datos<VersionDeMensaje[]>),
    llamadas: (convId: string) => http.get(`${conv(convId)}/calls`).then(datos<PortalLlamada[]>),
    // Operador: llamar, entrar y colgar.
    // En el lado del cliente ni se pide: el cliente no llama nunca (y el servidor responde 403).
    llamar: (convId: string, kind: 'audio' | 'video') => lado === 'client'
      ? Promise.reject(new Error('portal_llamada_solo_operador'))
      : http.post(`${conv(convId)}/calls`, { kind }).then(datos<PortalLlamada>),
    unirse: (convId: string, callId: string) =>
      http.post(`${conv(convId)}/calls/${encodeURIComponent(callId)}/join`).then(datos<PortalLlamada>),
    colgar: (convId: string, callId: string) =>
      http.post(`${conv(convId)}/calls/${encodeURIComponent(callId)}/end`).then(datos<PortalLlamada>),
    // Cliente: aceptar o rechazar (nunca iniciar).
    aceptar: (convId: string, callId: string) =>
      http.post(`${conv(convId)}/calls/${encodeURIComponent(callId)}/accept`).then(datos<PortalLlamada>),
    rechazar: (convId: string, callId: string) =>
      http.post(`${conv(convId)}/calls/${encodeURIComponent(callId)}/decline`).then(datos<PortalLlamada>),
    sonando: () => http.get('/sd/channels/livechat/calls/ringing').then(datos<PortalLlamada[]>),
  }
}

export type ChatEnVivoApi = ReturnType<typeof chatEnVivoApi>
