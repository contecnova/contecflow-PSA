import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { changesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useChanges(params = {}) {
  return useQuery({
    queryKey: ['sd-changes', params],
    queryFn: () => changesApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAllChanges() {
  return useQuery({
    queryKey: ['sd-changes'],
    queryFn: () => changesApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useChange(id) {
  return useQuery({
    queryKey: ['sd-change-detail', id],
    queryFn: () => changesApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateChange() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => changesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-changes'] }),
  })
}

export function useUpdateChange() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => changesApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-changes'] })
      qc.invalidateQueries({ queryKey: ['sd-change-detail'] })
    },
  })
}

export function useApproveChange() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => changesApi.approve(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-changes'] }),
  })
}

export function useDeleteChange() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => changesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-changes'] }),
  })
}
