/**
 * Texto plano con los enlaces convertidos en `<a>` (24-11-2026, chat del portal).
 *
 * Sin HTML: el texto se parte en trozos de React. Solo se enlazan `http(s)://`
 * y `www.`; cada URL pasa por `sanitizeUrl` y se abre en otra pestaña con
 * `noopener noreferrer` (la página de destino no puede tocar la nuestra ni ve
 * de dónde viene). Respeta los saltos de línea (`white-space: pre-wrap` en la
 * clase del contenedor).
 */
import { Fragment } from 'react'
import { sanitizeUrl } from '../../utils/security'

const PATRON_URL = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+)/gi
/** Signos que suelen cerrar una frase y no forman parte del enlace. */
const COLA = /[.,;:!?)\]]+$/

export function partirEnlaces(texto: string): Array<{ texto: string; href?: string }> {
  const trozos: Array<{ texto: string; href?: string }> = []
  let ultimo = 0
  for (const m of texto.matchAll(PATRON_URL)) {
    const inicio = m.index ?? 0
    let url = m[0]
    const cola = url.match(COLA)?.[0] ?? ''
    if (cola) url = url.slice(0, -cola.length)
    if (inicio > ultimo) trozos.push({ texto: texto.slice(ultimo, inicio) })
    const href = sanitizeUrl(url.toLowerCase().startsWith('www.') ? `https://${url}` : url)
    trozos.push(href && href !== '#' ? { texto: url, href } : { texto: url })
    ultimo = inicio + url.length
  }
  if (ultimo < texto.length) trozos.push({ texto: texto.slice(ultimo) })
  return trozos
}

export default function TextoConEnlaces({ texto, className }: { texto: string; className?: string }) {
  return (
    <div className={className}>
      {partirEnlaces(texto || '').map((t, i) => t.href ? (
        <a key={i} href={t.href} target="_blank" rel="noopener noreferrer">{t.texto}</a>
      ) : <Fragment key={i}>{t.texto}</Fragment>)}
    </div>
  )
}
