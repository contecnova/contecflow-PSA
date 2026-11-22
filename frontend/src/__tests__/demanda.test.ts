import { describe, expect, it } from 'vitest'
import {
  camposCambiados, claveDesdeTexto, definicionVacia, faseNueva, justificacionObligatoria, leerDefinicion, mover, renombrarFase, validarLocal,
} from '../components/demanda/utilDemanda'

describe('flujo de demanda: ayudas puras', () => {
  it('la justificación es obligatoria en reject/return/request_info/skip/hold', () => {
    for (const d of ['reject', 'return', 'request_info', 'skip', 'hold']) expect(justificacionObligatoria(d, false)).toBe(true)
    expect(justificacionObligatoria('approve', false)).toBe(false)
  })

  it('la vía rápida exige justificación solo si el comité era requerido (bypass)', () => {
    expect(justificacionObligatoria('fast_track', true)).toBe(true)
    expect(justificacionObligatoria('fast_track', false)).toBe(false)
    expect(justificacionObligatoria('to_committee', true)).toBe(false)
  })

  it('claveDesdeTexto limpia acentos y símbolos', () => {
    expect(claveDesdeTexto('Revisión de Pares')).toBe('revision_de_pares')
    expect(claveDesdeTexto('1 fase')).toBe('x_1_fase')
  })

  it('mover no sale del rango', () => {
    expect(mover([1, 2, 3], 0, -1)).toEqual([1, 2, 3])
    expect(mover([1, 2, 3], 0, 1)).toEqual([2, 1, 3])
  })

  it('validarLocal detecta claves duplicadas y destinos inexistentes', () => {
    const def = definicionVacia()
    const a = { ...faseNueva(1), key: 'a', name: { es: 'A' } }
    const b = { ...faseNueva(2), key: 'a', name: { es: 'B' }, on_approve: 'zeta' }
    def.phases = [a, b]
    const codigos = validarLocal(def).map(e => e.code)
    expect(codigos).toContain('clave_duplicada')
    expect(codigos).toContain('fase_inexistente')
  })

  it('renombrarFase actualiza referencias y las quita al borrar', () => {
    const def = definicionVacia()
    def.phases = [
      { ...faseNueva(1), key: 'a', name: { es: 'A' }, on_approve: 'b' },
      { ...faseNueva(2), key: 'b', name: { es: 'B' }, return_targets: ['a'] },
    ]
    const renombrada = renombrarFase(def, 'a', 'c')
    expect(renombrada.phases[0].key).toBe('c')
    expect(renombrada.phases[1].return_targets).toEqual(['c'])
    const borrada = renombrarFase(def, 'a', null)
    expect(borrada.phases.map(f => f.key)).toEqual(['b'])
    expect(borrada.phases[0].return_targets).toEqual([])
  })

  it('leerDefinicion rechaza JSON roto y completa los huecos', () => {
    expect(leerDefinicion('{').error).toBeTruthy()
    expect(leerDefinicion('[]').error).toBeTruthy()
    expect(leerDefinicion('{"phases": []}').def?.fields).toEqual([])
  })

  it('camposCambiados solo devuelve lo modificado y convierte tipos', () => {
    const cambios = camposCambiados({ coste: 10, nota: 'x' }, { coste: '25', nota: 'x' }, { coste: 'money', nota: 'text' })
    expect(cambios).toEqual({ coste: 25 })
  })
})
