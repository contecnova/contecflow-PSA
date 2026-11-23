import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import type { ParamsPeriodoApi } from '../utils/periodo'
import type { DesgloseDeMargen, FiltroDeMargen, MargenMensualOlap } from '../services/api/tipos-analitica'
import { analyticsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export type AnalyticsParams = Record<string, unknown>

/** Evolución del margen OLAP. `periodo` (de `usePeriodo({ granularidades: SIN_HORA })`) manda sobre `months`. */
export function useOlapMarginEvolution(months: number | string | undefined, periodo?: ParamsPeriodoApi, filtro?: FiltroDeMargen): UseQueryResult<MargenMensualOlap[]> {
  return useQuery({
    queryKey: ['olap-margin-evolution', months, periodo ?? null, filtro ?? null],
    queryFn: () => analyticsApi.olapMargin(months, periodo, filtro).then(r => r.data),
    staleTime: STALE,
  })
}

/** Totales del periodo por proyecto o cliente (desglose de la evolución del margen). */
export function useOlapMarginBreakdown(por: 'proyecto' | 'cliente', periodo?: ParamsPeriodoApi): UseQueryResult<DesgloseDeMargen[]> {
  return useQuery({
    queryKey: ['olap-margin-breakdown', por, periodo ?? null],
    queryFn: () => analyticsApi.olapMarginBreakdown(por, periodo).then(r => r.data),
    staleTime: STALE,
  })
}

