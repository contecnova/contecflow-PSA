import { useQuery, useMutation } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { forecastApi, biForecastingApi } from '../services/api'
import { STALE_5_MIN_MS } from '../constants/timings'

const STALE = 2 * 60 * 1000

export type ForecastParams = Record<string, unknown>

// ── Resource Forecast ─────────────────────────────────────────────────────────

export function useForecastHeatmap(params: ForecastParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['forecast-heatmap', params],
    queryFn: () => forecastApi.heatmap(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useForecastUserDetail(userId: string | undefined, params: ForecastParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['forecast-user', userId, params],
    queryFn: () => forecastApi.userDetail(userId, params).then((r: { data: unknown }) => r.data),
    enabled: !!userId,
    staleTime: STALE,
  })
}

export function useForecastAvailability(params: ForecastParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['forecast-availability', params],
    queryFn: () => forecastApi.availability(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useForecastSummary(params: ForecastParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['forecast-summary', params],
    queryFn: () => forecastApi.summary(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

// ── BI Forecasting ────────────────────────────────────────────────────────────

export function useBiForecastingMetrics(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['bi-forecasting-metrics'],
    queryFn: () => biForecastingApi.getMetrics().then((r: { data: unknown }) => r.data),
    staleTime: STALE_5_MIN_MS,
  })
}

export function useBiForecast(metric: string | undefined, params: ForecastParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['bi-forecast', metric, params],
    queryFn: () => biForecastingApi.forecast(metric, params).then((r: { data: unknown }) => r.data),
    enabled: !!metric,
    staleTime: STALE,
  })
}

export function useBiMultiForecast(): UseMutationResult<unknown, unknown, ForecastParams> {
  return useMutation({
    mutationFn: (data: ForecastParams) => biForecastingApi.multiForecast(data),
  })
}
