/**
 * Periodo libre en informes (16-11-2026). Lógica pura del selector de periodo:
 * accesos rápidos, rango, granularidad `auto` (igual que `app/core/periodo.py`),
 * parámetros para la API, parámetros para la URL y formato del eje temporal.
 *
 * Contrato con la API (todos los informes migrados):
 *   desde / hasta  ISO 8601 con desfase, `[desde, hasta)`
 *   days           últimos N días (accesos rápidos móviles: la clave de la
 *                  consulta no cambia cada minuto)
 *   granularidad   auto | hour | day | week | month
 *   tz             zona IANA del usuario (la del navegador, con la que se pintan
 *                  todas las fechas de la app)
 *   comparar       true para pedir también el periodo anterior
 */
import { formateadorDeFecha } from './helpers'

export type Granularidad = 'hour' | 'day' | 'week' | 'month'
export type GranularidadPedida = Granularidad | 'auto'
export type ClavePreset = 'hoy' | '24h' | '7d' | '30d' | '90d' | 'mes' | 'trimestre' | 'anio'
  | 'prox7d' | 'prox30d' | 'prox90d' | 'prox180d' | 'prox365d' | 'custom'
/** `pasado`: informes («últimos N días»); `futuro`: horizontes (vencimientos, renovaciones). */
export type SentidoPeriodo = 'pasado' | 'futuro'

export const GRANULARIDADES: Granularidad[] = ['hour', 'day', 'week', 'month']
/** Dato con instante (tickets, eventos, accesos, uso, IA…). */
export const CON_HORA: Granularidad[] = GRANULARIDADES
/** Dato por día de calendario (imputaciones, gastos, facturas…). */
export const SIN_HORA: Granularidad[] = ['day', 'week', 'month']
/** Dato mensual (presupuestos, cierres). */
export const SOLO_MES: Granularidad[] = ['month']

/** Orden con el que se ofrecen los accesos rápidos. */
export const PRESETS: Exclude<ClavePreset, 'custom'>[] = ['hoy', '24h', '7d', '30d', '90d', 'mes', 'trimestre', 'anio']
/** Accesos rápidos de un horizonte hacia delante (`sentido: 'futuro'`). */
export const PRESETS_FUTURO: Exclude<ClavePreset, 'custom'>[] = ['prox7d', 'prox30d', 'prox90d', 'prox180d', 'prox365d']
/** Accesos rápidos que son «los últimos N días» (van como `days`). */
const DIAS_MOVILES: Partial<Record<ClavePreset, number>> = { '24h': 1, '7d': 7, '30d': 30, '90d': 90 }
/** Accesos rápidos que son «los próximos N días» (van como `days`; la API los toma hacia delante). */
const DIAS_FUTUROS: Partial<Record<ClavePreset, number>> = { prox7d: 7, prox30d: 30, prox90d: 90, prox180d: 180, prox365d: 365 }

export interface ValorPeriodo {
  preset: ClavePreset
  /** Solo `custom`: ISO con desfase. */
  desde?: string
  hasta?: string
  granularidad: GranularidadPedida
  comparar: boolean
}

export interface LimitesPeriodo {
  max_dias: number
  max_puntos: Record<Granularidad, number>
  auto_max_puntos: number
}

/** Los mismos valores por defecto que `LimitesDePeriodo` del backend. */
export const LIMITES_POR_DEFECTO: LimitesPeriodo = {
  max_dias: 1830,
  max_puntos: { hour: 744, day: 1100, week: 530, month: 240 },
  auto_max_puntos: 120,
}

const SEGUNDOS: Record<Granularidad, number> = { hour: 3600, day: 86400, week: 7 * 86400, month: 30.4375 * 86400 }

export function zonaDelUsuario(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch { return 'UTC' }
}

const dos = (n: number) => String(n).padStart(2, '0')

/** ISO 8601 con el desfase local (`2026-11-16T08:00:00+01:00`). */
export function isoConDesfase(d: Date): string {
  const off = -d.getTimezoneOffset()
  const signo = off >= 0 ? '+' : '-'
  const abs = Math.abs(off)
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}T${dos(d.getHours())}:${dos(d.getMinutes())}:${dos(d.getSeconds())}${signo}${dos(Math.floor(abs / 60))}:${dos(abs % 60)}`
}

/** Valor de un `<input type="datetime-local">` (hora local). */
export function aInputFechaHora(d: Date): string {
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}T${dos(d.getHours())}:${dos(d.getMinutes())}`
}
/** Valor de un `<input type="date">` (día local). */
export function aInputFecha(d: Date): string {
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`
}
/** `YYYY-MM-DD` o `YYYY-MM-DDTHH:MM` local → Date. Inválido → null. */
export function deInput(v: string | undefined | null): Date | null {
  if (!v) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?$/.exec(v)
  if (!m) { const d = new Date(v); return isNaN(d.getTime()) ? null : d }
  return new Date(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 0, m[5] ? +m[5] : 0)
}

function inicioDelDia(d: Date): Date { return new Date(d.getFullYear(), d.getMonth(), d.getDate()) }

/** Inicio del acceso rápido de calendario (hoy, mes, trimestre, año). */
function inicioDePreset(p: ClavePreset, ahora: Date): Date | null {
  switch (p) {
    case 'hoy': return inicioDelDia(ahora)
    case 'mes': return new Date(ahora.getFullYear(), ahora.getMonth(), 1)
    case 'trimestre': return new Date(ahora.getFullYear(), Math.floor(ahora.getMonth() / 3) * 3, 1)
    case 'anio': return new Date(ahora.getFullYear(), 0, 1)
    default: return null
  }
}

/** Rango efectivo `[desde, hasta)` de un valor, a la fecha `ahora`. */
export function rangoDe(v: ValorPeriodo, ahora: Date = new Date()): { desde: Date; hasta: Date } {
  const dias = DIAS_MOVILES[v.preset]
  if (dias) return { desde: new Date(ahora.getTime() - dias * 86400000), hasta: ahora }
  const futuros = DIAS_FUTUROS[v.preset]
  if (futuros) return { desde: ahora, hasta: new Date(ahora.getTime() + futuros * 86400000) }
  const inicio = inicioDePreset(v.preset, ahora)
  if (inicio) return { desde: inicio, hasta: ahora }
  const desde = v.desde ? new Date(v.desde) : new Date(ahora.getTime() - 30 * 86400000)
  const hasta = v.hasta ? new Date(v.hasta) : ahora
  return { desde, hasta }
}

export function puntos(desde: Date, hasta: Date, g: Granularidad): number {
  return Math.max(1, Math.ceil((hasta.getTime() - desde.getTime()) / 1000 / SEGUNDOS[g]))
}

/** La misma regla que `resolver_granularidad` del backend. */
export function resolverGranularidad(
  desde: Date, hasta: Date, pedida: GranularidadPedida, admitidas: Granularidad[],
  limites: LimitesPeriodo = LIMITES_POR_DEFECTO,
): Granularidad {
  const orden = GRANULARIDADES.filter(g => admitidas.includes(g))
  const lista = orden.length ? orden : GRANULARIDADES
  if (pedida !== 'auto' && lista.includes(pedida)) return pedida
  for (const g of lista) if (puntos(desde, hasta, g) <= limites.auto_max_puntos) return g
  return lista[lista.length - 1]
}

export type ErrorDeValidacion =
  | { codigo: 'desde_mayor_que_hasta' }
  | { codigo: 'rango_excedido'; maximo: number; dias: number }
  | { codigo: 'demasiados_puntos'; maximo: number; puntos: number; granularidad: Granularidad }
  | { codigo: 'fecha_invalida' }

/** Lo mismo que rechazaría la API, para avisar antes de pedir. */
export function validarPeriodo(
  v: ValorPeriodo, admitidas: Granularidad[], limites: LimitesPeriodo = LIMITES_POR_DEFECTO, ahora = new Date(),
): ErrorDeValidacion | null {
  if (v.preset === 'custom' && (!v.desde || isNaN(new Date(v.desde).getTime()) || (v.hasta && isNaN(new Date(v.hasta).getTime())))) {
    return { codigo: 'fecha_invalida' }
  }
  const { desde, hasta } = rangoDe(v, ahora)
  if (v.preset === 'custom' && desde.getTime() >= hasta.getTime()) return { codigo: 'desde_mayor_que_hasta' }
  const dias = (hasta.getTime() - desde.getTime()) / 86400000
  if (dias > limites.max_dias + 1e-9) return { codigo: 'rango_excedido', maximo: limites.max_dias, dias: Math.ceil(dias) }
  const g = resolverGranularidad(desde, hasta, v.granularidad, admitidas, limites)
  const n = puntos(desde, hasta, g)
  const tope = limites.max_puntos[g]
  if (tope && n > tope) return { codigo: 'demasiados_puntos', maximo: tope, puntos: n, granularidad: g }
  return null
}

export interface ParamsPeriodoApi {
  desde?: string
  hasta?: string
  days?: number
  granularidad: GranularidadPedida
  tz: string
  comparar?: boolean
}

/**
 * Parámetros para la API. Estables mientras no cambie la elección: los
 * accesos móviles van como `days` y los de calendario solo con `desde` (el
 * servidor pone `hasta = ahora`), así la clave de React Query no cambia sola.
 */
export function paramsDeApi(v: ValorPeriodo, ahora: Date = new Date(), conGranularidad = true): ParamsPeriodoApi {
  const base: ParamsPeriodoApi = { granularidad: conGranularidad ? v.granularidad : 'auto', tz: zonaDelUsuario() }
  if (v.comparar) base.comparar = true
  const dias = DIAS_MOVILES[v.preset] ?? DIAS_FUTUROS[v.preset]
  if (dias) return { ...base, days: dias }
  const inicio = inicioDePreset(v.preset, ahora)
  if (inicio) return { ...base, desde: isoConDesfase(inicio) }
  return { ...base, desde: v.desde, ...(v.hasta ? { hasta: v.hasta } : {}) }
}

/**
 * Para APIs que todavía filtran por día (`YYYY-MM-DD`, ambos incluidos):
 * el último día es el de `hasta − 1 ms` (`hasta` es exclusivo).
 */
export function fechasDe(v: ValorPeriodo, ahora: Date = new Date()): { desde: string; hasta: string } {
  const { desde, hasta } = rangoDe(v, ahora)
  return { desde: aInputFecha(desde), hasta: aInputFecha(new Date(hasta.getTime() - 1)) }
}

// ── URL ───────────────────────────────────────────────────────────────────────
export const CLAVES_URL = ['periodo', 'desde', 'hasta', 'granularidad', 'comparar'] as const

export function deUrl(sp: URLSearchParams, defecto: ValorPeriodo, prefijo = ''): ValorPeriodo {
  const k = (c: string) => `${prefijo}${c}`
  const preset = sp.get(k('periodo')) as ClavePreset | null
  const gran = sp.get(k('granularidad')) as GranularidadPedida | null
  const valido = preset && (PRESETS as string[]).concat(PRESETS_FUTURO, 'custom').includes(preset)
  const v: ValorPeriodo = {
    preset: valido ? preset : defecto.preset,
    granularidad: gran && (['auto', ...GRANULARIDADES] as string[]).includes(gran) ? gran : defecto.granularidad,
    comparar: sp.has(k('comparar')) ? sp.get(k('comparar')) === '1' : defecto.comparar,
  }
  if (v.preset === 'custom') {
    v.desde = sp.get(k('desde')) || defecto.desde
    v.hasta = sp.get(k('hasta')) || defecto.hasta
    if (!v.desde) return { ...defecto }
  }
  return v
}

/** Escribe el valor en la query string sin tocar el resto de parámetros. */
export function aUrl(sp: URLSearchParams, v: ValorPeriodo, defecto: ValorPeriodo, prefijo = ''): URLSearchParams {
  const out = new URLSearchParams(sp)
  const k = (c: string) => `${prefijo}${c}`
  CLAVES_URL.forEach(c => out.delete(k(c)))
  const esDefecto = v.preset === defecto.preset && v.preset !== 'custom'
    && v.granularidad === defecto.granularidad && v.comparar === defecto.comparar
  if (esDefecto) return out
  out.set(k('periodo'), v.preset)
  if (v.preset === 'custom') {
    if (v.desde) out.set(k('desde'), v.desde)
    if (v.hasta) out.set(k('hasta'), v.hasta)
  }
  if (v.granularidad !== 'auto') out.set(k('granularidad'), v.granularidad)
  if (v.comparar) out.set(k('comparar'), '1')
  return out
}

// ── Eje temporal ──────────────────────────────────────────────────────────────
const FORMATO_TRAMO: Record<Granularidad, Intl.DateTimeFormatOptions> = {
  hour: { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' },
  day: { day: '2-digit', month: 'short' },
  week: { day: '2-digit', month: 'short' },
  month: { month: 'short', year: 'numeric' },
}
const FORMATO_TRAMO_LARGO: Record<Granularidad, Intl.DateTimeFormatOptions> = {
  hour: { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' },
  day: { weekday: 'short', day: '2-digit', month: 'long', year: 'numeric' },
  week: { day: '2-digit', month: 'long', year: 'numeric' },
  month: { month: 'long', year: 'numeric' },
}

/** Etiqueta del eje de un tramo (`t` ISO, o la `clave` `YYYY-MM-DDTHH:MM` local). */
export function formatearTramo(t: string | Date | null | undefined, g: Granularidad, largo = false): string {
  if (!t) return ''
  const d = t instanceof Date ? t : (/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(t) ? deInput(t) : new Date(t))
  if (!d || isNaN(d.getTime())) return String(t)
  return formateadorDeFecha((largo ? FORMATO_TRAMO_LARGO : FORMATO_TRAMO)[g]).format(d)
}

/** Código de error de periodo devuelto por la API (`detail.code = periodo.<motivo>`), o null. */
export function codigoDeErrorDePeriodo(e: unknown): { motivo: string; params: Record<string, unknown> } | null {
  const d = (e as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const o = d as { code?: string; params?: Record<string, unknown> }
    if (typeof o.code === 'string' && o.code.startsWith('periodo.')) return { motivo: o.code.slice(8), params: o.params ?? {} }
  }
  return null
}
