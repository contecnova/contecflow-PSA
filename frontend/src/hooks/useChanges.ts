import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { changesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface ChangeRequest {
  id: string
  title?: string
  status?: string
  risk_level?: string
  [extra: string]: unknown
}

export type ChangeListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type ApproveArgs = { id: string; data: Record<string, unknown> }

export function useChanges(params: ChangeListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-changes', params],
    queryFn: () => changesApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAllChanges(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-changes'],
    queryFn: () => changesApi.list().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useChange(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-change-detail', id],
    queryFn: () => changesApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateChange(): UseMutationResult<unknown, unknown, Partial<ChangeRequest>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<ChangeRequest>) => changesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-changes'] }),
  })
}

export function useUpdateChange(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<ChangeRequest>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<ChangeRequest>>) => changesApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-changes'] })
      qc.invalidateQueries({ queryKey: ['sd-change-detail'] })
    },
  })
}

export function useApproveChange(): UseMutationResult<unknown, unknown, ApproveArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: ApproveArgs) => changesApi.approve(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-changes'] }),
  })
}

export function useDeleteChange(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => changesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-changes'] }),
  })
}
