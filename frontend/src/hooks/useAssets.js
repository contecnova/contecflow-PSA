import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { assetsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useAssets(params = {}) {
  return useQuery({
    queryKey: ['alm-assets', params],
    queryFn: () => assetsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAllAssets() {
  return useQuery({
    queryKey: ['alm-assets'],
    queryFn: () => assetsApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useAsset(id) {
  return useQuery({
    queryKey: ['alm-assets', id],
    queryFn: () => assetsApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => assetsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-assets'] }),
  })
}

export function useUpdateAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => assetsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-assets'] }),
  })
}

export function useDeleteAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => assetsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-assets'] }),
  })
}
