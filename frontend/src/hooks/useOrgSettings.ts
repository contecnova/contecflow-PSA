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
  /** Valores de formulario de la empresa (19-11-2026, `valores_de_negocio.py`); no llega al externo. */
  propuestas?: Partial<Propuestas>
  [extra: string]: unknown
}

/** Valores que proponen los formularios; antes fijos en cada pantalla (ver `usePropuestas`). */
export interface Propuestas {
  /** `CHANGE_CANARY_RAMP_PCT`: % por fase de un despliegue canario (creciente, acaba en 100). */
  change_canary_ramp_pct: number[]
  /** `CHANGE_CANARY_*_MINUTES`: minutos de la primera fase, de cada intermedia y de la última. */
  change_canary_minutes: { first: number; step: number; last: number }
  /** `CHAT_RETENTION_PROPOSED_MONTHS`, ya dentro del mínimo y del tope de la empresa. */
  chat_retention_proposed_months: number
  /** `VACATION_MAX_DAYS_ENTITLED`. */
  vacation_max_days_entitled: number
}

/** Los valores por defecto del servidor: los que había escritos antes en cada pantalla. */
export const PROPUESTAS_POR_DEFECTO: Propuestas = {
  change_canary_ramp_pct: [1, 5, 25, 50, 100],
  change_canary_minutes: { first: 30, step: 45, last: 60 },
  chat_retention_proposed_months: 24,
  vacation_max_days_entitled: 60,
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
 * Valores de formulario de la empresa (19-11-2026): rampa canaria, retención
 * propuesta del chat, máximo de vacaciones. Se editan en Configuración; mientras
 * no responde el servidor, los de por defecto.
 */
export function usePropuestas(): Propuestas {
  return { ...PROPUESTAS_POR_DEFECTO, ...(useOrgSettings().propuestas ?? {}) }
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
