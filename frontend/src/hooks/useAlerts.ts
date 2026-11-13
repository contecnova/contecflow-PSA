import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS — typed as any via implicit import.
import { alertsApi } from '../services/api'
import { queryKeys } from '../constants/queryKeys'
import { POLL_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'

export interface AlertItem {
  id: string
  message?: string
  level?: 'info' | 'warning' | 'critical'
  is_read?: boolean
  resolved?: boolean
  created_at?: string
  [extra: string]: unknown
}

export type AlertListParams = Record<string, unknown>

export function useAlerts(params: AlertListParams = {}): UseQueryResult<AlertItem[]> {
  return useQuery<AlertItem[]>({
    queryKey: queryKeys.alerts.list(params),
    queryFn: () => alertsApi.list(params).then((r: { data: { items?: AlertItem[] } | AlertItem[] }) => {
      const d = r.data as { items?: AlertItem[] } | AlertItem[] | undefined
      if (Array.isArray(d)) return d
      return d?.items ?? []
    }),
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
