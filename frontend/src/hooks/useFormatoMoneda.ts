/**
 * useFormatoMoneda — formatea importes con la moneda de la empresa.
 *
 * Auditoria 2026-11 (#18): habia 50 lineas con '€' y 24 con 'EUR' escritos en
 * las pantallas aunque la moneda de la empresa existe (useOrgSettings). Este
 * hook es la unica via: `dinero(n)` usa la moneda de la empresa; si el dato
 * trae la suya, `dinero(n, { moneda: factura.currency })`.
 */
import { useMemo } from 'react'
import { useOrgSettings } from './useOrgSettings'
import { formatearMoneda, simboloMoneda, type OpcionesMoneda } from '../utils/helpers'

export interface FormatoMoneda {
  (n: number | string | null | undefined, op?: OpcionesMoneda & { moneda?: string | null }): string
  /** Codigo ISO de la moneda de la empresa ('EUR', 'USD'...). */
  moneda: string
  /** Su simbolo en el idioma activo ('€', 'US$'...), para etiquetas como "Importe (€)". */
  simbolo: string
}

export function useFormatoMoneda(): FormatoMoneda {
  const { currency } = useOrgSettings()
  return useMemo(() => {
    const formatear = (n: number | string | null | undefined, op: OpcionesMoneda & { moneda?: string | null } = {}) =>
      formatearMoneda(n, op.moneda || currency, op)
    return Object.assign(formatear, { moneda: currency, simbolo: simboloMoneda(currency) })
  }, [currency])
}
