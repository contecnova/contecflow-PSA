/**
 * Puente entre el `QueryCache` de TanStack (fuera de React) y `ToastProvider`.
 *
 * Sin él, una query que falla deja `data` en su valor por defecto (`[]`) y la
 * página se ve como una lista vacía. `main.tsx` llama a `reportQueryError` desde
 * `QueryCache.onError`; `ToastProvider` se suscribe y muestra el aviso.
 *
 * No se avisa cuando:
 *   - la query lleva `meta: { errorToast: false }` (la página ya pinta el error);
 *   - es un 401 (el interceptor refresca o emite `auth:session-expired`);
 *   - es un 429 (AuthContext ya avisa con `api:rate-limited`);
 *   - es una cancelación.
 * Mutaciones (auditoría 22-11-2026, M1 del 04b): `MutationCache.onError`
 * (`main.tsx`) llama a `reportMutationError` solo si la mutación NO trae su
 * propio `onError` y no lleva `meta: { errorToast: false }`. Así ninguna
 * escritura falla en silencio y las que ya avisan no avisan dos veces.
 */

declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: Record<string, unknown> & {
      /** `false` cuando la página ya muestra el error de la query. */
      errorToast?: boolean
    }
    mutationMeta: Record<string, unknown> & {
      /** `false` cuando la pantalla ya avisa del error de la mutación por su cuenta. */
      errorToast?: boolean
    }
  }
}

/** `consulta`: no se pudo cargar; `escritura`: no se pudo guardar/borrar. */
export type TipoDeError = 'consulta' | 'escritura'
export type QueryErrorListener = (error: unknown, tipo: TipoDeError) => void

const listeners = new Set<QueryErrorListener>()

export function subscribeQueryErrors(listener: QueryErrorListener): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

const SILENT_STATUS = new Set([401, 429])

export function shouldToastQueryError(error: unknown, meta?: Record<string, unknown>): boolean {
  if (meta?.errorToast === false) return false
  const e = error as { name?: string; code?: string; response?: { status?: number } } | null | undefined
  if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED' || e?.name === 'AbortError') return false
  const status = e?.response?.status
  if (status !== undefined && SILENT_STATUS.has(status)) return false
  return true
}

export function reportQueryError(error: unknown, meta?: Record<string, unknown>): void {
  if (!shouldToastQueryError(error, meta)) return
  listeners.forEach(listener => listener(error, 'consulta'))
}

/** Error de una mutación sin `onError` propio (ver cabecera). */
export function reportMutationError(error: unknown, meta?: Record<string, unknown>): void {
  if (!shouldToastQueryError(error, meta)) return
  listeners.forEach(listener => listener(error, 'escritura'))
}
