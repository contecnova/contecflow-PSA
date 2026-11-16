import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { ParamsPeriodoApi } from '../utils/periodo'
import type { AlertasDeMetricas, CatalogoDeMetricas, ConsultaDeMetrica, EtapaDelEmbudoOlap, HorasPorSemana, KpisOlap, MargenMensualOlap, NarrativaEjecutiva, OpcionesDeFiltroAnalitico, SaludDeProyectoOlap, UtilizacionAvanzada, UtilizacionOlap } from '../services/api/tipos-analitica'
import { analyticsApi } from '../services/api'
import { STALE_10_MIN_MS, STALE_5_MIN_MS } from '../constants/timings'

const STALE = 2 * 60 * 1000

export type AnalyticsParams = Record<string, unknown>

export function useAnalyticsQuery(metricId: string | undefined, params: AnalyticsParams = {}): UseQueryResult<ConsultaDeMetrica> {
  return useQuery({
    queryKey: ['analytics', metricId, params],
    queryFn: () => analyticsApi.query(metricId, params).then(r => r.data),
    enabled: !!metricId,
    staleTime: STALE,
  })
}

export function useAnalyticsFilterOptions(): UseQueryResult<OpcionesDeFiltroAnalitico> {
  return useQuery({
    queryKey: ['analytics-filter-options'],
    queryFn: () => analyticsApi.filterOptions().then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })
}

export function useHoursWeek(params: AnalyticsParams = {}): UseQueryResult<HorasPorSemana> {
  return useQuery({
    queryKey: ['analytics-hours-week', params],
    queryFn: () => analyticsApi.hoursWeek(params).then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })
}

export function useUtilization(params: AnalyticsParams = {}): UseQueryResult<UtilizacionAvanzada> {
  return useQuery({
    queryKey: ['analytics-utilization', params],
    queryFn: () => analyticsApi.utilization(params).then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })
}

export function useMetricBreaches(params: AnalyticsParams = {}): UseQueryResult<AlertasDeMetricas> {
  return useQuery({
    queryKey: ['analytics-metric-breaches', params],
    queryFn: () => analyticsApi.metricBreaches(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAnalyticsNarrative(params: AnalyticsParams = {}): UseQueryResult<NarrativaEjecutiva> {
  return useQuery({
    queryKey: ['analytics-narrative', params],
    queryFn: () => analyticsApi.narrative(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapKpis(params: AnalyticsParams = {}): UseQueryResult<KpisOlap> {
  return useQuery({
    queryKey: ['olap-kpis', params],
    queryFn: () => analyticsApi.olapKpis(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapPipelineFunnel(): UseQueryResult<EtapaDelEmbudoOlap[]> {
  return useQuery({
    queryKey: ['olap-pipeline-funnel'],
    queryFn: () => analyticsApi.olapFunnel().then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapPortfolioHealth(): UseQueryResult<SaludDeProyectoOlap[]> {
  return useQuery({
    queryKey: ['olap-portfolio-health'],
    queryFn: () => analyticsApi.olapPortfolio().then(r => r.data),
    staleTime: STALE,
  })
}

/** Evolución del margen OLAP. `periodo` (de `usePeriodo({ granularidades: SIN_HORA })`) manda sobre `months`. */
export function useOlapMarginEvolution(months: number | string | undefined, periodo?: ParamsPeriodoApi): UseQueryResult<MargenMensualOlap[]> {
  return useQuery({
    queryKey: ['olap-margin-evolution', months, periodo ?? null],
    queryFn: () => analyticsApi.olapMargin(months, periodo as Record<string, unknown> | undefined).then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapUtilization(): UseQueryResult<UtilizacionOlap[]> {
  return useQuery({
    queryKey: ['olap-utilization'],
    queryFn: () => analyticsApi.olapUtilization().then(r => r.data),
    staleTime: STALE,
  })
}

export function useAnalyticsCatalogue(): UseQueryResult<CatalogoDeMetricas> {
  return useQuery({
    queryKey: ['analytics-catalogue'],
    queryFn: () => analyticsApi.catalogue().then(r => r.data),
    staleTime: STALE_10_MIN_MS,
  })
}
