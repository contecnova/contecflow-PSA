import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { licensesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useLicenses(params = {}) {
  return useQuery({
    queryKey: ['alm-licenses', params],
    queryFn: () => licensesApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAllLicenses() {
  return useQuery({
    queryKey: ['alm-licenses'],
    queryFn: () => licensesApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useLicense(id) {
  return useQuery({
    queryKey: ['alm-licenses', id],
    queryFn: () => licensesApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateLicense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => licensesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
  })
}

export function useUpdateLicense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => licensesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
  })
}

export function useAssignLicense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => licensesApi.assign(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
  })
}

export function useDeleteLicense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => licensesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alm-licenses'] }),
  })
}
