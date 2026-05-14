import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { alertsApi } from '../services/api'
import { queryKeys } from '../constants/queryKeys'

export function useAlerts(params = {}) {
  return useQuery({
    queryKey: queryKeys.alerts.list(params),
    queryFn: () => alertsApi.list(params).then(r => r.data?.items ?? r.data ?? []),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  })
}

export function useReadAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => alertsApi.read(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.alerts.all() }),
  })
}

export function useResolveAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => alertsApi.resolve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.alerts.all() }),
  })
}

export function useRunAlerts() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => alertsApi.run(),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.alerts.all() }),
  })
}
