/**
 * Botón de icono del chat y hora corta (24-11-2026, «un solo chat»).
 * Salen de `pages/chat/compartido.tsx` sin cambios (allí se reexportan como
 * `IconBtn` y `fmtHora`) para que los usen también los chats del portal.
 */
import type { ReactNode } from 'react'
import { Phone, Video } from 'lucide-react'
import { formateadorDeFecha } from '../../utils/helpers'
import { IconButton, Pulsable } from '../ui'

/** Hora corta (hh:mm) con el formateador de fechas de la app. */
const HORA: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' }

export function fmtHora(d: string | null | undefined): string {
  return d ? formateadorDeFecha(HORA).format(new Date(d)) : ''
}

/** Botón de icono 32×32. `title` sirve también de nombre accesible.
 *  ghost/danger = IconButton variante="caja" del kit (estándar de acciones de
 *  icono, 23-11-2026); primary = botón de envío relleno del compositor. */
export function BotonDeChat({ children, onClick, title, variant = 'ghost', expanded, disabled }: {
  children: ReactNode; onClick?: () => void; title?: string
  variant?: 'ghost' | 'primary' | 'danger'; expanded?: boolean; disabled?: boolean
}) {
  if (variant !== 'primary') {
    return (
      <IconButton variante="caja" tono={variant === 'danger' ? 'peligro' : 'neutro'} onClick={onClick}
        ariaLabel={title ?? ''} aria-expanded={expanded} disabled={disabled}>{children}</IconButton>
    )
  }
  return (
    <Pulsable type="button" onClick={onClick} title={title} aria-label={title}
      aria-expanded={expanded} disabled={disabled}
      className="chat-enviar"
    >{children}</Pulsable>
  )
}

/** Llamar y videollamar en la cabecera de la conversación, como en el chat interno
 *  (mismos botones y misma colocación). En el portal solo los ve el operador con
 *  `clientes.llamar`: el cliente nunca inicia (lo impone el servidor). */
export function BotonesDeLlamada({ onLlamar, etiquetaVoz, etiquetaVideo, video = true, desactivado }: {
  onLlamar: (kind: 'audio' | 'video') => void
  etiquetaVoz: string
  etiquetaVideo: string
  /** Sin vídeo (la empresa lo tiene apagado), solo el de voz. */
  video?: boolean
  desactivado?: boolean
}) {
  return (
    <>
      <BotonDeChat onClick={() => onLlamar('audio')} title={etiquetaVoz} disabled={desactivado}><Phone size={15} aria-hidden="true" /></BotonDeChat>
      {video && <BotonDeChat onClick={() => onLlamar('video')} title={etiquetaVideo} disabled={desactivado}><Video size={15} aria-hidden="true" /></BotonDeChat>}
    </>
  )
}
