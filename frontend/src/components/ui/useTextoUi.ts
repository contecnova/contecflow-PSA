import { useAppLang } from '../../i18n/AppLangContext'
import { traducirSinHook } from '../../i18n/traducirSinHook'

type Traducir = (clave: string, params?: Record<string, string | number>) => string

/**
 * `t()` para las primitivas del kit (Spinner, Modal, DataTable, ColVisibility…).
 *
 * Se pintan en todas partes, también en tests y árboles montados sin
 * `AppLangProvider`; `useAppLang()` lanza ahí a propósito. Con proveedor se usa
 * su `t` (reacciona al cambio de idioma); sin él, `traducirSinHook`, que lee el
 * idioma guardado y los diccionarios ya cargados.
 *
 * Se pasa por `useAppLang()` (y no por `useContext(AppLangContext)`) para que
 * los tests que simulan ese módulo con `vi.mock` sigan sirviendo. El orden de
 * hooks no cambia: `useAppLang` siempre llama a `useContext` una vez y solo
 * después decide si lanza.
 */
export function useTextoUi(): Traducir {
  try {
    const t = useAppLang()?.t
    return typeof t === 'function' ? t : traducirSinHook
  } catch {
    return traducirSinHook
  }
}
