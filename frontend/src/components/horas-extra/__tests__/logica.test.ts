// Horas extra (18-11-2026): consumo frente a límites, línea de tiempo, franjas y CSV.
import { describe, expect, it } from 'vitest'
import {
  aCsv, horasDeFranja, lineaPorDia, nivelDeConsumo, nivelDeFila, paresDeDatos, pctDeLimite, pctDePresupuesto,
  peorLimite, porcentaje, reglasQueEncajan, totalesDeResumen,
} from '../logica'
import type { FilaResumenHe, LimiteConsumido } from '../../../services/api/horas-extra'

const lim = (consumo: number, umbral: number, pct = -1): LimiteConsumido =>
  ({ campo: 'horas_en_anio_pago', umbral, consumo, pct, politica: 'p', efecto: 'block' })

const fila = (p: Partial<FilaResumenHe>): FilaResumenHe => ({
  clave: 'k', etiqueta: 'K', peticiones: 1, horas_pedidas: 0, horas_aprobadas: 0, horas_pendientes: 0, horas_rechazadas: 0,
  horas_reales: 0, horas_sin_autorizar: 0, horas_pago: 0, horas_bolsa: 0, horas_ponderadas_pago: 0,
  presupuesto: null, limites: [], ...p,
})

describe('consumo frente a límites', () => {
  it('porcentaje y niveles en los umbrales 80 y 100', () => {
    expect(porcentaje(40, 80)).toBe(50)
    expect(porcentaje(5, 0)).toBe(0)
    expect(nivelDeConsumo(79.9)).toBe('ok')
    expect(nivelDeConsumo(80)).toBe('atencion')
    expect(nivelDeConsumo(100)).toBe('excedido')
  })
  it('el porcentaje del límite sale de consumo / umbral (pct del servidor solo sin umbral)', () => {
    expect(pctDeLimite(lim(72, 80, 0.9))).toBe(90)
    expect(pctDeLimite(lim(1, 0, 33))).toBe(33)
  })
  it('peor límite y nivel de la fila (límites y presupuesto)', () => {
    expect(peorLimite([])).toBeNull()
    expect(peorLimite([lim(10, 80), lim(70, 80), lim(1, 8)])?.consumo).toBe(70)
    expect(nivelDeFila(fila({ limites: [lim(10, 80)] }))).toBe('ok')
    expect(nivelDeFila(fila({ limites: [lim(10, 80)], presupuesto: { horas: 100, restantes: 15 } }))).toBe('atencion')
    expect(nivelDeFila(fila({ limites: [lim(81, 80)] }))).toBe('excedido')
    expect(pctDePresupuesto({ horas: 100, restantes: -10 })).toBe(110)
    expect(pctDePresupuesto({ horas: 0, restantes: 0 })).toBeNull()
  })
  it('totales del resumen', () => {
    const t = totalesDeResumen([fila({ horas_pedidas: 2.5, horas_ponderadas_pago: 3.75 }), fila({ horas_pedidas: 1.25, horas_sin_autorizar: 2 })])
    expect(t).toEqual({ pedidas: 3.75, aprobadas: 0, pendientes: 0, reales: 0, sin_autorizar: 2, a_pagar: 3.75 })
  })
})

describe('línea de tiempo y datos', () => {
  it('ordena y agrupa por día', () => {
    const g = lineaPorDia([
      { tipo: 'aprobada', quien: 'B', cuando: '2026-11-19T10:00:00', datos: null },
      { tipo: 'creada', quien: 'A', cuando: '2026-11-18T09:00:00', datos: null },
      { tipo: 'en_aprobacion', quien: null, cuando: '2026-11-18T09:00:01', datos: null },
    ])
    expect(g.map(x => x.dia)).toEqual(['2026-11-18', '2026-11-19'])
    expect(g[0].eventos.map(e => e.tipo)).toEqual(['creada', 'en_aprobacion'])
  })
  it('pares de datos sin vacíos y objetos en JSON', () => {
    expect(paresDeDatos({ a: 1, b: null, c: '', d: { x: 1 } })).toEqual([['a', '1'], ['d', '{"x":1}']])
    expect(paresDeDatos(null)).toEqual([])
  })
})

describe('franjas, reglas y CSV', () => {
  it('horas de una franja, también cruzando la medianoche', () => {
    expect(horasDeFranja('18:00', '20:30')).toBe(2.5)
    expect(horasDeFranja('22:00', '02:00')).toBe(4)
    expect(horasDeFranja('18:00', null)).toBeNull()
  })
  it('reglas que encajaron de las políticas que aplican', () => {
    expect(reglasQueEncajan([
      { politica: 'Máximo legal', aplica: true, reglas: [{ regla: '80 h/año', cumple: true }, { regla: 'otra', cumple: false }] },
      { politica: 'No aplica', aplica: false, reglas: [{ regla: 'x', cumple: true }] },
    ])).toEqual([{ politica: 'Máximo legal', reglas: ['80 h/año'] }])
  })
  it('CSV con comillas cuando hace falta', () => {
    expect(aCsv(['a', 'b'], [['x,y', 'di "hola"'], [1, null]])).toBe('a,b\r\n"x,y","di ""hola"""\r\n1,')
  })
})
