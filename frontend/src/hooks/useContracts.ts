import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { contractsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Contract {
  id: string
  client_id?: string
  name?: string
  status?: string
  [extra: string]: unknown
}

export type ContractListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useContracts(params: ContractListParams = {}): UseQueryResult<Contract[]> {
  return useQuery<Contract[]>({
    queryKey: ['contracts', params],
    queryFn: () => contractsApi.list(params).then((r: { data?: { items?: Contract[] } | Contract[] | null }) => unwrapList<Contract>(r)),
    staleTime: STALE,
  })
}

export function useAllContracts(): UseQueryResult<Contract[]> {
  return useQuery<Contract[]>({
    queryKey: ['contracts'],
    queryFn: () => contractsApi.list({}).then((r: { data?: { items?: Contract[] } | Contract[] | null }) => unwrapList<Contract>(r)),
    staleTime: STALE,
  })
}

export function useContract(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['contracts', id],
    queryFn: () => contractsApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateContract(): UseMutationResult<unknown, unknown, Partial<Contract>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Contract>) => contractsApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contracts'] })
      qc.invalidateQueries({ queryKey: ['clients'] })
    },
  })
}

export function useUpdateContract(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Contract>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Contract>>) => contractsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
  })
}

export function useDeleteContract(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => contractsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
  })
}
