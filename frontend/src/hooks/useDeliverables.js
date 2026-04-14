import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { deliverablesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useDeliverables(projectId) {
  return useQuery({
    queryKey: ['deliverables', projectId],
    queryFn: () => deliverablesApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useDeliverableOverview() {
  return useQuery({
    queryKey: ['deliverables-overview'],
    queryFn: () => deliverablesApi.overview().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateDeliverable() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => deliverablesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deliverables'] }),
  })
}

export function useUpdateDeliverable() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => deliverablesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deliverables'] }),
  })
}

export function useDeleteDeliverable() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => deliverablesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['deliverables'] }),
  })
}
