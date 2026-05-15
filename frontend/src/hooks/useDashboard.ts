import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { dashboardApi } from '../services/api'

const STALE = 2 * 60 * 1000 // 2 min — dashboard/analytics data

export type DashboardParams = Record<string, unknown>

export function useKpis(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['kpis'],
    queryFn: () => dashboardApi.kpis().then((r: { data: unknown }) => r.data),
    refetchInterval: 1000 * 60 * 5, // every 5 min
    staleTime: STALE,
  })
}

export function useProjectsHealth(params: DashboardParams): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['projects-health', params],
    queryFn: () => dashboardApi.projectsHealth(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useResourceLoad(params: DashboardParams): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['resource-load', params],
    queryFn: () => dashboardApi.resourceLoad(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useProfitability(params: DashboardParams): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['profitability', params],
    queryFn: () => dashboardApi.profitability(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useTeamProductivity(params: DashboardParams): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['team-productivity', params],
    queryFn: () => dashboardApi.teamProductivity(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}
