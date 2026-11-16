/**
 * Fechas del selector propio del kit (16-11-2026). Lógica pura, sin React:
 * el patrón de escritura de cada idioma (sale del formateador de la app), la
 * máscara al teclear, la validación, la rejilla del calendario, el primer día
 * de la semana y la conversión entre zonas.
 *
 * Por qué: el `<input type="date">` nativo pinta mm/dd/aaaa, dd/mm/aaaa o lo
 * que diga la región del navegador o del sistema, no el idioma de la app. Con
 * esto una fecha se escribe y se ve igual para todos los que usan el mismo
 * idioma, en cualquier navegador.
 *
 * Valores (los mismos que daban los controles nativos, para no tocar a nadie):
 *   fecha        'YYYY-MM-DD'
 *   fecha y hora 'YYYY-MM-DDTHH:MM'  (hora de pared; con `zona`, ISO con desfase)
 *   hora         'HH:MM'
 */
import { formateadorDeFecha, idiomaActivo } from './helpers'

export type ModoFecha = 'fecha' | 'fechaHora' | 'hora'

export interface Pared { y: number; m: number; d: number; h: number; mi: number }

type TipoParte = 'day' | 'month' | 'year'
export interface PatronDeFecha {
  /** Campos en el orden del idioma. */
  orden: TipoParte[]
  /** Literal tras cada campo ('' tras el último si no hay). */
  separadores: string[]
  /** Literal antes del primer campo (raro, pero existe en algunos idiomas). */
  prefijo: string
  /** Si día y mes se escriben con dos cifras (es/en) o sin relleno (zh). */
  relleno: boolean
  /** Texto de ayuda: dd/mm/aaaa, mm/dd/aaaa, aaaa年m月d日… (letras del idioma de la app). */
  marcador: string
}

/** Opciones del formateador de la app para la fecha corta de cada idioma. */
function opcionesDeFecha(lang: string): Intl.DateTimeFormatOptions {
  return lang.startsWith('zh')
    ? { year: 'numeric', month: 'long', day: 'numeric' }
    : { day: '2-digit', month: '2-digit', year: 'numeric' }
}

const LETRAS: Record<string, Record<TipoParte, string>> = {
  es: { day: 'd', month: 'm', year: 'a' },
  en: { day: 'd', month: 'm', year: 'y' },
  zh: { day: 'd', month: 'm', year: 'y' },
}

const _patrones = new Map<string, PatronDeFecha>()

/** Patrón de escritura del idioma, deducido del formateador de fechas de la app. */
export function patronDeFecha(lang: string = idiomaActivo()): PatronDeFecha {
  const cache = _patrones.get(lang)
  if (cache) return cache
  // 2 de enero de 2006: día y mes de una cifra dicen si el idioma rellena.
  const partes = formateadorDeFecha({ ...opcionesDeFecha(lang), timeZone: 'UTC' }, lang)
    .formatToParts(new Date(Date.UTC(2006, 0, 2)))
  const orden: TipoParte[] = []
  const separadores: string[] = []
  let prefijo = ''
  let relleno = true
  let mesNumerico = true
  for (const p of partes) {
    if (p.type === 'day' || p.type === 'month' || p.type === 'year') {
      if (p.type === 'month' && !/^\d+$/.test(p.value)) mesNumerico = false
      if ((p.type === 'day' || p.type === 'month') && p.value.length === 1) relleno = false
      orden.push(p.type)
      separadores.push('')
    } else if (p.type === 'literal') {
      if (orden.length === 0) prefijo += p.value
      else separadores[separadores.length - 1] += p.value
    }
  }
  let patron: PatronDeFecha
  if (orden.length !== 3 || !mesNumerico) {
    patron = { orden: ['day', 'month', 'year'], separadores: ['/', '/', ''], prefijo: '', relleno: true, marcador: '' }
  } else {
    patron = { orden, separadores, prefijo, relleno, marcador: '' }
  }
  const letras = LETRAS[lang.slice(0, 2)] ?? LETRAS.en
  patron.marcador = patron.prefijo + patron.orden.map((t, i) => {
    const n = t === 'year' ? 4 : patron.relleno ? 2 : 1
    return letras[t].repeat(n) + patron.separadores[i]
  }).join('')
  _patrones.set(lang, patron)
  return patron
}

const dos = (n: number) => String(n).padStart(2, '0')
const cuatro = (n: number) => String(n).padStart(4, '0')

export function diasDelMes(y: number, m: number): number {
  return new Date(Date.UTC(y, m, 0)).getUTCDate()
}

export function esFechaValida(y: number, m: number, d: number): boolean {
  return y >= 1 && y <= 9999 && m >= 1 && m <= 12 && d >= 1 && d <= diasDelMes(y, m)
}

// ── Valores (ISO) ─────────────────────────────────────────────────────────────
export function isoFecha(p: Pick<Pared, 'y' | 'm' | 'd'>): string { return `${cuatro(p.y)}-${dos(p.m)}-${dos(p.d)}` }
export function isoHora(p: Pick<Pared, 'h' | 'mi'>): string { return `${dos(p.h)}:${dos(p.mi)}` }
export function isoFechaHora(p: Pared): string { return `${isoFecha(p)}T${isoHora(p)}` }

/** 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM[:SS]' o 'HH:MM' → pared. Inválido → null. */
export function leerValor(v: string | null | undefined, modo: ModoFecha): Pared | null {
  if (!v) return null
  if (modo === 'hora') {
    const m = /^(\d{1,2}):(\d{2})/.exec(v)
    if (!m) return null
    const h = +m[1], mi = +m[2]
    return h < 24 && mi < 60 ? { y: 2000, m: 1, d: 1, h, mi } : null
  }
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(v)
  if (!m) return null
  const p = { y: +m[1], m: +m[2], d: +m[3], h: m[4] ? +m[4] : 0, mi: m[5] ? +m[5] : 0 }
  return esFechaValida(p.y, p.m, p.d) && p.h < 24 && p.mi < 60 ? p : null
}

export function valorDe(p: Pared, modo: ModoFecha): string {
  return modo === 'hora' ? isoHora(p) : modo === 'fechaHora' ? isoFechaHora(p) : isoFecha(p)
}

/** Compara solo hasta la precisión del modo. */
export function comparar(a: Pared, b: Pared, modo: ModoFecha = 'fechaHora'): number {
  const clave = (p: Pared) => modo === 'hora' ? p.h * 60 + p.mi
    : modo === 'fecha' ? (p.y * 13 + p.m) * 32 + p.d
      : ((((p.y * 13 + p.m) * 32 + p.d) * 24 + p.h) * 60 + p.mi)
  return clave(a) - clave(b)
}

// ── Texto visible ─────────────────────────────────────────────────────────────
export function textoDeFecha(p: Pick<Pared, 'y' | 'm' | 'd'>, patron: PatronDeFecha = patronDeFecha()): string {
  const campo = (t: TipoParte) => t === 'year' ? cuatro(p.y)
    : t === 'month' ? (patron.relleno ? dos(p.m) : String(p.m))
      : (patron.relleno ? dos(p.d) : String(p.d))
  return patron.prefijo + patron.orden.map((t, i) => campo(t) + patron.separadores[i]).join('')
}

export function textoDe(p: Pared | null, modo: ModoFecha, patron: PatronDeFecha = patronDeFecha()): string {
  if (!p) return ''
  if (modo === 'hora') return isoHora(p)
  if (modo === 'fechaHora') return `${textoDeFecha(p, patron)} ${isoHora(p)}`
  return textoDeFecha(p, patron)
}

export function marcadorDe(modo: ModoFecha, patron: PatronDeFecha = patronDeFecha()): string {
  if (modo === 'hora') return 'hh:mm'
  return modo === 'fechaHora' ? `${patron.marcador} hh:mm` : patron.marcador
}

/**
 * Máscara al teclear: se quedan las cifras y se ponen los separadores del
 * idioma según se completa cada campo (año 4 cifras; día, mes, hora y minuto 2).
 */
export function enmascarar(texto: string, modo: ModoFecha, patron: PatronDeFecha = patronDeFecha()): string {
  const cifras = texto.replace(/\D/g, '')
  const huecos: { n: number; tras: string }[] = []
  if (modo !== 'hora') {
    patron.orden.forEach((t, i) => huecos.push({ n: t === 'year' ? 4 : 2, tras: patron.separadores[i] }))
    if (modo === 'fechaHora') {
      if (!huecos[huecos.length - 1].tras) huecos[huecos.length - 1].tras = ' '
      else huecos[huecos.length - 1].tras += ' '
    }
  }
  if (modo !== 'fecha') huecos.push({ n: 2, tras: ':' }, { n: 2, tras: '' })
  let salida = modo === 'hora' ? '' : patron.prefijo
  let i = 0
  for (let h = 0; h < huecos.length && i < cifras.length; h++) {
    const trozo = cifras.slice(i, i + huecos[h].n)
    i += trozo.length
    salida += trozo
    // El separador sale cuando ya hay cifras del campo siguiente: así borrar
    // hacia atrás nunca choca con un separador que vuelve a aparecer.
    if (trozo.length === huecos[h].n && i < cifras.length) salida += huecos[h].tras
  }
  return salida
}

/** Texto escrito → pared (completo y válido), o null. Acepta día/mes de 1 cifra con separadores. */
export function leerTexto(texto: string, modo: ModoFecha, patron: PatronDeFecha = patronDeFecha()): Pared | null {
  const grupos = (texto.match(/\d+/g) ?? []).map(Number)
  const cadenas = texto.match(/\d+/g) ?? []
  let h = 0, mi = 0, y = 2000, m = 1, d = 1
  if (modo !== 'hora') {
    if (grupos.length < 3) return null
    const anioIdx = patron.orden.indexOf('year')
    if (cadenas[anioIdx]?.length !== 4) return null
    patron.orden.forEach((t, i) => { if (t === 'year') y = grupos[i]; else if (t === 'month') m = grupos[i]; else d = grupos[i] })
    if (!esFechaValida(y, m, d)) return null
  }
  if (modo !== 'fecha') {
    const base = modo === 'hora' ? 0 : 3
    if (grupos.length < base + 2) return null
    h = grupos[base]; mi = grupos[base + 1]
    if (h > 23 || mi > 59) return null
  }
  if (grupos.length > (modo === 'fecha' ? 3 : modo === 'hora' ? 2 : 5)) return null
  return { y, m, d, h, mi }
}

// ── Calendario ────────────────────────────────────────────────────────────────
/** 0 = domingo … 6 = sábado. Del idioma (Intl.Locale.weekInfo) o, si no, en → domingo, resto → lunes. */
export function primerDiaDeSemana(lang: string = idiomaActivo()): number {
  try {
    const loc = new Intl.Locale(lang === 'en' ? 'en-US' : lang === 'zh' ? 'zh-CN' : lang) as Intl.Locale & {
      weekInfo?: { firstDay: number }; getWeekInfo?: () => { firstDay: number }
    }
    const info = loc.getWeekInfo?.() ?? loc.weekInfo
    if (info?.firstDay) return info.firstDay % 7
  } catch { /* motor sin weekInfo */ }
  return lang.startsWith('en') ? 0 : 1
}

export interface Celda { y: number; m: number; d: number; delMes: boolean }

/** Seis semanas que cubren el mes, empezando por el primer día de semana del idioma. */
export function rejillaDelMes(y: number, m: number, primerDia: number): Celda[][] {
  const inicioSemana = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() - primerDia + 7) % 7
  const base = Date.UTC(y, m - 1, 1 - inicioSemana)
  const semanas: Celda[][] = []
  for (let s = 0; s < 6; s++) {
    const fila: Celda[] = []
    for (let k = 0; k < 7; k++) {
      const f = new Date(base + (s * 7 + k) * 86400000)
      fila.push({ y: f.getUTCFullYear(), m: f.getUTCMonth() + 1, d: f.getUTCDate(), delMes: f.getUTCMonth() + 1 === m })
    }
    semanas.push(fila)
  }
  return semanas
}

/** Suma días/meses/años a una fecha (el día se ajusta al último del mes si hace falta). */
export function moverFecha(p: Pared, unidad: 'dia' | 'mes' | 'anio', n: number): Pared {
  if (unidad === 'dia') {
    const f = new Date(Date.UTC(p.y, p.m - 1, p.d + n))
    return { ...p, y: f.getUTCFullYear(), m: f.getUTCMonth() + 1, d: f.getUTCDate() }
  }
  const meses = unidad === 'mes' ? n : n * 12
  const total = p.y * 12 + (p.m - 1) + meses
  const y = Math.floor(total / 12), m = (total % 12) + 1
  return { ...p, y, m, d: Math.min(p.d, diasDelMes(y, m)) }
}

/** Día de la semana (0 = domingo) de una fecha. */
export function diaDeSemana(p: Pick<Pared, 'y' | 'm' | 'd'>): number {
  return new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay()
}

/** Nombres cortos de los días, empezando por `primerDia`, en el idioma de la app. */
export function nombresDeDias(primerDia: number, lang: string = idiomaActivo(), estilo: 'short' | 'long' | 'narrow' = 'short'): string[] {
  const f = formateadorDeFecha({ weekday: estilo, timeZone: 'UTC' }, lang)
  // 2006-01-01 fue domingo
  return Array.from({ length: 7 }, (_, i) => f.format(new Date(Date.UTC(2006, 0, 1 + ((primerDia + i) % 7)))))
}

export function nombresDeMeses(lang: string = idiomaActivo()): string[] {
  const f = formateadorDeFecha({ month: 'long', timeZone: 'UTC' }, lang)
  return Array.from({ length: 12 }, (_, i) => f.format(new Date(Date.UTC(2006, i, 15))))
}

/** Etiqueta accesible de un día («lunes, 16 de noviembre de 2026»). */
export function etiquetaDeDia(p: Pick<Pared, 'y' | 'm' | 'd'>, lang: string = idiomaActivo()): string {
  return formateadorDeFecha({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }, lang)
    .format(new Date(Date.UTC(p.y, p.m - 1, p.d)))
}

// ── Zonas ─────────────────────────────────────────────────────────────────────
export function zonaDelNavegador(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch { return 'UTC' }
}

const _fmtZona = new Map<string, Intl.DateTimeFormat>()
function fmtZona(zona: string): Intl.DateTimeFormat {
  let f = _fmtZona.get(zona)
  if (!f) {
    try {
      f = new Intl.DateTimeFormat('en-US', { timeZone: zona, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      f = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
    }
    _fmtZona.set(zona, f)
  }
  return f
}

/** Hora de pared de un instante en una zona IANA. */
export function paredEnZona(instante: Date, zona: string): Pared {
  const o: Record<string, number> = {}
  for (const p of fmtZona(zona).formatToParts(instante)) if (p.type !== 'literal') o[p.type] = +p.value
  return { y: o.year, m: o.month, d: o.day, h: o.hour % 24, mi: o.minute }
}

/** Desfase (minutos) de la zona en ese instante. */
export function desfaseEnZona(instante: Date, zona: string): number {
  const p = paredEnZona(instante, zona)
  const comoUtc = Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi)
  return Math.round((comoUtc - Math.floor(instante.getTime() / 60000) * 60000) / 60000)
}

/** Instante de una hora de pared en una zona (en un hueco de cambio de hora, la hora siguiente válida). */
export function instanteEnZona(p: Pared, zona: string): Date {
  const comoUtc = Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi)
  let t = comoUtc - desfaseEnZona(new Date(comoUtc), zona) * 60000
  t = comoUtc - desfaseEnZona(new Date(t), zona) * 60000
  return new Date(t)
}

/** ISO con el desfase de la zona: '2026-11-16T08:00:00+01:00'. */
export function isoEnZona(instante: Date, zona: string): string {
  const p = paredEnZona(instante, zona)
  const off = desfaseEnZona(instante, zona)
  const abs = Math.abs(off)
  return `${isoFechaHora(p)}:00${off >= 0 ? '+' : '-'}${dos(Math.floor(abs / 60))}:${dos(abs % 60)}`
}

/** Hoy (y ahora) en la zona. */
export function ahoraEnZona(zona: string = zonaDelNavegador(), ahora: Date = new Date()): Pared {
  return paredEnZona(ahora, zona)
}
