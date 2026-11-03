/**
 * Shared constants, styles, and tiny presentational components
 * used across all ServiceDesk sub-modules.
 */
import { useState, useEffect } from 'react'
import { COLOR, alpha } from '../../constants/theme'
import { formateadorDeFecha } from '../../utils/helpers'
import { useAppT } from '../../i18n/AppLangContext'
import { traducirSinHook } from '../../i18n/traducirSinHook'

// ── Priority / Status maps ─────────────────────────────────────────────────────
export const PRIORITY_COLOR = {
  p1_critical: COLOR.danger,
  p2_high:     COLOR.orange,
  p3_medium:   COLOR.warning,
  p4_low:      COLOR.text2,
}
// Se traduce al leerlo, en el idioma activo. Auditoría 2026-11: eran literales
// en español y salían así también en inglés y en chino; con getters, los 25
// sitios que leen el mapa siguen igual.
const PRIORITY_KEY = { p1_critical: 'priority_p1', p2_high: 'priority_p2', p3_medium: 'priority_p3', p4_low: 'priority_p4' }
export const PRIORITY_LABEL: Record<string, string> = Object.defineProperties({}, Object.fromEntries(
  Object.entries(PRIORITY_KEY).map(([k, clave]) => [k, { enumerable: true, get: () => traducirSinHook(`service_desk.${clave}`) }]),
))
export const STATUS_COLOR = {
  new: COLOR.accent, assigned: COLOR.accent, in_progress: 'var(--sky-blue)',
  pending_client: COLOR.warning, pending_third: COLOR.warning,
  resolved: COLOR.success, closed: COLOR.text2, cancelled: COLOR.text3,
}

// ── Common inline style objects ────────────────────────────────────────────────
export const INPUT_STYLE = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '9px 13px',
  color: 'var(--text-1)',
  fontSize: "var(--text-base)",
  outline: 'none',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
}
export const LABEL_STYLE = {
  fontSize: "var(--text-xs)",
  fontWeight: 600,
  color: 'var(--text-2)',
  display: 'block',
  marginBottom: 5,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
}

// ── Formatters ─────────────────────────────────────────────────────────────────
const FORMATO_SD: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }

/** Día, mes abreviado y hora, en el idioma activo de la interfaz. */
export function fmtDate(d: string | number | Date | null | undefined) {
  if (!d) return '—'
  return formateadorDeFecha(FORMATO_SD).format(new Date(d))
}
export function fmtMinutes(m: number | null | undefined) {
  if (!m) return '—'
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60), min = Math.round(m % 60)
  return min > 0 ? `${h}h ${min}m` : `${h}h`
}

// ── Tiny badge components ──────────────────────────────────────────────────────
// `v` opcional (auditoría 2026-08, P1-10): el cuerpo ya resuelve el caso
// ausente con `|| COLOR.text2`, y las prioridades llegan como
// `string | undefined` desde la API. El tipo era más estrecho que el
// comportamiento real, igual que en los otros dos PBadge del módulo.
export function PBadge({ v }: { v?: string }) {
  const color = PRIORITY_COLOR[v as keyof typeof PRIORITY_COLOR] || COLOR.text2
  return (
    <span style={{
      fontSize: "var(--text-2xs)", fontWeight: 700, color,
      padding: '2px 7px', borderRadius: 4,
      border: `1px solid ${alpha(color, '30')}`, background: alpha(color, '12'),
      whiteSpace: 'nowrap',
    }}>
      {PRIORITY_LABEL[v as keyof typeof PRIORITY_LABEL] || v}
    </span>
  )
}
/** Estado del ticket → clave de traducción. Auditoría 2026-11: se pintaba el
 *  código tal cual («pending third», «in progress»). */
const STATUS_KEY: Record<string, string> = {
  new: 'status_new', assigned: 'status_assigned', in_progress: 'status_in_progress',
  pending_client: 'status_waiting_client', pending_third: 'status_pending_third',
  resolved: 'status_resolved', closed: 'status_closed', cancelled: 'status_cancelled',
}

/** Un código del Service Desk (estado de cambio, de problema...) en el idioma
 *  activo: `service_desk.<grupo>_<valor>`. Auditoría 2026-11: se pintaban
 *  con `.replace(/_/g, ' ')`, en inglés y en minúsculas. */
export function etiquetaSd(grupo: 'chg_st' | 'chg_type' | 'prb_st' | 'mi_st' | 'type', valor?: string | null): string {
  return valor ? traducirSinHook(`service_desk.${grupo}_${valor}`) : '—'
}

export function SBadge({ v }: { v: string }) {
  const t = useAppT()
  const color = STATUS_COLOR[v as keyof typeof STATUS_COLOR] || COLOR.text2
  return (
    <span style={{
      fontSize: "var(--text-2xs)", fontWeight: 600, color,
      padding: '2px 8px', borderRadius: 4,
      background: alpha(color, '15'), whiteSpace: 'nowrap',
    }}>
      {STATUS_KEY[v] ? t(`service_desk.${STATUS_KEY[v]}`) : v?.replace(/_/g, ' ')}
    </span>
  )
}

// ── useWindowWidth ─────────────────────────────────────────────────────────────
export function useWindowWidth() {
  const [width, setWidth] = useState(
    typeof window !== 'undefined' ? window.innerWidth : 1280,
  )
  useEffect(() => {
    const handler = () => setWidth(window.innerWidth)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return width
}
