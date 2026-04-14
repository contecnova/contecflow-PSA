import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { okrsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useOKRs(params = {}) {
  return useQuery({
    queryKey: ['okrs', params],
    queryFn: () => okrsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useOKR(id) {
  return useQuery({
    queryKey: ['okrs', id],
    queryFn: () => okrsApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateOKR() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => okrsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
  })
}

export function useUpdateOKR() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => okrsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
  })
}

export function useUpdateKeyResult() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, krid, data }) => okrsApi.updateKR(id, krid, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
  })
}

export function useDeleteOKR() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => okrsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
  })
}
