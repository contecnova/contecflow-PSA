import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useAnalyticsQuery(metricId, params = {}) {
  return useQuery({
    queryKey: ['analytics', metricId, params],
    queryFn: () => analyticsApi.query(metricId, params).then(r => r.data),
    enabled: !!metricId,
    staleTime: STALE,
  })
}

export function useAnalyticsFilterOptions() {
  return useQuery({
    queryKey: ['analytics-filter-options'],
    queryFn: () => analyticsApi.filterOptions().then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useHoursWeek(params = {}) {
  return useQuery({
    queryKey: ['analytics-hours-week', params],
    queryFn: () => analyticsApi.hoursWeek(params).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useUtilization(params = {}) {
  return useQuery({
    queryKey: ['analytics-utilization', params],
    queryFn: () => analyticsApi.utilization(params).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useMetricBreaches(params = {}) {
  return useQuery({
    queryKey: ['analytics-metric-breaches', params],
    queryFn: () => analyticsApi.metricBreaches(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAnalyticsNarrative(params = {}) {
  return useQuery({
    queryKey: ['analytics-narrative', params],
    queryFn: () => analyticsApi.narrative(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapKpis(params = {}) {
  return useQuery({
    queryKey: ['olap-kpis', params],
    queryFn: () => analyticsApi.olapKpis(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapPipelineFunnel() {
  return useQuery({
    queryKey: ['olap-pipeline-funnel'],
    queryFn: () => analyticsApi.olapFunnel().then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapPortfolioHealth() {
  return useQuery({
    queryKey: ['olap-portfolio-health'],
    queryFn: () => analyticsApi.olapPortfolio().then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapMarginEvolution(months) {
  return useQuery({
    queryKey: ['olap-margin-evolution', months],
    queryFn: () => analyticsApi.olapMargin(months).then(r => r.data),
    staleTime: STALE,
  })
}

export function useOlapUtilization() {
  return useQuery({
    queryKey: ['olap-utilization'],
    queryFn: () => analyticsApi.olapUtilization().then(r => r.data),
    staleTime: STALE,
  })
}

export function useAnalyticsCatalogue() {
  return useQuery({
    queryKey: ['analytics-catalogue'],
    queryFn: () => analyticsApi.catalogue().then(r => r.data),
    staleTime: 10 * 60 * 1000,
  })
}
