import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
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

export function useSprint(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sprints', id],
    queryFn: () => sprintsApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateSprint(): UseMutationResult<unknown, unknown, Partial<Sprint>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Sprint>) => sprintsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprints'] }),
  })
}

export function useUpdateSprint(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Sprint>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Sprint>>) => sprintsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprints'] }),
  })
}

export function useDeleteSprint(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => sprintsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprints'] }),
  })
}

export function useStartSprint(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => sprintsApi.start(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprints'] }),
  })
}

export function useCompleteSprint(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => sprintsApi.complete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprints'] }),
  })
}

export function useSprintBurndown(sprintId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sprint-burndown', sprintId],
    queryFn: () => sprintsApi.burndown(sprintId).then((r: { data: unknown }) => r.data),
    enabled: !!sprintId,
    staleTime: STALE,
  })
}

export function useSprintVelocity(projectId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sprint-velocity', projectId],
    queryFn: () => sprintsApi.velocity(projectId).then((r: { data: unknown }) => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}
