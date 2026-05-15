import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { assetsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Asset {
  id: string
  name?: string
  status?: string
  [extra: string]: unknown
}

export type AssetListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

export function useAssets(params: AssetListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['alm-assets', params],
    queryFn: () => assetsApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAllAssets(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['alm-assets'],
    queryFn: () => assetsApi.list().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAsset(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['alm-assets', id],
    queryFn: () => assetsApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateAsset(): UseMutationResult<unknown, unknown, Partial<Asset>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Asset>) => assetsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-assets'] }),
  })
}

export function useUpdateAsset(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Asset>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Asset>>) => assetsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-assets'] }),
  })
}

export function useDeleteAsset(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => assetsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-assets'] }),
  })
}
