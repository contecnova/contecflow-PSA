import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { milestonesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Milestone {
  id: string
  title?: string
  due_date?: string
  completed_at?: string | null
  [extra: string]: unknown
}

export type UpdateArgs<T> = { id: string; data: T }
export type CreateMilestoneArgs = { projectId: string; data: Partial<Milestone> }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useMilestones(projectId: string | undefined): UseQueryResult<Milestone[]> {
  return useQuery<Milestone[]>({
    queryKey: ['milestones', projectId],
    queryFn: () => milestonesApi.list(projectId).then((r: { data?: { items?: Milestone[] } | Milestone[] | null }) => unwrapList<Milestone>(r)),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useMilestoneDashboard(): UseQueryResult<Milestone[]> {
  return useQuery<Milestone[]>({
    queryKey: ['milestones-dashboard'],
    queryFn: () => milestonesApi.dashboard().then((r: { data?: { items?: Milestone[] } | Milestone[] | null }) => unwrapList<Milestone>(r)),
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
