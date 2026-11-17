// @vitest-environment node
// Migración al kit (16-11-2026): las hojas de estilo fuera de components/ui e
// index.css no llevan mayúsculas forzadas, letra monoespaciada, colores
// literales ni alto fijo en px en controles. Los ficheros de
// kit-pendientes.json (sección css) tienen un cupo que solo puede encoger.
import fs from 'node:fs'
import path from 'node:path'
import { describe, it, expect } from 'vitest'
import { analizarCss, hojasFueraDelKit, COMPROBACIONES_CSS } from '../../scripts/kit/comprobarCss.mjs'

const RAIZ = path.resolve(__dirname, '../..')
const CUPOS = JSON.parse(fs.readFileSync(path.join(RAIZ, 'kit-pendientes.json'), 'utf8')).css as Record<string, Record<string, number>>

describe('comprobación de CSS del kit', () => {
  it('detecta cada incumplimiento', () => {
    const r = analizarCss(`
      /* text-transform: uppercase en un comentario no cuenta */
      .a { text-transform: uppercase; color: var(--text-1); }
      .b { font-family: var(--font-mono); background: #fff; }
      .c { box-shadow: 0 0 0 1px rgba(0, 0, 0, .2); border-color: color-mix(in srgb, var(--accent) 20%, transparent); }
      @media (max-width: 600px) { .x-btn { height: 30px; } .barra { height: 30px; } }
      .campo input { height: 32px; min-height: 38px; }
      .d { text-transform: none; font-family: inherit; }
    `)
    expect(r.mayusculas).toHaveLength(1)
    expect(r.monoespaciada).toHaveLength(1)
    expect(r.colorLiteral).toHaveLength(2)
    expect(r.altoFijoControl).toHaveLength(2)
  })

  it('ninguna hoja supera su cupo de kit-pendientes.json', () => {
    const fallos: string[] = []
    for (const rel of hojasFueraDelKit(RAIZ)) {
      const a = analizarCss(fs.readFileSync(path.join(RAIZ, rel), 'utf8'))
      for (const c of COMPROBACIONES_CSS) {
        const cupo = CUPOS[c]?.[rel] ?? 0
        const hallados = a[c as keyof typeof a]
        if (hallados.length > cupo) fallos.push(`${rel} ${c}: ${hallados.length} (cupo ${cupo}) — ${hallados.map(h => `l.${h.linea} ${h.texto}`).join('; ')}`)
      }
    }
    expect(fallos).toEqual([])
  })
})
