/**
 * Shape-normalisation helpers shared by all api/* modules.
 */
import type { AxiosResponse } from 'axios'

/**
 * Normalises any listing response to a guaranteed array.
 *
 * Supports the three shapes the backend uses indistinctly:
 *   1) raw array: `[a, b, c]`
 *   2) paginated: `{ items: [...], count?, total? }`
 *   3) alternative key: `{ rows | results | data | tickets | sessions: [...] }`
 *
 * Never returns null/undefined — always an array.
 */
export function unwrapList<T = unknown>(response: AxiosResponse<unknown> | unknown, key?: string): T[] {
  const raw = (response as { data?: unknown })?.data ?? response
  if (Array.isArray(raw)) return raw as T[]
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>
    if (key && Array.isArray(obj[key])) return obj[key] as T[]
    for (const k of ['items', 'results', 'rows', 'data', 'list']) {
      if (Array.isArray(obj[k])) return obj[k] as T[]
    }
  }
  return []
}

/**
 * Returns the response data verbatim — useful when the caller needs to
 * inspect pagination metadata (`{items, count}` preserves `count`).
 */
export function unwrapData<T = unknown>(response: AxiosResponse<T> | T | null | undefined): T | null {
  const r = response as { data?: T } | T | null | undefined
  if (r && typeof r === 'object' && 'data' in (r as object)) {
    return (r as { data?: T }).data ?? null
  }
  return ((r ?? null) as T | null)
}

/**
 * Normalise a Pydantic v2 / FastAPI error detail to a plain string.
 * `detail` may be an array of {type,loc,msg,input,url} objects or a plain string.
 */
export function apiErrorMsg(e: unknown, fallback = 'Error'): string {
  const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
  const raw = err?.response?.data?.detail
  if (Array.isArray(raw)) {
    return raw.map((d) => (d as { msg?: string })?.msg ?? '').filter(Boolean).join(', ')
  }
  if (typeof raw === 'string') return raw
  return err?.message ?? fallback
}
