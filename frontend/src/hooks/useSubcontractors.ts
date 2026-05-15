import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { subcontractorsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Subcontractor {
  id: string
  name?: string
  [extra: string]: unknown
}

export type SubcontractorListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

export function useSubcontractors(params: SubcontractorListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['subcontractors', params],
    queryFn: () => subcontractorsApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAllSubcontractors(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['subcontractors'],
    queryFn: () => subcontractorsApi.list().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useCreateSubcontractor(): UseMutationResult<unknown, unknown, Partial<Subcontractor>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Subcontractor>) => subcontractorsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subcontractors'] }),
  })
}

export function useUpdateSubcontractor(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Subcontractor>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Subcontractor>>) => subcontractorsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subcontractors'] }),
  })
}

export function useDeleteSubcontractor(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => subcontractorsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subcontractors'] }),
  })
}
