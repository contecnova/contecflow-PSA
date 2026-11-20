/**
 * InformesComunes — piezas compartidas de los informes de CMDB y del análisis
 * del cambio (19-11-2026). Sustituyen al volcado genérico `VistaDeDatos`:
 * cada resultado del servidor tiene ahora su informe propio
 * (`InformesDeCmdb.tsx`, `InformesDelCambio.tsx`) con el mismo lenguaje que
 * «Mi panel» (`WidgetsDelPanel.tsx`): KpiCard, BarRow, TablaSimple, gráficos
 * Recharts con `useChartTheme` y textos del bloque i18n `sd_informes`.
 *
 * Nunca se enseña un id interno ni un código sin traducir: los códigos pasan
 * por `etiquetaCodigo` con su catálogo y las fechas por `fmtDate*`.
 */
import type { ReactNode } from 'react'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { StatusBadge } from '../ui'
import type { StatusBadgeKind } from '../ui'
import './sdMercado.css'

/** Un código del servidor sin el prefijo de enumerado («CIType.server» → «server»). */
export const codigo = (v: unknown): string => (v == null ? '' : String(v).split('.').pop() ?? '')

/** Lista de una respuesta que puede llegar como array o como `{ items }`. */
export function listaDe<T>(d: unknown): T[] {
  if (Array.isArray(d)) return d as T[]
  const items = (d as { items?: unknown } | null | undefined)?.items
  return Array.isArray(items) ? (items as T[]) : []
}

/** Tono de un nivel de riesgo o criticidad. */
export const KIND_DE_NIVEL: Record<string, StatusBadgeKind> = {
  critical: 'danger', high: 'orange', medium: 'warning', low: 'success', normal: 'neutral',
}
export const NIVELES = ['critical', 'high', 'medium', 'low'] as const
/** Color (variable CSS) de cada nivel para barras y gráficos. */
export const COLOR_DE_NIVEL: Record<string, string> = {
  critical: 'var(--danger)', high: 'var(--orange)', medium: 'var(--warning)', low: 'var(--success)', normal: 'var(--text-3)',
}

/** Insignia de nivel (riesgo, criticidad, impacto) traducida. */
export function Nivel({ nivel }: { nivel: string | null | undefined }) {
  const t = useAppT()
  const c = codigo(nivel).toLowerCase()
  if (!c) return <span className="u-text3-sm">—</span>
  return <StatusBadge caps={false} dot kind={KIND_DE_NIVEL[c] ?? 'neutral'}>{etiquetaCodigo(t, 'sd_informes.nivel', c)}</StatusBadge>
}

/** Subtítulo de un bloque del informe. */
export function Subtitulo({ children }: { children: ReactNode }) {
  return <div className="ds-eyebrow sdp-subtitulo">{children}</div>
}

const DIAS_DEL_SERVIDOR = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const dosCifras = (n: number) => String(((n % 24) + 24) % 24).padStart(2, '0')

/**
 * Ventana de mantenimiento de cuatro horas traducida. Acepta día (0 = lunes) y
 * hora UTC, o la etiqueta que manda el servidor en inglés
 * («Tuesday 02:00–06:00 UTC»), que se vuelve a escribir en el idioma activo.
 */
export function useVentana() {
  const t = useAppT()
  return (dia: number | null | undefined, hora: number | null | undefined, etiqueta?: string | null): string => {
    let d = dia
    let h = hora
    if ((d == null || h == null) && etiqueta) {
      const m = /^(\w+)\s+(\d{1,2}):00/.exec(etiqueta)
      const i = m ? DIAS_DEL_SERVIDOR.indexOf(m[1]) : -1
      if (m && i >= 0) { d = i; h = Number(m[2]) }
    }
    if (d == null || h == null) return etiqueta || '—'
    return t('sd_informes.ventana', { dia: t(`sd_mercado.dia_${d}`), desde: `${dosCifras(h)}:00`, hasta: `${dosCifras(h + 4)}:00` })
  }
}

/** Duración entre dos instantes en minutos (o null). */
export function minutosEntre(desde: string | null | undefined, hasta: string | null | undefined): number | null {
  if (!desde || !hasta) return null
  const ms = new Date(hasta).getTime() - new Date(desde).getTime()
  return Number.isFinite(ms) && ms >= 0 ? ms / 60_000 : null
}
