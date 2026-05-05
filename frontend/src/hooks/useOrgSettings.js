/**
 * useOrgSettings — fetches org-level defaults (currency, timezone, language, etc.)
 * from the backend /settings/org-defaults endpoint.
 *
 * Falls back to sensible defaults so components never crash when the query is
 * loading or if the endpoint is temporarily unavailable.
 */
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

const FALLBACK = {
  currency: 'EUR',
  timezone: 'Europe/Madrid',
  language: 'es',
  working_hours_per_day: 8,
  weekly_capacity_hours: 40,
  vacation_days_per_year: 23,
  tax_rate: 21.0,
}

export function useOrgSettings() {
  const { data } = useQuery({
    queryKey: ['org-defaults'],
    queryFn: () => api.get('/settings/org-defaults').then(r => r.data),
    staleTime: 5 * 60 * 1000, // 5 min
    retry: 1,
  })
  return { ...FALLBACK, ...data }
}
