import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { vendorsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useVendors(params = {}) {
  return useQuery({
    queryKey: ['alm-vendors', params],
    queryFn: () => vendorsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAllVendors() {
  return useQuery({
    queryKey: ['alm-vendors'],
    queryFn: () => vendorsApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateVendor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => vendorsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
  })
}

export function useUpdateVendor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => vendorsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
  })
}

export function useDeleteVendor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => vendorsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-vendors'] }),
  })
}
