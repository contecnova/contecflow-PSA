import { describe, expect, it } from 'vitest'
import { px } from './estilos'

describe('px', () => {
  it('añade px a los números y respeta las cadenas', () => {
    expect(px(24)).toBe('24px')
    expect(px(0)).toBe('0px')
    expect(px(-4)).toBe('-4px')
    expect(px('50%')).toBe('50%')
    expect(px('calc(100% - 8px)')).toBe('calc(100% - 8px)')
  })
  it('devuelve undefined si no hay valor (React no emite la propiedad)', () => {
    expect(px(undefined)).toBeUndefined()
    expect(px(null)).toBeUndefined()
  })
})
