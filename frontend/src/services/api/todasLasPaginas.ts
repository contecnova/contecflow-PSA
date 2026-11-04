/**
 * Pide todas las páginas de un listado paginado y devuelve los elementos juntos.
 *
 * Auditoría 2026-11: los selectores de proyecto, persona y tarea llamaban a
 * `/projects`, `/users` o `/tasks` sin `page` y la API devuelve 50 por defecto:
 * con más, los demás no aparecían nunca y nada avisaba. Si quien llama pide una
 * página concreta (`page`), se respeta y se hace una sola petición.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'

// El máximo que aceptan todos estos listados (`/projects` admite 200).
const TAMANO_DE_PAGINA = 200

export async function todasLasPaginas<T>(path: string, params?: Record<string, unknown>): Promise<AxiosResponse<T[]>> {
  if (params && params.page != null) return api.get(path, { params })
  const tamano = TAMANO_DE_PAGINA
  // `limit` es un alias viejo de `page_size` en algunos listados: con él la
  // página llegaría más corta y el recorrido se pararía antes de tiempo.
  const { limit: _limit, page_size: _ps, ...resto } = params || {}
  let pagina = 1
  let primera: AxiosResponse<T[]> | null = null
  let items: T[] = []
  for (;;) {
    const res = await api.get(path, { params: { ...resto, page: pagina, page_size: tamano } }) as AxiosResponse<T[]> & { meta?: { total?: number } }
    if (!primera) primera = res
    const body = res.data as unknown
    const lote: T[] = Array.isArray(body) ? body : ((body as { items?: T[] })?.items ?? [])
    items = items.concat(lote)
    const total = res.meta?.total
    if (lote.length < tamano || (typeof total === 'number' && items.length >= total)) break
    pagina += 1
  }
  const meta = { ...((primera as { meta?: object }).meta || {}), total: items.length, page: 1, page_size: items.length }
  return Object.assign({}, primera, { data: items, meta })
}
