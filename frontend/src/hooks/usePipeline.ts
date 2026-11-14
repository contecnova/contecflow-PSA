import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import type { AxiosResponse } from 'axios'
import { pipelineApi } from '../services/api'
import type { Oportunidad, OportunidadConvertida } from '../services/api/tipos-personas'

const STALE = 2 * 60 * 1000

export type Opportunity = Oportunidad
/** Cuerpo de alta o edicion (`OpportunityIn` / `OpportunityUpdate` en app/schemas/pipeline.py). */
export type OpportunityPayload = Record<string, unknown>

export type PipelineParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type GenerateProposalArgs = { id: string; payload: Record<string, unknown> }

export function usePipeline(params: PipelineParams = {}): UseQueryResult<Oportunidad[]> {
  return useQuery({
    queryKey: ['pipeline', params],
    queryFn: () => pipelineApi.list(params).then((r) => r.data),
    staleTime: STALE,
  })
}

export function useOpportunity(id: string | undefined): UseQueryResult<Oportunidad> {
  return useQuery({
    queryKey: ['pipeline', id],
    queryFn: () => pipelineApi.get(id).then((r) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateOpportunity(): UseMutationResult<unknown, unknown, OpportunityPayload> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: OpportunityPayload) => pipelineApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}

export function useUpdateOpportunity(): UseMutationResult<unknown, unknown, UpdateArgs<OpportunityPayload>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<OpportunityPayload>) => pipelineApi.update(id, data),
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

export function useConvertToProject(): UseMutationResult<AxiosResponse<OportunidadConvertida>, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => pipelineApi.convertToProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })
}
