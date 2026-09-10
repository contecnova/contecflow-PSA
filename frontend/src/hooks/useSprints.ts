import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { sprintsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Sprint {
  id: string
  project_id?: string
  name?: string
  status?: string
  [extra: string]: unknown
}

export type SprintListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useSprints(projectId: string | undefined, params: SprintListParams = {}): UseQueryResult<Sprint[]> {
  return useQuery<Sprint[]>({
    queryKey: ['sprints', projectId, params],
    queryFn: () => sprintsApi.list(projectId, params).then((r: { data?: { items?: Sprint[] } | Sprint[] | null }) => unwrapList<Sprint>(r)),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useAllSprints(params: SprintListParams = {}): UseQueryResult<Sprint[]> {
  return useQuery<Sprint[]>({
    queryKey: ['sprints', params],
    queryFn: () => sprintsApi.list(undefined, params).then((r: { data?: { items?: Sprint[] } | Sprint[] | null }) => unwrapList<Sprint>(r)),
    staleTime: STALE,
  })
}

