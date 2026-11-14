import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import { assetsApi } from '../services/api'
import type { AlmActivo, AlmActivoDetalle } from '../services/api/tipos-alm'

const STALE = 2 * 60 * 1000

/** Lo que manda el backend (services/api/tipos-alm). */
export type Asset = AlmActivo

export type AssetListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

export function useAssets(params: AssetListParams = {}): UseQueryResult<AlmActivo[]> {
  return useQuery({
    queryKey: ['alm-assets', params],
    queryFn: () => assetsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAllAssets(): UseQueryResult<AlmActivo[]> {
  return useQuery({
    queryKey: ['alm-assets'],
    queryFn: () => assetsApi.list({}).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAsset(id: string | undefined): UseQueryResult<AlmActivoDetalle> {
  return useQuery({
    queryKey: ['alm-assets', id],
    queryFn: () => assetsApi.get(id).then(r => r.data),
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
