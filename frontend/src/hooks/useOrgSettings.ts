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
  [extra: string]: unknown
}

const FALLBACK: OrgSettings = {
  currency: 'EUR',
  timezone: 'Europe/Madrid',
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
    staleTime: 5 * 60 * 1000, // 5 min
    retry: 1,
  })
  return { ...FALLBACK, ...(data ?? {}) }
}
