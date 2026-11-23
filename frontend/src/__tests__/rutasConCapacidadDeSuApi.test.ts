// Auditoría 22-11-2026 (M16), 23-11-2026: cada ruta pide la capacidad que exige
// la API que carga (antes /bpm pedía recursos.prevision, /agent-dashboard
// cmdb.ver con una API de cmdb.gestionar y /portfolio/intake colaboracion.ver).
import { describe, it, expect } from 'vitest'
import { rutaDeclarada } from '../permisos/navegacion'

describe('capacidad por ruta = la de su API', () => {
  it.each([
    ['/bpm', 'bpm.usar'],
    ['/agent-dashboard', 'cmdb.gestionar'],
    ['/portfolio/intake', 'cartera.usar'],
    ['/reports', 'colaboracion.ver'],
  ])('%s → %s', (ruta, capacidad) => {
    expect(rutaDeclarada(ruta)?.capacidad).toBe(capacidad)
  })
})
