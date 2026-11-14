import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import { epicsApi } from '../services/api'

const STALE = 2 * 60 * 1000

// Tipo de respuesta del cliente de API (services/api/tipos.ts, auditoria 2026-11 #39).
import type { Epic } from '../services/api/tipos'
export type { Epic }

export type UpdateArgs<T> = { id: string; data: T }

export function useEpics(projectId: string | undefined): UseQueryResult<Epic[]> {
  return useQuery({
    queryKey: ['epics', projectId],
    queryFn: () => epicsApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

// POST /epics exige `project_id` en la query (antes se llamaba sin él: 422 siempre).
export type CreateEpicArgs = { projectId: string; data: Partial<Epic> }

export function useCreateEpic(): UseMutationResult<unknown, unknown, CreateEpicArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: CreateEpicArgs) => epicsApi.createForProject(projectId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}

export function useUpdateEpic(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Epic>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Epic>>) => epicsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}

export function useDeleteEpic(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => epicsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}
