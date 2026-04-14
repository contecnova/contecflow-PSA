import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { pipelineApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function usePipeline(params = {}) {
  return useQuery({
    queryKey: ['pipeline', params],
    queryFn: () => pipelineApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useOpportunity(id) {
  return useQuery({
    queryKey: ['pipeline', id],
    queryFn: () => pipelineApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateOpportunity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => pipelineApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}

export function useUpdateOpportunity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => pipelineApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}

export function useDeleteOpportunity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => pipelineApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}
