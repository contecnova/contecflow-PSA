// Auditoría 22-11-2026 (M1 del 04): volver al enlace profundo tras el login sin abrir
// una redirección a otro dominio.
import { beforeEach, describe, expect, it } from 'vitest'
import { esRutaInterna, guardarDestinoTrasLogin, tomarDestinoTrasLogin } from './destinoTrasLogin'

describe('destinoTrasLogin', () => {
  beforeEach(() => sessionStorage.clear())

  it('solo admite rutas internas', () => {
    expect(esRutaInterna('/projects/123?tab=uat#x')).toBe(true)
    expect(esRutaInterna('//evil.example')).toBe(false)
    expect(esRutaInterna('/\\evil.example')).toBe(false)
    expect(esRutaInterna('https://evil.example')).toBe(false)
    expect(esRutaInterna('/login?next=/x')).toBe(false)
  })

  it('guarda, devuelve una vez y borra', () => {
    guardarDestinoTrasLogin('/projects/123')
    expect(tomarDestinoTrasLogin()).toBe('/projects/123')
    expect(tomarDestinoTrasLogin()).toBeNull()
  })

  it('ignora destinos externos guardados a mano', () => {
    sessionStorage.setItem('cf_volver_a', '//evil.example')
    expect(tomarDestinoTrasLogin()).toBeNull()
  })
})
