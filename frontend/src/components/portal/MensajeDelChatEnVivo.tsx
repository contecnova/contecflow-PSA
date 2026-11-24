/**
 * Un mensaje del chat en vivo de Soporte (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md §10).
 *
 * Lo pintan los dos lados (bandeja de canales del operador y Soporte → Chat
 * en vivo del cliente) con la MISMA fila del chat interno (`FilaDeMensaje`,
 * «un solo chat»): avatar, nombre, hora, cita, texto con enlaces seguros,
 * imágenes y ficheros (`AdjuntoDelChat`: siempre por la API con la sesión),
 * reacciones y la barra flotante de acciones. Las acciones dependen del lado:
 * responder y reaccionar, los dos; editar y borrar, el autor; ver el historial,
 * solo el operador.
 */
import type { ReactNode } from 'react'
import { History, Pencil, Reply, Trash2 } from 'lucide-react'
import { TextoConEnlaces } from '../ui'
import { type AccionDeMensaje, EstadoDeEntrega, EtiquetaDeAutor, FilaDeMensaje, agruparReacciones } from '../chat'
import type { MensajeDeCanal } from '../../services/api/serviceDeskMercado'
import AdjuntoDelChat from './AdjuntoDelChat'
import type { ChatEnVivoApi, LadoDelChatEnVivo } from './chatEnVivoApi'
import { useTextoConversacion } from './GovernedConversationsComun'

export interface MensajeDelChatEnVivoProps {
  m: MensajeDeCanal
  lado: LadoDelChatEnVivo
  convId: string
  api: ChatEnVivoApi
  /** Nombre que se enseña (el autor o, si no hay, «Cliente» / «Equipo» / «Asistente»). */
  autor: string
  /** Nombre del autor de la cita si no viene. */
  autorDeCita?: (authorType: string) => string
  esMio: boolean
  quien: { userId?: string | null; clientId?: string | null }
  /** El cuerpo ya preparado (p. ej. traducido en la bandeja); sin él, texto con enlaces. */
  cuerpo?: ReactNode
  /** Lo que va bajo el texto además de los adjuntos (entrega, artículos…). */
  extras?: ReactNode
  /** «Leído» si es el propio y el otro lado ya lo leyó; null = no aplica. */
  leido?: boolean | null
  /** La conversación está abierta (sin ella, solo lectura). */
  activa: boolean
  compacto?: boolean
  onResponder: (m: MensajeDeCanal) => void
  onEditar: (m: MensajeDeCanal) => void
  onBorrar: (m: MensajeDeCanal) => void
  onReaccionar: (m: MensajeDeCanal, emoji: string) => void
  onHistorial?: (m: MensajeDeCanal) => void
  onError: (e: unknown) => void
}

export default function MensajeDelChatEnVivo({
  m, lado, convId, api, autor, autorDeCita, esMio, quien, cuerpo, extras, leido, activa, compacto,
  onResponder, onEditar, onBorrar, onReaccionar, onHistorial, onError,
}: MensajeDelChatEnVivoProps) {
  const t = useTextoConversacion(lado)
  const borrado = !!m.is_deleted
  const adjuntos = borrado ? [] : (m.attachments || [])
  const soloAdjunto = adjuntos.length > 0 && adjuntos.some(a => a.name === m.body)
  const interactivo = activa && !borrado && m.author_type !== 'system'
  const historial: AccionDeMensaje[] = lado === 'team' && onHistorial && (m.edited_at || borrado)
    ? [{ clave: 'historial', etiqueta: t('governedconversations.ver_historial'), icono: <History size={13} aria-hidden="true" />, onClick: () => onHistorial(m) }]
    : []
  const acciones: AccionDeMensaje[] = !interactivo ? historial : [
    { clave: 'responder', etiqueta: t('governedconversations.responder'), icono: <Reply size={13} aria-hidden="true" />, onClick: () => onResponder(m) },
    ...(esMio ? [
      { clave: 'editar', etiqueta: t('governedconversations.editar'), icono: <Pencil size={13} aria-hidden="true" />, onClick: () => onEditar(m) },
      { clave: 'borrar', etiqueta: t('governedconversations.borrar'), icono: <Trash2 size={13} aria-hidden="true" />, onClick: () => onBorrar(m), peligro: true },
    ] : []),
    ...historial,
  ]
  const cita = m.reply_to
    ? { autor: m.reply_to.author_name || autorDeCita?.(m.reply_to.author_type) || '', texto: m.reply_to.body, borrada: m.reply_to.is_deleted }
    : null
  return (
    <FilaDeMensaje
      autor={autor}
      fecha={m.created_at}
      // 24-11-2026 (burbujas): lo de quien mira a la derecha (cliente: lo suyo; operador: lo suyo).
      propio={esMio}
      compacto={compacto}
      borrado={borrado}
      esBot={m.author_type === 'bot'}
      editado={!!m.edited_at && !borrado}
      textos={{
        mensajeDe: t('governedconversations.mensaje_de', { name: autor }),
        acciones: t('governedconversations.acciones_del_mensaje'),
        editado: t('governedconversations.editado'),
        eliminado: t('governedconversations.mensaje_borrado'),
        reaccion: (emoji, n) => t('governedconversations.reaccion_de', { emoji, n }),
        reaccionarCon: (emoji) => t('governedconversations.reaccionar_con', { emoji }),
      }}
      insignias={m.author_type === 'customer' && lado === 'team' ? <EtiquetaDeAutor>{t('governedconversations.remitente_cliente')}</EtiquetaDeAutor> : null}
      cita={cita}
      cuerpo={borrado
        ? <div className="chat-msg__body">{t('governedconversations.mensaje_borrado')}</div>
        : soloAdjunto ? null : (cuerpo ?? <TextoConEnlaces texto={m.body || ''} className="chat-msg__body" />)}
      extras={<>
        {adjuntos.length > 0 && (
          <div className="chat-msg__attachments">
            {adjuntos.map(a => (
              <AdjuntoDelChat key={a.id} adjunto={a} cargar={(id) => api.adjunto(convId, id)} t={t} onError={onError} />
            ))}
          </div>
        )}
        {extras}
      </>}
      reacciones={borrado ? [] : agruparReacciones(m.reactions, quien)}
      onReaccionar={interactivo ? (emoji) => onReaccionar(m, emoji) : undefined}
      acciones={acciones}
      accionesSiBorrado={historial}
      pie={esMio && !borrado && leido !== null && leido !== undefined ? (
        <EstadoDeEntrega leido={leido} textoLeido={t('governedconversations.leido')} textoEnviado={t('governedconversations.enviado')} />
      ) : null}
    />
  )
}
