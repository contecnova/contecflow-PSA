import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import { risksApi } from '../services/api'

const STALE = 2 * 60 * 1000

// Tipo de respuesta del cliente de API (services/api/tipos.ts, auditoria 2026-11 #39).
import type { Risk, RiesgosDelProyecto } from '../services/api/tipos'
import type { RiesgoAbiertoDeLaCartera, RiesgoSerializado } from '../services/api/tipos-proyectos'
export type { Risk }

export type RiskListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type CreateRiskArgs = { projectId: string; data: Partial<Risk> }
export type UpdateRiskArgs = { projectId: string; id: string; data: Partial<Risk> }
export type DeleteRiskArgs = { projectId: string; id: string }

export function useRisks(projectId: string | undefined, params: RiskListParams = {}): UseQueryResult<RiesgosDelProyecto> {
  return useQuery({
    queryKey: ['risks', projectId, params],
    queryFn: () => risksApi.list(projectId, params).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useAllRisks(): UseQueryResult<RiesgoAbiertoDeLaCartera[]> {
  return useQuery({
    queryKey: ['risks'],
    queryFn: () => risksApi.portfolioAll().then(r => r.data),
    staleTime: STALE,
  })
}

export function useRisk(projectId: string | undefined, id: string | undefined): UseQueryResult<RiesgoSerializado> {
  return useQuery({
    queryKey: ['risk-detail', projectId, id],
    queryFn: () => risksApi.get(projectId as string, id as string).then(r => r.data),
    enabled: !!projectId && !!id,
    staleTime: STALE,
  })
}

export function useCreateRisk(): UseMutationResult<unknown, unknown, CreateRiskArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: CreateRiskArgs) => risksApi.create(projectId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}

export function useUpdateRisk(): UseMutationResult<unknown, unknown, UpdateRiskArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, id, data }: UpdateRiskArgs) => risksApi.update(projectId, id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}

export function useDeleteRisk(): UseMutationResult<unknown, unknown, DeleteRiskArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, id }: DeleteRiskArgs) => risksApi.delete(projectId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks'] }),
  })
}
