import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { risksApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useRisks(projectId, params = {}) {
  return useQuery({
    queryKey: ['risks', projectId, params],
    queryFn: () => risksApi.list(projectId, params).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useAllRisks() {
  return useQuery({
    queryKey: ['risks'],
    queryFn: () => risksApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useRisk(id) {
  return useQuery({
    queryKey: ['risk-detail', id],
    queryFn: () => risksApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateRisk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => risksApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}

export function useUpdateRisk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => risksApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}

export function useDeleteRisk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => risksApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}
