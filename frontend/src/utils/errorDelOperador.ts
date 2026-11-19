import { APP_TRANSLATIONS } from '../i18n/appTranslations.ts'
import { traducirSinHook } from '../i18n/traducirSinHook'

/**
 * Errores del servidor con código para el operador (17-11-2026).
 *
 * Los códigos de `MENSAJES_DEL_OPERADOR` (`app/core/codigos_de_error.py`)
 * tienen su texto en `err_srv.<código>` de los diccionarios de operador
 * (`i18n/langs/{es,en,zh}.mjs`). Si el error trae uno de esos códigos, sale en
 * el idioma del operador con sus `params` (`{nombre}`); si no, null y quien
 * llama enseña el `detail` de siempre. Lo usa `extractErr`, así que cualquier
 * pantalla de operador que ya pinte `extractErr(e)` lo traduce sin cambios.
 */
export function textoDeErrorDelOperador(e: unknown): string | null {
  const data = (e as { response?: { data?: { code?: unknown; params?: unknown } } } | null | undefined)?.response?.data
  const codigo = data?.code
  if (typeof codigo !== 'string' || !/^[a-z0-9_]+$/.test(codigo)) return null
  // Solo los códigos del catálogo del operador (el castellano siempre está cargado).
  const catalogo = APP_TRANSLATIONS.es?.err_srv as Record<string, unknown> | undefined
  if (!catalogo || typeof catalogo[codigo] !== 'string') return null
  const texto = traducirSinHook(`err_srv.${codigo}`)
  const params = data?.params && typeof data.params === 'object' ? data.params as Record<string, unknown> : {}
  return texto.replace(/\{(\w+)\}/g, (m, k: string) => {
    const v = params[k]
    // 19-11-2026: `que` es una entidad del catálogo (`no_encontrado`, `que=epica`):
    // se traduce con `err_srv.que_<entidad>` (`QUE` en codigos_de_error.py).
    if (k === 'que' && typeof v === 'string' && typeof catalogo[`que_${v}`] === 'string') {
      return traducirSinHook(`err_srv.que_${v}`)
    }
    return typeof v === 'string' || typeof v === 'number' ? String(v) : m
  })
}
