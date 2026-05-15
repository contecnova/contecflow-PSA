import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { epicsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Epic {
  id: string
  title?: string
  status?: string
  [extra: string]: unknown
}

export type UpdateArgs<T> = { id: string; data: T }

export function useEpics(projectId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['epics', projectId],
    queryFn: () => epicsApi.list(projectId).then((r: { data: unknown }) => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useAllEpics(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['epics'],
    queryFn: () => epicsApi.list().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useCreateEpic(): UseMutationResult<unknown, unknown, Partial<Epic>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Epic>) => epicsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}

export function useUpdateEpic(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Epic>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Epic>>) => epicsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}

export function useDeleteEpic(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => epicsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}
