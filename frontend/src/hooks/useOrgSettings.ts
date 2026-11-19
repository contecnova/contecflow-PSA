/**
 * useOrgSettings — fetches org-level defaults (currency, timezone, language, etc.)
 * from the backend /settings/org-defaults endpoint.
 *
 * Falls back to sensible defaults so components never crash when the query is
 * loading or if the endpoint is temporarily unavailable.
 */
import { useQuery } from '@tanstack/react-query'
// TODO type: api service is still JS; treat default export as untyped axios instance.
import api from '../services/api'
import { STALE_5_MIN_MS } from '../constants/timings'
import { browserTimezone } from '../constants/timezones'
import { conDefectos, tonoDe } from '../utils/umbrales'
import type { Metrica, Tono, Umbrales } from '../utils/umbrales'

export interface OrgSettings {
  currency: string
  timezone: string
  language: string
  working_hours_per_day: number
  weekly_capacity_hours: number
  vacation_days_per_year: number
  tax_rate: number
  /** Monedas de la empresa (`SUPPORTED_CURRENCIES`, Admin). Vacía hasta que responde el servidor. */
  currencies: string[]
  /** Umbrales de semáforo por métrica (19-11-2026, `app/core/umbrales.py`). */
  umbrales?: Partial<Umbrales>
  [extra: string]: unknown
}

const FALLBACK: OrgSettings = {
  currency: 'EUR',
  // Mientras no responde el servidor: la zona del navegador (la de la empresa llega de /settings/org-defaults).
  timezone: browserTimezone(),
  language: 'es',
  working_hours_per_day: 8,
  weekly_capacity_hours: 40,
  vacation_days_per_year: 23,
  tax_rate: 21.0,
  currencies: [],
}

export function useOrgSettings(): OrgSettings {
  const { data } = useQuery<Partial<OrgSettings>>({
    queryKey: ['org-defaults'],
    queryFn: () => api.get('/settings/org-defaults').then((r: { data: Partial<OrgSettings> }) => r.data),
    staleTime: STALE_5_MIN_MS, // 5 min
    retry: 1,
  })
  return { ...FALLBACK, ...(data ?? {}) }
}

/**
 * Umbrales de semáforo de la empresa (19-11-2026): una definición por métrica
 * para todas las pantallas (ver utils/umbrales.ts). Mientras no responde el
 * servidor, los valores por defecto.
 */
export function useUmbrales(): Umbrales {
  return conDefectos(useOrgSettings().umbrales)
}

/** `tono(metrica, valor)` con los umbrales de la empresa. */
export function useTono(): (metrica: Metrica, valor: number | null | undefined) => Tono | undefined {
  const umbrales = useUmbrales()
  return (metrica, valor) => tonoDe(metrica, valor, umbrales)
}
