import { extractErr } from './helpers'
import type { TraductorDeCodigos } from '../components/ui/useTextoUi'

/**
 * Mensaje de un error del servidor para quien lo ve (16-11-2026).
 *
 * Los errores que ve el cliente del portal llegan con un código estable y sus
 * datos (`{detail, code, params}`, `app/core/codigos_de_error.py`): si el
 * traductor tiene ese código, el texto sale en su idioma; si no, el `detail`
 * (castellano, lo que ya veía el operador) y, sin él, `fallback`.
 */
export function mensajeDeError(e: unknown, traducirCodigo: TraductorDeCodigos | null | undefined, fallback: string): string {
  const data = (e as { response?: { data?: { code?: unknown; params?: unknown } } } | null | undefined)?.response?.data
  const codigo = data?.code
  if (traducirCodigo && typeof codigo === 'string' && codigo) {
    const params = data?.params && typeof data.params === 'object' ? data.params as Record<string, unknown> : null
    const texto = traducirCodigo(codigo, params)
    if (texto) return texto
  }
  return extractErr(e, fallback)
}
