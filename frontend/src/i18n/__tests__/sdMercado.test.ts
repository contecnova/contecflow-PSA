// Service desk — mejoras de mercado (16-11-2026): los textos nuevos existen en
// los tres idiomas de la aplicación (es/en/zh) y los del portal en todos los
// idiomas que ofrece el portal.
import { describe, expect, it } from 'vitest'
import en from '../langs/en.mjs'
import es from '../langs/es.mjs'
import zh from '../langs/zh.mjs'
import { PORTAL_LANGUAGES, PORTAL_TRANSLATIONS } from '../portalTranslations'
import { etiquetaCodigo } from '../etiquetaCodigo'

type Arbol = { [k: string]: string | Arbol }
const hojas = (o: Arbol, prefijo = ''): string[] =>
  Object.entries(o).flatMap(([k, v]) => typeof v === 'string' ? [`${prefijo}${k}`] : hojas(v, `${prefijo}${k}.`))

describe('sd_mercado', () => {
  const claves = (d: unknown) => hojas((d as { sd_mercado: Arbol }).sd_mercado).sort()

  it('tiene las mismas claves en es, en y zh, y ninguna vacía', () => {
    expect(claves(en)).toEqual(claves(es))
    expect(claves(zh)).toEqual(claves(es))
    for (const d of [es, en, zh]) {
      const raiz = (d as { sd_mercado: Arbol }).sd_mercado
      for (const k of hojas(raiz)) {
        const valor = k.split('.').reduce<string | Arbol>((n, p) => (n as Arbol)[p], raiz)
        expect(String(valor).trim()).not.toBe('')
      }
    }
  })

  it('traduce los códigos del backend que pinta la pantalla', () => {
    const t = ((clave: string, respaldo?: string) => {
      const v = clave.split('.').reduce<unknown>((n, p) => (n as Record<string, unknown> | undefined)?.[p], es)
      return typeof v === 'string' ? v : respaldo ?? clave
    }) as never
    expect(etiquetaCodigo(t, 'sd_mercado.ejec', 'suggested')).toBe('Propuesto')
    expect(etiquetaCodigo(t, 'sd_mercado.pb', 'pw-reset')).toBe('Restablecer contraseña')
    expect(etiquetaCodigo(t, 'sd_mercado.conv_estado', 'waiting_agent')).toBe('Espera agente')
  })

  it('el catálogo de aprobaciones conoce las peticiones del catálogo', () => {
    for (const d of [es, en, zh]) expect((d as { approvals: Record<string, string> }).approvals.entity_catalog_request).toBeTruthy()
  })
})

describe('portal: asistente y chat', () => {
  it('cada idioma del portal tiene todos los textos sdm_*', () => {
    const base = Object.keys(PORTAL_TRANSLATIONS.es).filter(k => k.startsWith('sdm_')).sort()
    expect(base.length).toBeGreaterThan(30)
    for (const { code } of PORTAL_LANGUAGES) {
      const dic = PORTAL_TRANSLATIONS[code]
      expect(Object.keys(dic).filter(k => k.startsWith('sdm_')).sort()).toEqual(base)
      for (const k of base) expect(dic[k].trim()).not.toBe('')
    }
  })
})
