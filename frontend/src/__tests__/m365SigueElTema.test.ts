// 16-11-2026: la pantalla de Microsoft 365 pintaba la pestaña activa y los
// botones con azul fijo (`--info`) sobre el fondo del tema y llevaba emojis en
// títulos, pestañas y botones. Ahora usa los componentes comunes y el color del
// tema; el botón «Exportar Excel» de todas las cabeceras lleva icono, no emoji.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'

const raiz = resolve(__dirname, '..')
const leer = (p: string) => readFileSync(resolve(raiz, p), 'utf8')
const EMOJI = /\p{Extended_Pictographic}/u

describe('Microsoft 365 sigue el tema', () => {
  it('no usa el azul fijo ni pestañas o botones propios', () => {
    const tsx = leer('pages/M365Page.tsx')
    const css = leer('pages/M365Page.css')
    expect(css).not.toMatch(/var\(--info\)/)
    expect(tsx).toMatch(/<Tabs\b/)
    expect(tsx).toMatch(/<Button\b/)
    expect(tsx).not.toMatch(EMOJI)
  })

  it('sus textos no llevan emojis en ningún idioma', () => {
    for (const d of [es, en, zh] as Array<Record<string, Record<string, string>>>) {
      for (const modulo of ['pagina_m365', 'm365']) {
        for (const [clave, valor] of Object.entries(d[modulo] || {})) {
          expect(EMOJI.test(String(valor)), `${modulo}.${clave}`).toBe(false)
        }
      }
    }
  })

  it('el botón de exportar de la cabecera usa icono, no emoji', () => {
    expect(leer('components/layout/PageHeader.tsx')).not.toMatch(EMOJI)
  })
})
