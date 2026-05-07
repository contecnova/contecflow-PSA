import { useQuery, useMutation } from '@tanstack/react-query'
import { forecastApi, biForecastingApi } from '../services/api'

const STALE = 2 * 60 * 1000

// ── Resource Forecast ─────────────────────────────────────────────────────────

export function useForecastHeatmap(params = {}) {
  return useQuery({
    queryKey: ['forecast-heatmap', params],
    queryFn: () => forecastApi.heatmap(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useForecastUserDetail(userId, params = {}) {
  return useQuery({
    queryKey: ['forecast-user', userId, params],
    queryFn: () => forecastApi.userDetail(userId, params).then(r => r.data),
    enabled: !!userId,
    staleTime: STALE,
  })
}

export function useForecastAvailability(params = {}) {
  return useQuery({
    queryKey: ['forecast-availability', params],
    queryFn: () => forecastApi.availability(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useForecastSummary(params = {}) {
  return useQuery({
    queryKey: ['forecast-summary', params],
    queryFn: () => forecastApi.summary(params).then(r => r.data),
    staleTime: STALE,
  })
}

// ── BI Forecasting ────────────────────────────────────────────────────────────

export function useBiForecastingMetrics() {
  return useQuery({
    queryKey: ['bi-forecasting-metrics'],
    queryFn: () => biForecastingApi.getMetrics().then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useBiForecast(metric, params = {}) {
  return useQuery({
    queryKey: ['bi-forecast', metric, params],
    queryFn: () => biForecastingApi.forecast(metric, params).then(r => r.data),
    enabled: !!metric,
    staleTime: STALE,
  })
}

export function useBiMultiForecast() {
  return useMutation({
    mutationFn: (data) => biForecastingApi.multiForecast(data),
  })
}
