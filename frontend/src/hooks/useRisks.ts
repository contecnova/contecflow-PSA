import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { risksApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Risk {
  id: string
  title?: string
  probability?: number
  impact?: number
  status?: string
  [extra: string]: unknown
}

export type RiskListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

export function useRisks(projectId: string | undefined, params: RiskListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['risks', projectId, params],
    queryFn: () => risksApi.list(projectId, params).then((r: { data: unknown }) => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useAllRisks(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['risks'],
    queryFn: () => risksApi.list().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useRisk(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['risk-detail', id],
    queryFn: () => risksApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateRisk(): UseMutationResult<unknown, unknown, Partial<Risk>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Risk>) => risksApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}

export function useUpdateRisk(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Risk>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Risk>>) => risksApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}

export function useDeleteRisk(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => risksApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}
