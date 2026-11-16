// 16-11-2026: en Registrar horas los botones (0,5h…8h) son atajos; la cantidad
// también se escribe a mano, con coma o punto.
import { describe, expect, it } from 'vitest'
import { leerHoras } from '../pages/ImputarPage'

describe('horas escritas a mano', () => {
  it('acepta coma o punto y redondea a centésimas', () => {
    expect(leerHoras('2,25')).toBe(2.25)
    expect(leerHoras('2.25')).toBe(2.25)
    expect(leerHoras(' 3 ')).toBe(3)
    expect(leerHoras('1,333')).toBe(1.33)
  })
  it('rechaza lo que no es una cantidad válida de horas', () => {
    for (const v of ['', '0', '-1', '25', 'abc', '2,5,1', '1e2']) expect(leerHoras(v), v).toBeNull()
  })
})
