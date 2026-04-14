import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sprintsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useSprints(projectId, params = {}) {
  return useQuery({
    queryKey: ['sprints', projectId, params],
    queryFn: () => sprintsApi.list(projectId, params).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useAllSprints(params = {}) {
  return useQuery({
    queryKey: ['sprints', params],
    queryFn: () => sprintsApi.list(undefined, params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useSprint(id) {
  return useQuery({
    queryKey: ['sprints', id],
    queryFn: () => sprintsApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateSprint() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => sprintsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprints'] }),
  })
}

export function useUpdateSprint() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => sprintsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprints'] }),
  })
}

export function useDeleteSprint() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => sprintsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sprints'] }),
  })
}
