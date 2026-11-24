// Atajos «G + letra» (23-11-2026): la ventana de atajos los anunciaba y nadie
// los atendía. Lógica pura de components/layout/atajosDeTeclado.ts.
import { describe, expect, it } from 'vitest'
import { ATAJOS_IR, ESPERA_SEGUNDA_TECLA_MS, crearSecuenciaIr, esCampoDeTexto } from '../components/layout/atajosDeTeclado'

describe('secuencia G + letra', () => {
  it('G y luego T, P, I o S llevan a su página', () => {
    for (const [tecla, ruta] of Object.entries(ATAJOS_IR)) {
      const pulsar = crearSecuenciaIr(() => 1000)
      expect(pulsar('g')).toEqual({ tipo: 'espera' })
      expect(pulsar(tecla)).toEqual({ tipo: 'ir', ruta })
    }
    expect(ATAJOS_IR).toEqual({ t: '/tasks', p: '/projects', i: '/imputar', s: '/service-desk' })
  })

  it('acepta mayúsculas (Bloq Mayús o Mayús)', () => {
    const pulsar = crearSecuenciaIr(() => 1)
    pulsar('G')
    expect(pulsar('T')).toEqual({ tipo: 'ir', ruta: '/tasks' })
  })

  it('sin G delante, la letra sola no hace nada', () => {
    const pulsar = crearSecuenciaIr(() => 1000)
    expect(pulsar('t')).toBeNull()
  })

  it('si la segunda tecla llega tarde, no navega', () => {
    let ahora = 1000
    const pulsar = crearSecuenciaIr(() => ahora)
    pulsar('g')
    ahora += ESPERA_SEGUNDA_TECLA_MS + 1
    expect(pulsar('t')).toBeNull()
  })

  it('una letra que no es atajo cancela la secuencia', () => {
    const pulsar = crearSecuenciaIr(() => 1000)
    pulsar('g')
    expect(pulsar('x')).toBeNull()
    expect(pulsar('t')).toBeNull()
  })
})

describe('campos de texto', () => {
  it('en inputs, textareas, selects y contenteditable no hay atajos', () => {
    expect(esCampoDeTexto(document.createElement('input'))).toBe(true)
    expect(esCampoDeTexto(document.createElement('textarea'))).toBe(true)
    expect(esCampoDeTexto(document.createElement('select'))).toBe(true)
    const editable = document.createElement('div')
    editable.contentEditable = 'true'
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    expect(esCampoDeTexto(editable)).toBe(true)
    expect(esCampoDeTexto(document.createElement('div'))).toBe(false)
    expect(esCampoDeTexto(null)).toBe(false)
  })
})
