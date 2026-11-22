/**
 * Piezas comunes de la pestaña Riesgo (22-11-2026): etiquetas de los códigos
 * del servidor (`swr.v_<catálogo>`), listas de valores (`/risk/meta`), tono por
 * nivel de riesgo, barra de porcentaje y fecha de mañana.
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.
 */
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { StatusBadge } from '../../../ui'
import type { StatusBadgeKind } from '../../../ui'
import { useAppT } from '../../../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../../../i18n/etiquetaCodigo'
import { STALE_DEFAULT_MS } from '../../../../constants/timings'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { NivelDeRiesgo } from '../../../../services/api/cmdbRiesgo'

export const NIVEL_KIND: Record<string, StatusBadgeKind> = { critical: 'danger', high: 'orange', medium: 'warning', low: 'success' }

/** Texto traducido de un código del servidor: `swr.v_<catalogo>.<codigo>` (si falta, el código). */
export function useEtiquetaSwr() {
  const t = useAppT()
  return (catalogo: string, codigo: string | null | undefined) => (codigo ? etiquetaCodigo(t, `swr.v_${catalogo}`, codigo) : '—')
}

/** Valores permitidos del riesgo (ámbitos, controles, superficies, fuentes…): el servidor manda. */
export function useMetaRiesgo() {
  return useQuery({ queryKey: ['swr', 'meta'], queryFn: cmdbRiesgoApi.meta, staleTime: STALE_DEFAULT_MS })
}

export function NivelBadge({ nivel }: { nivel: NivelDeRiesgo | string | null | undefined }) {
  const e = useEtiquetaSwr()
  if (!nivel) return <span className="u-text3-xs">—</span>
  return <StatusBadge kind={NIVEL_KIND[nivel] ?? 'neutral'} caps={false}>{e('nivel', nivel)}</StatusBadge>
}

/** Barra horizontal 0-100 con el color del nivel (sin nivel, el acento). */
export function BarraPct({ pct, nivel, etiqueta }: { pct: number; nivel?: string | null; etiqueta?: string }) {
  const w = Math.max(0, Math.min(100, pct))
  return (
    <span className="sdm-bar" role="img" aria-label={etiqueta ?? `${Math.round(w)} %`}>
      <span className={`sdm-bar__fill${nivel ? ` swr-fill--${nivel}` : ''}`} style={{ '--sdm-w': `${w}%` } as CSSProperties} />
    </span>
  )
}

export const redondeo = (n: number | null | undefined, dec = 0) => (n == null ? '—' : Number(n).toFixed(dec))
export const pct = (n: number | null | undefined) => (n == null ? '—' : `${Number(n).toFixed(1)} %`)

export const enDias = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
