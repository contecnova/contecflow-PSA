import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { licensesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface License {
  id: string
  product?: string
  status?: string
  [extra: string]: unknown
}

export type LicenseListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type AssignArgs = { id: string; data: Record<string, unknown> }

export function useLicenses(params: LicenseListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['alm-licenses', params],
    queryFn: () => licensesApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAllLicenses(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['alm-licenses'],
    queryFn: () => licensesApi.list().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useLicense(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['alm-licenses', id],
    queryFn: () => licensesApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateLicense(): UseMutationResult<unknown, unknown, Partial<License>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<License>) => licensesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
  })
}

export function useUpdateLicense(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<License>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<License>>) => licensesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
  })
}

export function useAssignLicense(): UseMutationResult<unknown, unknown, AssignArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: AssignArgs) => licensesApi.assign(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
  })
}

export function useDeleteLicense(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => licensesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
  })
}
