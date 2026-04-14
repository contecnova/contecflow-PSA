import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { milestonesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useMilestones(projectId) {
  return useQuery({
    queryKey: ['milestones', projectId],
    queryFn: () => milestonesApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useMilestoneDashboard() {
  return useQuery({
    queryKey: ['milestones-dashboard'],
    queryFn: () => milestonesApi.dashboard().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateMilestone() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }) => milestonesApi.create(projectId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones'] }),
  })
}

export function useUpdateMilestone() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => milestonesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones'] }),
  })
}

export function useCompleteMilestone() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => milestonesApi.complete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones'] }),
  })
}

export function useDeleteMilestone() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => milestonesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones'] }),
  })
}
