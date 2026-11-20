/**
 * Rampa canaria de la empresa (19-11-2026): antes 1/5/25/50/100 y 30/45/60 min
 * fijos en ChangeRolloutPanel; ahora llegan de /settings/org-defaults → propuestas.
 */
import { describe, expect, it } from 'vitest'
import { fasesCanarias } from '../components/servicedesk/ChangeRolloutPanel'
import { PROPUESTAS_POR_DEFECTO } from '../hooks/useOrgSettings'

describe('fasesCanarias', () => {
  it('con los valores por defecto da lo mismo que antes', () => {
    expect(fasesCanarias(PROPUESTAS_POR_DEFECTO, 3)).toEqual([
      { pct: 1, minutos: 30 }, { pct: 5, minutos: 45 }, { pct: 100, minutos: 60 },
    ])
    expect(fasesCanarias(PROPUESTAS_POR_DEFECTO, 5).map(f => f.pct)).toEqual([1, 5, 25, 50, 100])
  })

  it('usa la rampa y los minutos de la empresa', () => {
    const canario = { change_canary_ramp_pct: [10, 30, 100], change_canary_minutes: { first: 15, step: 20, last: 90 } }
    expect(fasesCanarias(canario, 3)).toEqual([
      { pct: 10, minutos: 15 }, { pct: 30, minutos: 20 }, { pct: 100, minutos: 90 },
    ])
  })

  it('respeta el número de fases (1-10), con el mismo recorte que antes', () => {
    // Recorte heredado: con 2 fases la rampa se corta antes del 100 % (igual que antes del ajuste).
    const fases = fasesCanarias(PROPUESTAS_POR_DEFECTO, 2)
    expect(fases.map(f => f.pct)).toEqual([1, 5])
    expect(fasesCanarias(PROPUESTAS_POR_DEFECTO, 4).at(-1)).toEqual({ pct: 100, minutos: 60 })
    expect(fasesCanarias(PROPUESTAS_POR_DEFECTO, 50).length).toBeLessThanOrEqual(10)
  })
})
