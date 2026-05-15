import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { problemsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface ProblemRecord {
  id: string
  title?: string
  status?: string
  priority?: string
  [extra: string]: unknown
}

export type ProblemListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

export function useProblems(params: ProblemListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-problems', params],
    queryFn: () => problemsApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAllProblems(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-problems'],
    queryFn: () => problemsApi.list().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useCreateProblem(): UseMutationResult<unknown, unknown, Partial<ProblemRecord>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<ProblemRecord>) => problemsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-problems'] }),
  })
}

export function useUpdateProblem(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<ProblemRecord>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<ProblemRecord>>) => problemsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-problems'] }),
  })
}

export function useDeleteProblem(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => problemsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-problems'] }),
  })
}
