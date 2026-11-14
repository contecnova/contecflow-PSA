import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import { okrsApi } from '../services/api'

const STALE = 2 * 60 * 1000

// okr_service.serialize_objective: el objetivo tiene `title` (no `objective`).
import type { Objetivo } from '../services/api/tipos-proyectos'
export type OKR = Objetivo

export type OKRListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type UpdateKRArgs = { id: string; krid: string; data: Record<string, unknown> }

export function useOKRs(params: OKRListParams = {}): UseQueryResult<OKR[]> {
  return useQuery<OKR[]>({
    queryKey: ['okrs', params],
    queryFn: () => okrsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateOKR(): UseMutationResult<unknown, unknown, Partial<OKR>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<OKR>) => okrsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
  })
}

export function useUpdateOKR(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<OKR>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<OKR>>) => okrsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
  })
}

export function useDeleteOKR(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => okrsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
  })
}
