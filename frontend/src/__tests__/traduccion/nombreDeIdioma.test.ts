// Traducción en tiempo real (16-11-2026): el nombre de un idioma sale de
// `Intl.DisplayNames` en el idioma de quien mira, nunca de una tabla fija.
import { describe, it, expect, vi } from 'vitest'

vi.mock('../../i18n/AppLangContext', () => ({ useAppLang: () => ({ lang: 'es', t: (k: string) => k }) }))

import { nombreDeIdioma, motivoDeTraduccion, errorDeTraduccion } from '../../hooks/useTraduccion'

describe('nombreDeIdioma', () => {
  it('nombra el idioma en el idioma de la interfaz', () => {
    expect(nombreDeIdioma('en', 'es').toLowerCase()).toBe('inglés')
    expect(nombreDeIdioma('es', 'en')).toBe('Spanish')
    expect(nombreDeIdioma('fr', 'en')).toBe('French')
  })

  it('el chino tradicional (`zh-hant`) se nombra como tal', () => {
    const nombre = nombreDeIdioma('zh-hant', 'en')
    expect(nombre).toMatch(/Chinese/)
    expect(nombre).not.toBe(nombreDeIdioma('zh', 'en'))
  })

  it('sin código, cadena vacía', () => {
    expect(nombreDeIdioma(null, 'es')).toBe('')
    expect(nombreDeIdioma(undefined, 'es')).toBe('')
    expect(nombreDeIdioma('', 'es')).toBe('')
  })

  it('un código inválido se devuelve tal cual', () => {
    expect(nombreDeIdioma('no válido', 'es')).toBe('no válido')
  })
})

describe('motivoDeTraduccion y errorDeTraduccion', () => {
  const t = (k: string, r?: string | Record<string, unknown>) => (k === 'traduccion.motivo.desconocido' && typeof r === 'string' ? r : k)

  it('traduce el motivo y, sin él, da el genérico', () => {
    expect(motivoDeTraduccion(t, 'timeout')).toBe('traduccion.motivo.timeout')
    expect(motivoDeTraduccion(t, null)).toBe('traduccion.motivo.provider_error')
    expect(motivoDeTraduccion(t, 'desconocido')).toBe('traduccion.motivo.provider_error')
  })

  it('los códigos `trad_*` del servidor se traducen; el resto se deja', () => {
    expect(errorDeTraduccion(t, 'trad_idioma_no_soportado')).toBe('traduccion.err.idioma_no_soportado')
    expect(errorDeTraduccion(t, 'Otro error')).toBe('Otro error')
    expect(errorDeTraduccion(t, '')).toBe('traduccion.err.generico')
  })
})
