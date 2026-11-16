// 16-11-2026: la traducción con el proveedor «IA» puede usar cualquier IA
// generalista configurada (Gemini, Claude, GPT…). Se elige en Ajustes →
// Traducción y se guarda en la ruta por función del Hub de IA (`translation`),
// la misma que usa el servidor; y el Hub enseña el nombre de cada función en el
// idioma del operador.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'

const raiz = resolve(__dirname, '..')
const seccion = readFileSync(resolve(raiz, 'pages/settings-sections/TraduccionSection.tsx'), 'utf8')
const hub = readFileSync(resolve(raiz, 'pages/AIHubPage.tsx'), 'utf8')
const rutas = readFileSync(resolve(raiz, '../../app/services/ai_provider_service/rutas.py'), 'utf8')

describe('IA que traduce', () => {
  it('guarda en la ruta por función del Hub, sin una configuración aparte', () => {
    expect(seccion).toMatch(/MODULO_TRADUCCION = 'translation'/)
    expect(seccion).toMatch(/aiProvidersApi\.saveRouting\(/)
    expect(seccion).toMatch(/\.\.\.\(enrutado\?\.routes \|\| \{\}\)/) // conserva las demás rutas
    expect(rutas).toMatch(/"translation":/)
  })

  it('tiene sus textos en los tres idiomas de operador', () => {
    for (const d of [es, en, zh] as Array<Record<string, Record<string, unknown>>>) {
      for (const k of ['ia_titulo', 'ia_desc', 'ia_proveedor', 'ia_principal', 'ia_principal_de', 'ia_modelo', 'ia_guardada', 'ia_error']) {
        expect(typeof d.traduccion_admin[k], k).toBe('string')
      }
    }
  })

  it('el Hub nombra cada función en el idioma del operador', () => {
    const claves = [...rutas.matchAll(/^\s+"([a-z_0-9]+)":\s*"/gm)].map(m => m[1])
    expect(claves.length).toBeGreaterThan(10)
    for (const d of [es, en, zh] as Array<Record<string, Record<string, Record<string, string>>>>) {
      for (const k of claves) expect(typeof d.aihub.modulo[k], k).toBe('string')
    }
    expect(hub).toMatch(/aihub\.modulo\.\$\{m\.key\}/)
  })
})
