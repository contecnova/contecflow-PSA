import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { CargaDeRecurso, KpisDelCuadroDeMando, ProductividadDelEquipo, RentabilidadDeProyecto, SaludDeProyecto } from '../services/api/tipos-analitica'
import { dashboardApi } from '../services/api'
import { POLL_SLOW_MS } from '../constants/timings'

const STALE = 2 * 60 * 1000 // 2 min — dashboard/analytics data

export type DashboardParams = Record<string, unknown>

export function useKpis(): UseQueryResult<KpisDelCuadroDeMando> {
  return useQuery({
    queryKey: ['kpis'],
    queryFn: () => dashboardApi.kpis().then(r => r.data),
    refetchInterval: POLL_SLOW_MS, // every 5 min
    staleTime: STALE,
  })
}

export function useProjectsHealth(params: DashboardParams): UseQueryResult<SaludDeProyecto[]> {
  return useQuery({
    queryKey: ['projects-health', params],
    queryFn: () => dashboardApi.projectsHealth(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useResourceLoad(params: DashboardParams): UseQueryResult<CargaDeRecurso[]> {
  return useQuery({
    queryKey: ['resource-load', params],
    queryFn: () => dashboardApi.resourceLoad(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useProfitability(params: DashboardParams): UseQueryResult<RentabilidadDeProyecto[]> {
  return useQuery({
    queryKey: ['profitability', params],
    queryFn: () => dashboardApi.profitability(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useTeamProductivity(params: DashboardParams): UseQueryResult<ProductividadDelEquipo> {
  return useQuery({
    queryKey: ['team-productivity', params],
    queryFn: () => dashboardApi.teamProductivity(params).then(r => r.data),
    staleTime: STALE,
  })
}
