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
 * Las mutaciones no pasan por aquí: cada una gestiona su `onError`.
 */

declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: Record<string, unknown> & {
      /** `false` cuando la página ya muestra el error de la query. */
      errorToast?: boolean
    }
  }
}

export type QueryErrorListener = (error: unknown) => void

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
  listeners.forEach(listener => listener(error))
}
