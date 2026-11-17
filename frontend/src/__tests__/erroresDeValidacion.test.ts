// Errores de validación del servidor por campo (17-11-2026).
import { describe, it, expect } from 'vitest'
import { erroresDeValidacion, erroresPorCampo, resumenDeValidacion, textoDeErrorDeCampo } from '../utils/erroresDeValidacion'

const TEXTOS: Record<string, string> = {
  'validacion.obligatorio': 'Obligatorio',
  'validacion.longitud_maxima': 'Como mucho {max} caracteres',
  'validacion.no_valido': 'No válido',
  'validacion.resumen': 'Revisa los datos',
}
const t = (k: string) => TEXTOS[k] ?? k

const error422 = (errores: unknown[]) => ({
  response: { status: 422, data: { detail: 'Revisa los datos', code: 'validacion', params: { errores } } },
})

describe('errores de validación', () => {
  it('solo reconoce el código validacion', () => {
    expect(erroresDeValidacion({ response: { data: { detail: 'x', code: 'otro' } } })).toBeNull()
    expect(erroresDeValidacion(new Error('x'))).toBeNull()
    expect(erroresDeValidacion(error422([{ campo: 'name', tipo: 'obligatorio' }]))).toHaveLength(1)
  })

  it('traduce por campo, con parámetros y también por el último tramo de la ruta', () => {
    const e = error422([
      { campo: 'name', tipo: 'obligatorio', origen: 'body' },
      { campo: 'lineas.0.descripcion', tipo: 'longitud_maxima', max: 200 },
    ])
    expect(erroresPorCampo(e, t)).toEqual({
      name: 'Obligatorio',
      'lineas.0.descripcion': 'Como mucho 200 caracteres',
      descripcion: 'Como mucho 200 caracteres',
    })
  })

  it('un tipo desconocido cae en «no válido»', () => {
    expect(textoDeErrorDeCampo(t, { campo: 'x', tipo: 'nuevo_tipo' })).toBe('No válido')
  })

  it('resume para el aviso', () => {
    expect(resumenDeValidacion(t, [{ campo: 'name', tipo: 'obligatorio' }])).toBe('Revisa los datos: name: Obligatorio')
  })
})
