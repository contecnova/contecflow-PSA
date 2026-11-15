/**
 * Markdown mínimo de las respuestas de IA y de los artículos: párrafos, saltos de
 * línea, títulos (`#` a `####`), viñetas (`* ` o `- `), **negrita** y *cursiva*. Sin HTML: cada trozo es texto de React.
 *
 * Revisión 2026-11: vivía dentro de NarrativeCard; el resultado de NexusAgent
 * enseñaba los asteriscos en crudo.
 */
import React from 'react'
import './MarkdownText.css'

const VINETA = /^\s*[*-]\s+/
const TITULO = /^\s*(#{1,4})\s+/

function enLinea(texto: string) {
  return texto.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/).map((trozo, i) => {
    if (/^\*\*[^*]+\*\*$/.test(trozo)) return <strong key={i}>{trozo.slice(2, -2)}</strong>
    if (/^\*[^*\s][^*]*\*$/.test(trozo)) return <em key={i}>{trozo.slice(1, -1)}</em>
    return trozo
  })
}

export default function MarkdownText({ text, className, style }: { text: string; className?: string; style?: React.CSSProperties }) {
  return (
    <div className={className} style={style}>
      {text.split(/\n\n+/).map((parrafo, pi) => (
        <p key={pi} className={`${pi > 0 ? 'markdown-text-m1' : 'markdown-text-m2'}`}>
          {parrafo.split(/\n/).map((linea, li) => TITULO.test(linea) ? (
            <strong className={`uimarktext-box-1 ${li ? 'markdown-text-m3' : 'markdown-text-m4'}`} key={li} role="heading" aria-level={Math.min(6, (linea.match(TITULO)?.[1].length ?? 1) + 2)}>
              {enLinea(linea.replace(TITULO, ''))}
            </strong>
          ) : (
            <span key={li} className={VINETA.test(linea) ? 'markdown-text-vineta' : undefined}>
              {li > 0 && !VINETA.test(linea) && <br />}
              {VINETA.test(linea) ? <>{'•  '}{enLinea(linea.replace(VINETA, ''))}</> : enLinea(linea)}
            </span>
          ))}
        </p>
      ))}
    </div>
  )
}
