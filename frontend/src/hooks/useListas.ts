/**
 * Listas compartidas de proyectos y de personas (auditoría 22-11-2026, A8 del 04
 * y M5 del 04b).
 *
 * Antes cada pantalla pedía `['projects']` o `['users']` con su propia función
 * (respuesta cruda, filtrada por estado, con `.catch(() => [])`…) y react-query
 * compartía la caché: una pantalla recibía la lista con la forma o el filtro de
 * otra, o un `[]` guardado por un error tragado. Ahora la clave lleva los
 * parámetros (`queryKeys.*.list(params)`) y la función es siempre la misma, así
 * que misma clave = mismos datos. La invalidación por prefijo (`['projects']`,
 * `['users']`) sigue alcanzando a estas listas.
 */
import { useQuery } from '@tanstack/react-query'
import { projectsApi, usersApi } from '../services/api'
import type { ProjectListItem, ProjectListParams } from '../services/api/projects'
import type { UserListItem, UserListParams } from '../services/api/users'
import { queryKeys } from '../constants/queryKeys'

const comoLista = <T,>(datos: unknown): T[] => {
  if (Array.isArray(datos)) return datos as T[]
  const items = (datos as { items?: unknown } | null | undefined)?.items
  return Array.isArray(items) ? (items as T[]) : []
}

/** Proyectos visibles (todas las páginas). `params` entra en la clave. */
export function useListaDeProyectos(params?: ProjectListParams, opciones?: { enabled?: boolean }) {
  return useQuery<ProjectListItem[]>({
    queryKey: queryKeys.projects.list(params as Record<string, unknown> | undefined),
    queryFn: () => projectsApi.list(params).then((r) => comoLista<ProjectListItem>(r.data)),
    enabled: opciones?.enabled ?? true,
  })
}

/** Personas de la empresa (todas las páginas). `params` entra en la clave. */
export function useListaDeUsuarios(params?: UserListParams, opciones?: { enabled?: boolean }) {
  return useQuery<UserListItem[]>({
    queryKey: queryKeys.users.list(params as Record<string, unknown> | undefined),
    queryFn: () => usersApi.list(params).then((r) => comoLista<UserListItem>(r.data)),
    enabled: opciones?.enabled ?? true,
  })
}
