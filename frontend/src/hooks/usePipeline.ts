import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { pipelineApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Opportunity {
  id: string
  name?: string
  status?: string
  [extra: string]: unknown
}

export type PipelineParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type GenerateProposalArgs = { id: string; payload: Record<string, unknown> }

export function usePipeline(params: PipelineParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['pipeline', params],
    queryFn: () => pipelineApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useOpportunity(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['pipeline', id],
    queryFn: () => pipelineApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateOpportunity(): UseMutationResult<unknown, unknown, Partial<Opportunity>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Opportunity>) => pipelineApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}

export function useUpdateOpportunity(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Opportunity>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Opportunity>>) => pipelineApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}

export function useDeleteOpportunity(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => pipelineApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}

export function useGenerateProposal(): UseMutationResult<unknown, unknown, GenerateProposalArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: GenerateProposalArgs) => pipelineApi.generateProposal(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}

export function useMarkProposalSent(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => pipelineApi.markProposalSent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}

export function useConvertToProject(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => pipelineApi.convertToProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}
