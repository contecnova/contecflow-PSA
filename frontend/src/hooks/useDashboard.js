import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '../services/api'

const STALE = 2 * 60 * 1000 // 2 min — dashboard/analytics data

export function useKpis() {
  return useQuery({
    queryKey: ['kpis'],
    queryFn: () => dashboardApi.kpis().then(r => r.data),
    refetchInterval: 1000 * 60 * 5, // every 5 min
    staleTime: STALE,
  })
}

export function useProjectsHealth(params) {
  return useQuery({
    queryKey: ['projects-health', params],
    queryFn: () => dashboardApi.projectsHealth(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useResourceLoad(params) {
  return useQuery({
    queryKey: ['resource-load', params],
    queryFn: () => dashboardApi.resourceLoad(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useProfitability(params) {
  return useQuery({
    queryKey: ['profitability', params],
    queryFn: () => dashboardApi.profitability(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useTeamProductivity(params) {
  return useQuery({
    queryKey: ['team-productivity', params],
    queryFn: () => dashboardApi.teamProductivity(params).then(r => r.data),
    staleTime: STALE,
  })
}
