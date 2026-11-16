// Revisión BPM 2026-11-16: textos construidos con códigos del backend.
import { describe, it, expect } from 'vitest'
import { leerVariables, textoErrorDeInstancia, textoProblema, textoRol, textoTipo } from './textos'

// Como `t` de verdad: devuelve la clave cuando no hay texto.
const DICC: Record<string, string> = {
  'bpm.problema_no_outgoing': '«{element}» no tiene salida',
  'bpm.tipo_userTask': 'Tarea de usuario',
  'bpm.rol_cualquiera': 'Cualquiera',
}
const t = (k: string, p?: Record<string, unknown>) =>
  (DICC[k] ?? k).replace(/\{(\w+)\}/g, (_m, n: string) => String(p?.[n] ?? ''))

describe('textos de BPM', () => {
  it('traduce un problema por su código y, sin texto, usa el del backend', () => {
    expect(textoProblema(t, { code: 'no_outgoing', element: 'Revisar', extra: null, detail: 'x' })).toBe('«Revisar» no tiene salida')
    expect(textoProblema(t, { code: 'nuevo', element: null, extra: null, detail: 'texto del backend' })).toBe('texto del backend')
  })

  it('el motivo del fallo cae al texto del backend si no hay código o texto', () => {
    expect(textoErrorDeInstancia(t, { error: null, error_code: null, error_params: null })).toBeNull()
    expect(textoErrorDeInstancia(t, { error: 'antiguo', error_code: null, error_params: null })).toBe('antiguo')
    expect(textoErrorDeInstancia(t, { error: 'motivo', error_code: 'desconocido', error_params: null })).toBe('motivo')
  })

  it('tipo y rol: traducidos, o el código tal cual; sin rol, «cualquiera»', () => {
    expect(textoTipo(t, 'userTask')).toBe('Tarea de usuario')
    expect(textoTipo(t, 'otroTipo')).toBe('otroTipo')
    expect(textoRol(t, null)).toBe('Cualquiera')
    expect(textoRol(t, 'hr')).toBe('hr')
  })

  it('lee variables con su tipo', () => {
    expect(leerVariables('a=true\nb=12\nc=hola\n=x\nd=')).toEqual({ a: true, b: 12, c: 'hola', d: '' })
  })
})
