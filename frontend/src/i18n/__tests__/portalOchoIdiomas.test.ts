// Portal de clientes en 8 idiomas (16-11-2026).
//
// La interfaz de operadores va en es/en/zh (`i18n/langs/*.mjs`); el portal de
// clientes ofrece 8 (`i18n/portal/*.ts`) y TODO su texto visible tiene que
// salir de esos 8 diccionarios. Estos tests fallan si:
//   1. una clave del portal falta en alguno de los 8 diccionarios (o sobra);
//   2. el portal usa una clave que no existe en los 8;
//   3. un componente del portal llama al traductor de operador.
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { PORTAL_TRANSLATIONS, PORTAL_LANGUAGES } from '../portalTranslations'

const SRC = join(__dirname, '..', '..')
const IDIOMAS = ['es', 'en', 'fr', 'de', 'pt', 'it', 'pl', 'zh'] as const

/** Ficheros que pinta el portal de clientes (y la vista pública por enlace). */
function ficherosDelPortal(): string[] {
  const dir = join(SRC, 'pages', 'portal-client')
  return [
    ...readdirSync(dir).filter((f) => f.endsWith('.tsx')).map((f) => join(dir, f)),
    join(SRC, 'pages', 'PortalClientePage.tsx'),
    join(SRC, 'pages', 'PortalPublicViewPage.tsx'),
  ]
}

const GOVERNED = join(SRC, 'components', 'portal', 'GovernedConversations.tsx')

/** Troceado de GovernedConversations (23-11-2026, auditoria M12): la bandeja son estos tres ficheros; el panel de politicas (solo operadores) vive aparte en ConversationPoliciesPanel.tsx y no cuenta. */
const GOVERNED_FICHEROS = ['GovernedConversationsComun.tsx', 'GovernedConversationsPiezas.tsx', 'GovernedConversations.tsx']
  .map((f) => join(SRC, 'components', 'portal', f))

/** La bandeja de conversaciones gobernadas sin el panel de politicas (solo operadores). */
function governedSinPanelDePoliticas(): string {
  return GOVERNED_FICHEROS.map((f) => readFileSync(f, 'utf8')).join('\n')
}

/** Nombres con los que el portal guarda su traductor (`const X = useLang()`). */
const TRADUCTORES = ['t', 'tp', 'tr', 'tf', '_t', 'traducir', 'portal']

/** Claves que usa un fichero del portal:
 *  - primer argumento literal de una llamada a un traductor del portal;
 *  - cualquier literal `modulo.clave` (las claves que vinieron del diccionario
 *    de operador conservan ese nombre), también en ternarios y tablas. */
function clavesUsadas(fuente: string): Set<string> {
  const claves = new Set<string>()
  const llamada = new RegExp(`(?<![\\w.])(?:${TRADUCTORES.join('|')})\\(\\s*(['"])([^'"\`$]+)\\1`, 'g')
  for (const m of fuente.matchAll(llamada)) claves.add(m[2])
  for (const m of fuente.matchAll(/['"]([a-z][a-z0-9_]*\.[a-z0-9_]+)['"]/g)) {
    // `import x from './y.css'`, rutas, extensiones: no son claves.
    if (/\.(css|tsx?|mjs|json|png|svg)$/.test(m[1])) continue
    claves.add(m[1])
  }
  // Plantillas `modulo.prefijo_${x}`: se comprueba que exista alguna con ese prefijo.
  for (const m of fuente.matchAll(/`([a-z][a-z0-9_]*\.[a-z0-9_]+)\$\{/g)) claves.add(`${m[1]}*`)
  return claves
}

describe('portal de clientes: 8 idiomas', () => {
  it('ofrece exactamente los 8 idiomas, sin banderas emoji', () => {
    expect(PORTAL_LANGUAGES.map((l) => l.code)).toEqual([...IDIOMAS])
    for (const l of PORTAL_LANGUAGES) {
      expect(l.label.trim()).not.toBe('')
      expect(/\p{Extended_Pictographic}|\p{Regional_Indicator}/u.test(JSON.stringify(l))).toBe(false)
    }
  })

  it('los 8 diccionarios tienen las mismas claves y ningún texto vacío', () => {
    const base = Object.keys(PORTAL_TRANSLATIONS.es).sort()
    for (const idioma of IDIOMAS) {
      const dic = PORTAL_TRANSLATIONS[idioma]
      const claves = Object.keys(dic).sort()
      const faltan = base.filter((k) => !(k in dic))
      const sobran = claves.filter((k) => !(k in PORTAL_TRANSLATIONS.es))
      expect({ idioma, faltan, sobran }).toEqual({ idioma, faltan: [], sobran: [] })
      const vacias = claves.filter((k) => typeof dic[k] !== 'string' || !dic[k].trim())
      expect({ idioma, vacias }).toEqual({ idioma, vacias: [] })
    }
  })

  it('las variables {{x}} de cada texto son las mismas en los 8 idiomas', () => {
    const vars = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort().join(',')
    const distintas: string[] = []
    for (const [clave, es] of Object.entries(PORTAL_TRANSLATIONS.es)) {
      for (const idioma of IDIOMAS) {
        const otro = PORTAL_TRANSLATIONS[idioma][clave]
        if (otro !== undefined && vars(otro) !== vars(es)) distintas.push(`${idioma}:${clave}`)
      }
    }
    expect(distintas).toEqual([])
  })

  it('toda clave que usa el portal existe en los 8 diccionarios', () => {
    const fuentes: Array<[string, string]> = [
      ...ficherosDelPortal().map((f) => [f, readFileSync(f, 'utf8')] as [string, string]),
      [GOVERNED, governedSinPanelDePoliticas()],
    ]
    const faltan: string[] = []
    for (const [fichero, fuente] of fuentes) {
      for (const clave of clavesUsadas(fuente)) {
        for (const idioma of IDIOMAS) {
          const dic = PORTAL_TRANSLATIONS[idioma]
          const existe = clave.endsWith('*')
            ? Object.keys(dic).some((k) => k.startsWith(clave.slice(0, -1)))
            : clave in dic
          if (!existe) faltan.push(`${fichero.split(/[\\/]/).pop()}: ${clave} (${idioma})`)
        }
      }
    }
    expect(faltan).toEqual([])
  })
})

describe('portal de clientes: nunca el traductor de operador', () => {
  const OPERADOR = /\b(useAppT|useAppLang|traducirSinHook)\s*\(|from\s+['"][./]*(?:\.\.\/)*i18n\/AppLangContext['"]|from\s+['"][./]*hooks\/useAppT['"]|\betiquetaCodigo\s*\(/

  it.each(ficherosDelPortal().map((f) => [f.split(/[\\/]/).pop() as string, f]))(
    '%s no usa el traductor de operador',
    (_nombre, fichero) => {
      const lineas = readFileSync(fichero, 'utf8').split(/\r?\n/)
        .map((l, i) => [i + 1, l] as const)
        .filter(([, l]) => !/^\s*(\/\/|\*|\/\*)/.test(l) && OPERADOR.test(l))
        .map(([n, l]) => `${n}: ${l.trim()}`)
      expect(lineas).toEqual([])
    },
  )

  it('GovernedConversations: solo el panel de políticas y el selector usan el de operador', () => {
    const fuente = governedSinPanelDePoliticas()
    // Fuera del panel de políticas, `useAppLang(` aparece una sola vez: dentro
    // de `useTextoConversacion`, que elige el traductor según `mode`.
    const usos = [...fuente.matchAll(/\buseAppLang\s*\(/g)].length
    expect(usos).toBe(1)
    const hook = fuente.slice(fuente.indexOf('export function useTextoConversacion'))
    expect(hook.indexOf('useAppLang(')).toBeGreaterThan(-1)
    expect(hook.indexOf('useAppLang(')).toBeLessThan(hook.indexOf('\n}'))
    expect(/mode === 'client'/.test(hook.slice(0, hook.indexOf('\n}')))).toBe(true)
    // Ningún componente de la bandeja llama a useAppT.
    expect(/\buseAppT\s*\(/.test(fuente)).toBe(false)
  })
})
