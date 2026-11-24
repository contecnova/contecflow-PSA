/**
 * Incidencias de usuarios reales (23-11-2026): 3 (valores crudos del alta de
 * ticket), 5 (idioma por defecto inglés) y 10 (resultado de «probar conexión»
 * traducido).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { etiquetaDeCampoDinamico, etiquetaDeOpcionDinamica, legible, valorDePistaDeEnrutado } from '../pages/service-desk/camposDinamicosSd'
import { textoDeResultado } from '../utils/resultadoConCodigo'
import { IDIOMA_DE_RESPALDO, idiomaDelNavegador } from '../i18n/appTranslations.ts'
import { IDIOMA_FUENTE, IDIOMA_POR_DEFECTO, idiomaInicialDelPortal } from '../i18n/portalTranslations'

const DICC: Record<string, string> = {
  'sd_campos_dinamicos.campo_affected_environment': 'Affected environment',
  'sd_campos_dinamicos.opcion_produccion': 'Production',
  'sd_campos_dinamicos.cola_incident_l1': 'Incidents · first line',
  'err_srv.buzon_prueba_ok': '{protocolo}: {n} unread emails',
}
const t = (clave: string, otro?: string | Record<string, unknown>) => {
  const v = DICC[clave]
  if (v === undefined) return typeof otro === 'string' ? otro : clave
  if (otro && typeof otro === 'object') return v.replace(/\{(\w+)\}/g, (_, k: string) => String(otro[k]))
  return v
}

describe('incidencia 3: campos dinámicos legibles', () => {
  it('traduce la etiqueta y las opciones de serie; respeta las del administrador', () => {
    expect(etiquetaDeCampoDinamico(t, { id: 'affected_environment', label: 'Entorno afectado' })).toBe('Affected environment')
    expect(etiquetaDeCampoDinamico(t, { id: 'campo_propio', label: 'Mi campo' })).toBe('Mi campo')
    expect(etiquetaDeOpcionDinamica(t, 'produccion')).toBe('Production')
    expect(etiquetaDeOpcionDinamica(t, 'valor_propio')).toBe('valor_propio')
  })
  it('la cola sugerida sale por su nombre, nunca la clave cruda', () => {
    expect(valorDePistaDeEnrutado(t, 'queue', 'incident_l1')).toBe('Incidents · first line')
    expect(valorDePistaDeEnrutado(t, 'queue', 'cola_rara')).toBe('Cola rara')
    expect(valorDePistaDeEnrutado(t, 'priority', 'p2_high', { priority: { p2_high: 'High' } })).toBe('High')
    expect(legible('incident_l2')).toBe('Incident l2')
  })
})

describe('incidencia 5: idioma por defecto', () => {
  afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

  it('inglés por defecto; el castellano sigue siendo la fuente', () => {
    expect(IDIOMA_DE_RESPALDO).toBe('en')
    expect(IDIOMA_POR_DEFECTO).toBe('en')
    expect(IDIOMA_FUENTE).toBe('es')
  })
  it('navegador soportado > inglés', () => {
    vi.stubGlobal('navigator', { language: 'zh-CN', languages: ['zh-CN'] })
    expect(idiomaDelNavegador()).toBe('zh')
    vi.stubGlobal('navigator', { language: 'ja-JP', languages: ['ja-JP'] })
    expect(idiomaDelNavegador()).toBe('en')
  })
  it('portal: preferencia guardada > navegador > inglés', () => {
    vi.stubGlobal('navigator', { language: 'ja-JP', languages: ['ja-JP'] })
    expect(idiomaInicialDelPortal()).toBe('en')
    vi.stubGlobal('navigator', { language: 'de-DE', languages: ['de-DE'] })
    expect(idiomaInicialDelPortal()).toBe('de')
    localStorage.setItem('client_user', JSON.stringify({ language: 'it' }))
    expect(idiomaInicialDelPortal()).toBe('it')
  })
})

describe('incidencia 10: resultado de la prueba con código', () => {
  it('traduce el código y cae al texto de respaldo', () => {
    expect(textoDeResultado(t, { code: 'buzon_prueba_ok', params: { protocolo: 'imap', n: 3 }, detail: 'imap: 3 sin leer' }))
      .toBe('imap: 3 unread emails')
    expect(textoDeResultado(t, { code: 'desconocido', detail: 'texto del servidor' })).toBe('texto del servidor')
    expect(textoDeResultado(t, null, 'respaldo')).toBe('respaldo')
  })
})
