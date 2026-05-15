import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { deliverablesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Deliverable {
  id: string
  title?: string
  status?: string
  [extra: string]: unknown
}

export type UpdateArgs<T> = { id: string; data: T }

export function useDeliverables(projectId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['deliverables', projectId],
    queryFn: () => deliverablesApi.list(projectId).then((r: { data: unknown }) => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useDeliverableOverview(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['deliverables-overview'],
    queryFn: () => deliverablesApi.overview().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useCreateDeliverable(): UseMutationResult<unknown, unknown, Partial<Deliverable>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Deliverable>) => deliverablesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deliverables'] }),
  })
}

export function useUpdateDeliverable(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Deliverable>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Deliverable>>) => deliverablesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deliverables'] }),
  })
}

export function useDeleteDeliverable(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deliverablesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deliverables'] }),
  })
}
