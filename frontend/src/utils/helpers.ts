import { formatDistanceToNow } from 'date-fns'
import { es, enUS, zhCN } from 'date-fns/locale'
import type { Locale } from 'date-fns'

export type DateInput = Date | string | number | null | undefined
export type Maybe<T> = T | null | undefined

// ── Date helpers ──────────────────────────────────────────────────────────────
// Las fechas salen en el idioma activo de la interfaz (es, en, zh), con el
// orden y los nombres que tocan en cada uno, y la zona horaria del navegador.

/** La clave con la que AppLangProvider recuerda el idioma. */
const CLAVE_IDIOMA = 'contecflow_operator_lang'

/** Idioma activo leído sin hooks: sirve en formateadores y en boundaries. */
export function idiomaActivo(): string {
  try {
    return localStorage.getItem(CLAVE_IDIOMA) || 'es'
  } catch {
    return 'es'   // almacenamiento bloqueado: castellano y seguir
  }
}

const _locales = new Map<string, string>()

/**
 * Locale para `Intl.*` y `toLocale*String`: el idioma activo, o el que se le
 * pase. Un valor que el navegador no reconoce cae a castellano en vez de
 * lanzar RangeError en mitad del render.
 */
export function localeActivo(lang: string = idiomaActivo()): string {
  let l = _locales.get(lang)
  if (l === undefined) {
    try { l = Intl.getCanonicalLocales(lang)[0] ?? 'es' } catch { l = 'es' }
    _locales.set(lang, l)
  }
  return l
}

const FORMATOS: Record<'date' | 'datetime' | 'month', Intl.DateTimeFormatOptions> = {
  date:     { day: '2-digit', month: '2-digit', year: 'numeric' },
  datetime: { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' },
  month:    { month: 'long', year: 'numeric' },
}
const _formateadores = new Map<string, Intl.DateTimeFormat>()

/** Intl.DateTimeFormat del idioma activo, uno por idioma y formato. */
export function formateadorDeFecha(opciones: Intl.DateTimeFormatOptions, lang = idiomaActivo()): Intl.DateTimeFormat {
  const clave = lang + JSON.stringify(opciones)
  let f = _formateadores.get(clave)
  if (!f) {
    try { f = new Intl.DateTimeFormat(lang, opciones) } catch { f = new Intl.DateTimeFormat('es', opciones) }
    _formateadores.set(clave, f)
  }
  return f
}

const LOCALES_DATE_FNS: Record<string, Locale> = { es, en: enUS, zh: zhCN }

export const fmtDate     = (d: DateInput): string => d ? formateadorDeFecha(FORMATOS.date).format(new Date(d)) : '—'
export const fmtDateTime = (d: DateInput): string => d ? formateadorDeFecha(FORMATOS.datetime).format(new Date(d)) : '—'
export const fmtRelative = (d: DateInput): string => d
  ? formatDistanceToNow(new Date(d), { addSuffix: true, locale: LOCALES_DATE_FNS[idiomaActivo()] ?? es })
  : '—'
export const fmtMonth    = (d: DateInput): string => d ? formateadorDeFecha(FORMATOS.month).format(new Date(d)) : '—'

// ── Number helpers ────────────────────────────────────────────────────────────
// Separadores de miles y decimales del idioma activo; la moneda es la que se
// pase, el idioma sólo cambia cómo se escribe.
export const fmtCurrency = (n: Maybe<number>, currency?: string | null): string => {
  if (!currency) return new Intl.NumberFormat(localeActivo(), { maximumFractionDigits: 0 }).format(n ?? 0)
  return formatearMoneda(n, currency, { decimales: 0 })
}

// ── Moneda ────────────────────────────────────────────────────────────────────
// Auditoria 2026-11 (#18): EL formateador de importes. La moneda es la del dato
// (factura, gasto...) o, si no trae, la de la empresa (`useFormatoMoneda()`, que
// lee useOrgSettings().currency); nunca un '€' o 'EUR' escrito en la pantalla.
export interface OpcionesMoneda {
  /** Decimales fijos (min = max). Sin ellos, los de la moneda (2 en EUR/USD). */
  decimales?: number
  /** Notacion compacta: 12,3 mil €. */
  compacto?: boolean
}
const _monedas = new Map<string, Intl.NumberFormat>()
function formateadorDeMoneda(moneda: string, op: OpcionesMoneda = {}): Intl.NumberFormat {
  const lang = localeActivo()
  const clave = `${lang}|${moneda}|${op.decimales ?? ''}|${op.compacto ? 1 : 0}`
  let f = _monedas.get(clave)
  if (!f) {
    const o: Intl.NumberFormatOptions = { style: 'currency', currency: moneda }
    if (op.decimales != null) { o.minimumFractionDigits = op.decimales; o.maximumFractionDigits = op.decimales }
    if (op.compacto) { o.notation = 'compact'; o.maximumFractionDigits = op.decimales ?? 1 }
    try { f = new Intl.NumberFormat(lang, o) } catch { f = new Intl.NumberFormat(lang, { ...o, currency: 'EUR' }) }
    _monedas.set(clave, f)
  }
  return f
}

/** Importe con su moneda en el idioma activo. `null`/`undefined`/NaN -> '—'. */
export function formatearMoneda(n: Maybe<number | string>, moneda: string, op: OpcionesMoneda = {}): string {
  if (n == null || n === '' || Number.isNaN(Number(n))) return '—'
  return formateadorDeMoneda(moneda || 'EUR', op).format(Number(n))
}

/** El simbolo de una moneda en el idioma activo ('€', 'US$', '£'...). */
export function simboloMoneda(moneda: string): string {
  const parte = formateadorDeMoneda(moneda || 'EUR', { decimales: 0 }).formatToParts(0).find((p) => p.type === 'currency')
  return parte?.value ?? moneda
}

export const fmtNumber = (n: Maybe<number>, decimals = 1): string =>
  (n ?? 0).toLocaleString(localeActivo(), { maximumFractionDigits: decimals })

export const fmtHours = (h: Maybe<number>): string => `${fmtNumber(h ?? 0, 1)}h`

export const fmtPct = (n: Maybe<number>): string => `${fmtNumber(n ?? 0, 1)}%`

// ── Color helpers ─────────────────────────────────────────────────────────────
export function loadColor(pct: number): string {
  if (pct > 100) return 'var(--danger)'
  if (pct > 85)  return 'var(--warning)'
  return 'var(--success)'
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export function riskColor(risk: Maybe<string>): string {
  const map: Record<RiskLevel, string> = {
    low: 'var(--success)',
    medium: 'var(--warning)',
    high: 'var(--danger)',
    critical: 'var(--danger)',
  }
  return (risk && (risk in map) ? map[risk as RiskLevel] : undefined) ?? 'var(--text-3)'
}

export function statusColor(status: Maybe<string>): string {
  const map: Record<string, string> = {
    active: 'var(--accent)', planning: 'var(--text-3)', paused: 'var(--warning)',
    closed: 'var(--success)', cancelled: 'var(--danger)',
    todo: 'var(--text-3)', in_progress: 'var(--accent)', done: 'var(--success)',
    blocked: 'var(--danger)', review: 'var(--warning)', backlog: 'var(--surface-5)',
  }
  return (status && map[status]) ?? 'var(--text-3)'
}

// ── File download helper ──────────────────────────────────────────────────────
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// ── Role helpers ──────────────────────────────────────────────────────────────
export const ROLE_LABELS: Record<string, string> = {
  admin: 'Dirección',
  pm: 'Project Manager',
  team_lead: 'Team Lead',
  hr: 'RRHH',
  employee: 'Empleado',
}

export const PRIORITY_LABELS: Record<string, string> = {
  critical: 'Crítica', high: 'Alta', medium: 'Normal', low: 'Baja',
}

export const STATUS_LABELS: Record<string, string> = {
  planning: 'Planificación', active: 'Activo', paused: 'Pausado',
  closed: 'Cerrado', cancelled: 'Cancelado',
  todo: 'Pendiente', in_progress: 'En curso', done: 'Completada',
  blocked: 'Bloqueada', in_review: 'En revisión', backlog: 'Backlog',
}

export const TYPE_LABELS: Record<string, string> = {
  development: 'Desarrollo', maintenance: 'Mantenimiento',
  rd: 'I+D', internal: 'Interno', consulting: 'Consultoría',
}

// ── Initials ──────────────────────────────────────────────────────────────────
export function initials(name = ''): string {
  return name.split(' ').slice(0, 2).map(w => w[0] ?? '').join('').toUpperCase()
}

// ── Normaliza errores de API (Pydantic 422 devuelve array de objetos) ──────────
// TODO type: shape inferred from axios + FastAPI Pydantic; refine to AxiosError<ApiError>
// once axios is migrated in a later batch.
interface PydanticIssue {
  loc?: unknown
  msg?: unknown
}

export function extractErr(e: unknown, fallback = 'Error inesperado'): string {
  const d = (e as { response?: { data?: { detail?: unknown } } } | null | undefined)?.response?.data?.detail
  if (!d) return fallback
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return (d as PydanticIssue[]).map((item) => {
      const field = Array.isArray(item?.loc) ? item.loc.slice(1).join('.') : ''
      const msg = typeof item?.msg === 'string' ? item.msg : ''
      return field ? `${field}: ${msg}` : msg
    }).filter(Boolean).join(' · ') || fallback
  }
  return String(d) || fallback
}
