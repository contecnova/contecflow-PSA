/**
 * Selector de emoji del kit (24-11-2026, chat del portal completo).
 *
 * Un botón de icono que abre una rejilla de emojis habituales. Se usa para
 * insertar un emoji en un texto o para reaccionar a un mensaje. Sin
 * dependencias: la lista es corta y fija (los de uso más común en chats de
 * trabajo), y cada emoji es un botón accesible con su propio carácter como
 * nombre. Esc o pulsar fuera lo cierran y el foco vuelve al botón.
 *
 * Textos: `uikit.elegir_emoji` (operador y portal, vía `useTextoUi`).
 */
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Smile } from 'lucide-react'
import IconButton from './IconButton'
import { useTextoUi } from './useTextoUi'
import './SelectorDeEmoji.css'

/** Reacciones rápidas: las mismas en el chat interno y en el del portal. */
export const REACCIONES_RAPIDAS = ['👍', '❤️', '😂', '🎉', '✅', '👀'] as const

/** Emojis del selector (los de las reacciones rápidas primero). */
export const EMOJIS_DEL_SELECTOR: readonly string[] = [
  ...REACCIONES_RAPIDAS,
  '😀', '😃', '😄', '😁', '😊', '🙂', '😉', '😍', '🤔', '😅', '😮', '😢', '😡', '🙏', '👏', '🙌',
  '👌', '✌️', '🤝', '💪', '👎', '🔥', '⭐', '💡', '📌', '📎', '📄', '📅', '⏰', '⚠️', '❗', '❓',
  '🚀', '🎯', '🛠️', '🐞', '💬', '📞', '📹', '🔒',
]

export interface SelectorDeEmojiProps {
  onElegir: (emoji: string) => void
  /** Nombre del botón (por defecto «Elegir emoji»). */
  ariaLabel?: string
  disabled?: boolean
  /** Icono del botón (por defecto, una cara sonriente). */
  icono?: ReactNode
  tamano?: 'xs' | 'sm' | 'md'
}

export function SelectorDeEmoji({ onElegir, ariaLabel, disabled, icono, tamano = 'sm' }: SelectorDeEmojiProps) {
  const t = useTextoUi()
  const [abierto, setAbierto] = useState(false)
  const contenedor = useRef<HTMLDivElement | null>(null)
  const boton = useRef<HTMLDivElement | null>(null)
  const id = useId()
  const nombre = ariaLabel || t('uikit.elegir_emoji')

  useEffect(() => {
    if (!abierto) return undefined
    const fuera = (e: MouseEvent) => {
      if (contenedor.current && !contenedor.current.contains(e.target as Node)) setAbierto(false)
    }
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setAbierto(false)
        boton.current?.querySelector('button')?.focus()
      }
    }
    document.addEventListener('mousedown', fuera)
    document.addEventListener('keydown', tecla)
    return () => {
      document.removeEventListener('mousedown', fuera)
      document.removeEventListener('keydown', tecla)
    }
  }, [abierto])

  return (
    <div className="selector-emoji" ref={contenedor}>
      <div ref={boton}>
        <IconButton variante="caja" tamano={tamano} ariaLabel={nombre} disabled={disabled}
          aria-expanded={abierto} aria-controls={id} onClick={() => setAbierto(v => !v)}>
          {icono ?? <Smile size={15} aria-hidden="true" />}
        </IconButton>
      </div>
      {abierto && (
        <div id={id} role="listbox" aria-label={nombre} className="selector-emoji__panel">
          {EMOJIS_DEL_SELECTOR.map(e => (
            <button key={e} type="button" role="option" aria-selected={false} aria-label={e}
              className="selector-emoji__opcion"
              onClick={() => { onElegir(e); setAbierto(false) }}>{e}</button>
          ))}
        </div>
      )}
    </div>
  )
}

export default SelectorDeEmoji
