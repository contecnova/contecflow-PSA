import { traducirSinHook } from '../i18n/traducirSinHook'

/**
 * Errores de validación del servidor, campo a campo (17-11-2026).
 *
 * Un 422 de validación llega como `{detail, code: 'validacion', params:
 * {errores: [{campo, tipo, origen?, min?, max?, permitidos?}]}}`
 * (`app/core/validacion.py`). `tipo` es una lista cerrada que se traduce con
 * `validacion.<tipo>` (operador es/en/zh en `i18n/langs`, portal en sus 8
 * idiomas en `i18n/portal`). Los formularios lo pintan junto a cada campo con
 * `useErroresDeCampo` (kit); el resto de pantallas, en el aviso de error
 * (`extractErr`), ya traducido.
 */
export interface ErrorDeCampo {
  /** Ruta del dato sin el origen (`nombre`, `lineas.0.importe`); '' si es del cuerpo entero. */
  campo: string
  tipo: string
  origen?: string
  min?: number | string
  max?: number | string
  permitidos?: string[]
}

type Traducir = (clave: string, params?: Record<string, string | number>) => string

export const CODIGO_DE_VALIDACION = 'validacion'

/** Los errores por campo de un 422 de validación, o null si `e` no es uno. */
export function erroresDeValidacion(e: unknown): ErrorDeCampo[] | null {
  const data = (e as { response?: { data?: { code?: unknown; params?: { errores?: unknown } } } } | null | undefined)?.response?.data
  if (!data || data.code !== CODIGO_DE_VALIDACION) return null
  const errores = data.params?.errores
  if (!Array.isArray(errores)) return []
  return errores.filter((x): x is ErrorDeCampo => !!x && typeof x === 'object' && typeof (x as ErrorDeCampo).tipo === 'string')
    .map(x => ({ ...x, campo: typeof x.campo === 'string' ? x.campo : '' }))
}

function rellenar(texto: string, params: Record<string, string | number>): string {
  return texto.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m))
}

/** Texto de un error de campo en el idioma de `t` (operador o portal). */
export function textoDeErrorDeCampo(t: Traducir, err: ErrorDeCampo): string {
  const params: Record<string, string | number> = {}
  if (err.min != null) params.min = err.min
  if (err.max != null) params.max = err.max
  if (err.permitidos?.length) params.permitidos = err.permitidos.join(', ')
  const clave = `validacion.${err.tipo}`
  let texto = t(clave, params)
  if (!texto || texto === clave) texto = t('validacion.no_valido', params)
  // El traductor de respaldo no interpola.
  return rellenar(texto, params)
}

/**
 * `{campo: texto}` de un 422 de validación. Cada error queda bajo su ruta
 * completa (`lineas.0.importe`) y, si no choca, también bajo su último tramo
 * (`importe`), para los formularios planos.
 */
export function erroresPorCampo(e: unknown, t: Traducir): Record<string, string> | null {
  const errores = erroresDeValidacion(e)
  if (!errores) return null
  const salida: Record<string, string> = {}
  for (const err of errores) {
    const texto = textoDeErrorDeCampo(t, err)
    if (!(err.campo in salida)) salida[err.campo] = texto
    const ultimo = err.campo.split('.').filter(p => !/^\d+$/.test(p)).pop()
    if (ultimo && !(ultimo in salida)) salida[ultimo] = texto
  }
  return salida
}

/** Resumen para un aviso: «Revisa los datos: nombre: Obligatorio · …». */
export function resumenDeValidacion(t: Traducir, errores: ErrorDeCampo[]): string {
  const partes = errores.slice(0, 6).map(err => {
    const texto = textoDeErrorDeCampo(t, err)
    return err.campo ? `${err.campo}: ${texto}` : texto
  })
  const cabecera = t('validacion.resumen')
  const titulo = cabecera && cabecera !== 'validacion.resumen' ? cabecera : 'Revisa los datos'
  return partes.length ? `${titulo}: ${partes.join(' · ')}` : titulo
}

/** Resumen en el idioma de operador guardado (sin contexto de React: `extractErr`). */
export function resumenDeValidacionSinHook(e: unknown): string | null {
  const errores = erroresDeValidacion(e)
  if (!errores) return null
  return resumenDeValidacion((clave, params) => {
    const texto = traducirSinHook(clave)
    return params ? rellenar(texto, params) : texto
  }, errores)
}
