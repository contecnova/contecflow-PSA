// Los nombres de métricas y categorías que manda el backend se traducen por
// código (`etiquetaCodigo`) y, si el código no está en el diccionario, se
// muestra el nombre recibido.
import { describe, expect, it } from 'vitest'
import { etiquetaCodigo } from '../etiquetaCodigo'
import {
  descripcionMetrica,
  etiquetaCategoriaMetrica,
  etiquetaMetrica,
  etiquetaMetricaBi,
} from '../catalogoMetricas'
import en from '../langs/en.mjs'
import es from '../langs/es.mjs'
import zh from '../langs/zh.mjs'

type Arbol = { [k: string]: string | Arbol }
const traductor = (dic: Arbol) => (clave: string, respaldo?: unknown): string => {
  const v = clave.split('.').reduce<unknown>((a, p) => (a as Arbol | undefined)?.[p], dic)
  return typeof v === 'string' ? v : typeof respaldo === 'string' ? respaldo : clave
}
const tEs = traductor(es as Arbol) as never
const tEn = traductor(en as Arbol) as never
const tZh = traductor(zh as Arbol) as never

describe('catálogos del backend traducidos por código', () => {
  it('una métrica del catálogo se traduce en los tres idiomas', () => {
    expect(etiquetaMetrica(tEs, 'hours_by_person', 'x')).toBe('Horas por persona')
    expect(etiquetaMetrica(tEn, 'hours_by_person', 'x')).toBe('Hours by person')
    expect(etiquetaMetrica(tZh, 'hours_by_person', 'x')).toBe('按人员统计工时')
  })

  it('una métrica que el diccionario no conoce muestra el nombre recibido', () => {
    expect(etiquetaMetrica(tEn, 'metrica_nueva', 'Métrica nueva')).toBe('Métrica nueva')
    expect(descripcionMetrica(tEn, 'metrica_nueva', 'Descripción nueva')).toBe('Descripción nueva')
  })

  it('sin código ni respaldo no rompe', () => {
    expect(etiquetaMetrica(tEn, undefined, null)).toBe('')
  })

  it('la descripción de la métrica se traduce', () => {
    expect(descripcionMetrica(tEn, 'hours_by_week')).toBe('Weekly trend of logged hours')
  })

  it('las categorías con tilde o espacio resuelven su clave', () => {
    expect(etiquetaCategoriaMetrica(tEn, 'Formación')).toBe(etiquetaCodigo(tEn, 'catalogo_categoria', 'formacion'))
    expect(etiquetaCategoriaMetrica(tEn, 'Formación')).not.toBe('Formación')
    expect(etiquetaCategoriaMetrica(tEn, 'Service Desk')).toBe('Service Desk')
    expect(etiquetaCategoriaMetrica(tZh, 'Horas')).not.toBe('Horas')
    expect(etiquetaCategoriaMetrica(tEn, 'Categoría nueva')).toBe('Categoría nueva')
  })

  it('el marcador de moneda ¤ se sustituye por el símbolo de la empresa', () => {
    expect(etiquetaMetricaBi(tEn, 'invoice_overdue_amount', 'x', '$')).toBe('Overdue invoices ($)')
    expect(etiquetaMetricaBi(tEs, 'invoice_overdue_amount', 'x', '€')).toBe('Facturas vencidas (€)')
  })

  it('las métricas de previsión sin traducción muestran su código', () => {
    expect(etiquetaMetricaBi(tEn, 'tickets', 'tickets')).toBe('tickets')
    expect(etiquetaMetricaBi(tEn, 'utilization', 'utilization')).toBe('Team utilisation (%)')
  })
})
