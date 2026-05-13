import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { alertsApi } from '../services/api'

export function useAlerts(params = {}) {
  return useQuery({
    queryKey: ['alerts', params],
    queryFn: () => alertsApi.list(params).then(r => r.data?.items ?? r.data ?? []),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  })
}

export function useReadAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => alertsApi.read(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useResolveAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => alertsApi.resolve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useRunAlerts() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => alertsApi.run(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}
