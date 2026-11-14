import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import { alertsApi } from '../services/api'
import type { Alerta } from '../services/api/tipos-documentos'
import { queryKeys } from '../constants/queryKeys'
import { POLL_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'

/** `AlertOut` (antes anunciaba `message`, `level` y `resolved`, que el backend no manda:
 *  son `title`, `severity` e `is_resolved`). */
export type AlertItem = Alerta

export type AlertListParams = Record<string, unknown>

export function useAlerts(params: AlertListParams = {}): UseQueryResult<AlertItem[]> {
  return useQuery<AlertItem[]>({
    queryKey: queryKeys.alerts.list(params),
    queryFn: () => alertsApi.list(params).then(r => r.data),
    staleTime: STALE_SHORT_MS,
    refetchInterval: POLL_DEFAULT_MS,
  })
}

export function useReadAlert(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => alertsApi.read(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.alerts.all() }),
  })
}

export function useResolveAlert(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => alertsApi.resolve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.alerts.all() }),
  })
}

export function useRunAlerts(): UseMutationResult<unknown, unknown, void> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => alertsApi.run(),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.alerts.all() }),
  })
}
