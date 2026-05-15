import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { analyticsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export type AnalyticsParams = Record<string, unknown>

export function useAnalyticsQuery(metricId: string | undefined, params: AnalyticsParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['analytics', metricId, params],
    queryFn: () => analyticsApi.query(metricId, params).then((r: { data: unknown }) => r.data),
    enabled: !!metricId,
    staleTime: STALE,
  })
}

export function useAnalyticsFilterOptions(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['analytics-filter-options'],
    queryFn: () => analyticsApi.filterOptions().then((r: { data: unknown }) => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useHoursWeek(params: AnalyticsParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['analytics-hours-week', params],
    queryFn: () => analyticsApi.hoursWeek(params).then((r: { data: unknown }) => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useUtilization(params: AnalyticsParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['analytics-utilization', params],
    queryFn: () => analyticsApi.utilization(params).then((r: { data: unknown }) => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useMetricBreaches(params: AnalyticsParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['analytics-metric-breaches', params],
    queryFn: () => analyticsApi.metricBreaches(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAnalyticsNarrative(params: AnalyticsParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['analytics-narrative', params],
    queryFn: () => analyticsApi.narrative(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useOlapKpis(params: AnalyticsParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['olap-kpis', params],
    queryFn: () => analyticsApi.olapKpis(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useOlapPipelineFunnel(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['olap-pipeline-funnel'],
    queryFn: () => analyticsApi.olapFunnel().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useOlapPortfolioHealth(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['olap-portfolio-health'],
    queryFn: () => analyticsApi.olapPortfolio().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useOlapMarginEvolution(months: number | string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['olap-margin-evolution', months],
    queryFn: () => analyticsApi.olapMargin(months).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useOlapUtilization(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['olap-utilization'],
    queryFn: () => analyticsApi.olapUtilization().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAnalyticsCatalogue(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['analytics-catalogue'],
    queryFn: () => analyticsApi.catalogue().then((r: { data: unknown }) => r.data),
    staleTime: 10 * 60 * 1000,
  })
}
