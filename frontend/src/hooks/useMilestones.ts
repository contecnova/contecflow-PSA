import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import { milestonesApi } from '../services/api'
import type { HitoDeFacturacion, HitoPendiente } from '../services/api/tipos-finanzas'

const STALE = 2 * 60 * 1000

/** serialize_milestone (services/api/tipos-finanzas.ts): el hito tiene `name` y `completed_date`. */
export type Milestone = HitoDeFacturacion

export type UpdateArgs<T> = { id: string; data: T }
export type CreateMilestoneArgs = { projectId: string; data: Partial<Milestone> }

export function useMilestones(projectId: string | undefined): UseQueryResult<Milestone[]> {
  return useQuery<Milestone[]>({
    queryKey: ['milestones', projectId],
    queryFn: () => milestonesApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useMilestoneDashboard(): UseQueryResult<HitoPendiente[]> {
  return useQuery<HitoPendiente[]>({
    queryKey: ['milestones-dashboard'],
    queryFn: () => milestonesApi.dashboard().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateMilestone(): UseMutationResult<unknown, unknown, CreateMilestoneArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: CreateMilestoneArgs) => milestonesApi.create(projectId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones'] }),
  })
}

export function useUpdateMilestone(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Milestone>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Milestone>>) => milestonesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones'] }),
  })
}

export function useCompleteMilestone(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => milestonesApi.complete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones'] }),
  })
}

export function useDeleteMilestone(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => milestonesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['milestones'] }),
  })
}
