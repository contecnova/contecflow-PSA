/**
 * Editor del chat (24-11-2026, «un solo chat»: docs/GUIA_DE_DISENO.md).
 *
 * El compositor del chat interno (`pages/chat/PanelDeConversacion.tsx`), el
 * MISMO en todos los chats: un único cuadro con el texto; arriba a la derecha
 * la @ (solo donde hay menciones: el chat interno) y el selector de emoji
 * (siempre, mismo tamaño y estilo); abajo a la izquierda el clip de adjuntar y
 * abajo a la derecha el botón de enviar (icono). Todo dentro del cuadro.
 * Encima, los avisos de «respondiendo» / «editando» y los menús.
 * Intro envía; Mayús+Intro, salto de línea.
 */
import { type ClipboardEvent, type KeyboardEvent, type ReactNode, type Ref } from 'react'
import { Paperclip, Send, Smile, X } from 'lucide-react'
import { IconButton, SelectorDeEmoji, Textarea } from '../ui'
import { BotonDeChat } from './BotonDeChat'
import './chat.css'

export interface AdjuntarDelEditor {
  /** Título y nombre accesible del clip. */
  etiqueta: string
  onFichero: (f: File) => void
  /** Extensiones aceptadas (`.png,.pdf`); sin él, cualquiera (el servidor valida). */
  aceptar?: string
  desactivado?: boolean
}

export interface EditorDeChatProps {
  valor: string
  onCambiar: (v: string) => void
  onEnviar: () => void
  /** Nombre accesible del campo y texto de ayuda. */
  etiquetaCampo: string
  placeholder?: string
  etiquetaEnviar: string
  adjuntar?: AdjuntarDelEditor | null
  /** Botón de menciones (la @ del chat interno), arriba a la derecha junto al emoji. */
  mencion?: ReactNode
  /** Nombre accesible del selector de emoji (inserta el emoji al final del texto). */
  etiquetaEmoji: string
  /** Avisos y menús encima del cuadro (`AvisoDelEditor`, menciones, comandos). */
  encima?: ReactNode
  campoRef?: Ref<HTMLTextAreaElement>
  onPegar?: (e: ClipboardEvent<HTMLTextAreaElement>) => void
  /** Teclas extra (las menciones del chat interno); Intro sin Mayús envía igualmente. */
  onTecla?: (e: KeyboardEvent<HTMLTextAreaElement>) => void
  desactivado?: boolean
  /** Marca `data-chat-composer` (atajos del chat interno). */
  marcaDeCompositor?: boolean
}

export function EditorDeChat({
  valor, onCambiar, onEnviar, etiquetaCampo, placeholder, etiquetaEnviar, adjuntar, mencion, etiquetaEmoji, encima,
  campoRef, onPegar, onTecla, desactivado, marcaDeCompositor,
}: EditorDeChatProps) {
  return (
    <div className="chat-composer">
      {encima}
      <div className="chat-composer__box">
        <div className="chat-composer__fila">
          <Textarea
            ref={campoRef}
            className="u-flex1-min0"
            {...(marcaDeCompositor ? { 'data-chat-composer': true } : {})}
            aria-label={etiquetaCampo}
            value={valor}
            disabled={desactivado}
            onChange={e => onCambiar(e.target.value)}
            onKeyDown={e => {
              onTecla?.(e)
              if (e.defaultPrevented) return
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                onEnviar()
              }
            }}
            onPaste={onPegar}
            placeholder={placeholder}
            rows={1}
            inputClassName="chat-composer__input"
          />
          <div className="chat-composer__herramientas">
            {mencion}
            <SelectorDeEmoji ariaLabel={etiquetaEmoji} disabled={desactivado} icono={<Smile size={16} aria-hidden="true" />}
              onElegir={e => onCambiar(`${valor}${e}`)} />
          </div>
        </div>
        <div className="chat-composer__pie">
          {adjuntar ? (
            /* Patrón label+input: el click en el label abre el selector sin
               depender de programmatic .click() (más fiable cross-browser) */
            <label title={adjuntar.etiqueta} className="chat-attach">
              <Paperclip size={16} aria-hidden="true" />
              <input type="file" aria-label={adjuntar.etiqueta} className="u-sr-only" accept={adjuntar.aceptar}
                disabled={adjuntar.desactivado}
                onChange={e => {
                  const f = e.target.files?.[0]
                  if (f) adjuntar.onFichero(f)
                  e.target.value = ''
                }} />
            </label>
          ) : <span />}
          <BotonDeChat onClick={onEnviar} title={etiquetaEnviar} variant="primary" disabled={desactivado}>
            <Send size={16} aria-hidden="true" />
          </BotonDeChat>
        </div>
      </div>
    </div>
  )
}

/** Aviso sobre el editor («Respondiendo en hilo», «Editando el mensaje»…) con su botón de cancelar. */
export function AvisoDelEditor({ icono, texto, etiquetaCancelar, onCancelar }: {
  icono: ReactNode; texto: ReactNode; etiquetaCancelar: string; onCancelar: () => void
}) {
  return (
    <div className="chat-hint-bar" role="status">
      {icono} {texto}
      <IconButton variante="caja" onClick={onCancelar} className="chat-icon-close--end" ariaLabel={etiquetaCancelar}>
        <X size={12} aria-hidden="true" />
      </IconButton>
    </div>
  )
}
