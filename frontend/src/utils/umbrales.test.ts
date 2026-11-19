/**
 * Umbrales de semáforo (19-11-2026): una definición por métrica, la misma regla
 * que `app/core/umbrales.py` (`tests/test_umbrales_por_metrica_2026_11_19.py`).
 */
import { describe, expect, it } from 'vitest'
import { conDefectos, estadoDeCarga, tonoDe, UMBRALES_POR_DEFECTO } from './umbrales'
import { loadColor } from './helpers'

describe('tonoDe', () => {
  it('más es peor: corta por encima del umbral (presupuesto 70/90)', () => {
    expect(tonoDe('presupuesto', 70)).toBe('success')
    expect(tonoDe('presupuesto', 70.1)).toBe('warning')
    expect(tonoDe('presupuesto', 90)).toBe('warning')
    expect(tonoDe('presupuesto', 90.1)).toBe('danger')
  })

  it('menos es peor: bueno desde el aviso (SLA 90/75)', () => {
    expect(tonoDe('sla', 90)).toBe('success')
    expect(tonoDe('sla', 89.9)).toBe('warning')
    expect(tonoDe('sla', 74.9)).toBe('danger')
  })

  it('inclusivo: riesgo «desde» y días que faltan «o menos»', () => {
    expect(tonoDe('riesgo', 75)).toBe('danger')
    expect(tonoDe('riesgo', 50)).toBe('warning')
    expect(tonoDe('vencimiento', 14)).toBe('danger')
    expect(tonoDe('vencimiento', 30)).toBe('warning')
    expect(tonoDe('vencimiento', 31)).toBe('success')
  })

  it('sin dato no hay tono', () => {
    expect(tonoDe('presupuesto', null)).toBeUndefined()
    expect(tonoDe('sla', undefined)).toBeUndefined()
  })

  it('usa los umbrales de la empresa que manda el servidor', () => {
    const u = conDefectos({ presupuesto: { aviso: 50, critico: 80, mayor_peor: true } })
    expect(tonoDe('presupuesto', 85, u)).toBe('danger')
    expect(tonoDe('presupuesto', 85)).toBe('warning')
    // Lo que no manda el servidor sigue con el valor por defecto.
    expect(u.carga).toEqual(UMBRALES_POR_DEFECTO.carga)
  })
})

describe('estadoDeCarga y loadColor', () => {
  it('cuatro bandas con UMBRAL_CARGA_* y RESOURCE_UNDERUSE_PCT', () => {
    expect(estadoDeCarga(101)).toBe('sobrecargado')
    expect(estadoDeCarga(90)).toBe('alto')
    expect(estadoDeCarga(50)).toBe('ocupado')
    expect(estadoDeCarga(49)).toBe('disponible')
  })

  it('loadColor delega en la misma regla', () => {
    expect(loadColor(110)).toBe('var(--danger)')
    expect(loadColor(90)).toBe('var(--warning)')
    expect(loadColor(70)).toBe('var(--success)')
    expect(loadColor(90, conDefectos({ carga: { aviso: 95, critico: 120, mayor_peor: true } }))).toBe('var(--success)')
  })
})
