import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { vendorsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Vendor {
  id: string
  name?: string
  [extra: string]: unknown
}

export type VendorListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

export function useVendors(params: VendorListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['alm-vendors', params],
    queryFn: () => vendorsApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAllVendors(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['alm-vendors'],
    queryFn: () => vendorsApi.list({}).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useCreateVendor(): UseMutationResult<unknown, unknown, Partial<Vendor>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Vendor>) => vendorsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
  })
}

export function useUpdateVendor(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Vendor>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Vendor>>) => vendorsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
  })
}

export function useDeleteVendor(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => vendorsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
  })
}
