import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { okrsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface OKR {
  id: string
  objective?: string
  status?: string
  progress?: number
  [extra: string]: unknown
}

export type OKRListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type UpdateKRArgs = { id: string; krid: string; data: Record<string, unknown> }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useOKRs(params: OKRListParams = {}): UseQueryResult<OKR[]> {
  return useQuery<OKR[]>({
    queryKey: ['okrs', params],
    queryFn: () => okrsApi.list(params).then((r: { data?: { items?: OKR[] } | OKR[] | null }) => unwrapList<OKR>(r)),
    staleTime: STALE,
  })
}

export function useOKR(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['okrs', id],
    queryFn: () => okrsApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
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

export function useUpdateKeyResult(): UseMutationResult<unknown, unknown, UpdateKRArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, krid, data }: UpdateKRArgs) => okrsApi.updateKR(id, krid, data),
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
