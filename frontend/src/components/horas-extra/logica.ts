/**
 * Lógica pura de la pantalla de horas extra (18-11-2026): consumo frente a
 * límites y presupuestos, línea de tiempo ordenada por día, horas de una
 * franja, reglas que encajaron y CSV de nómina. Sin React: se prueba aparte.
 */
import type { EventoHe, FilaResumenHe, LimiteConsumido, PoliticaExplicada } from '../../services/api/horas-extra'

export type NivelDeConsumo = 'ok' | 'atencion' | 'excedido'

/** Umbrales del aviso de consumo: desde el 80 % atención, desde el 100 % excedido. */
export const UMBRAL_ATENCION = 80
export const UMBRAL_EXCEDIDO = 100

/** Porcentaje consumido (0 si no hay umbral). */
export function porcentaje(consumo: number, umbral: number): number {
  if (!umbral || umbral <= 0) return 0
  return Math.round((consumo / umbral) * 1000) / 10
}

export function nivelDeConsumo(pct: number): NivelDeConsumo {
  if (pct >= UMBRAL_EXCEDIDO) return 'excedido'
  if (pct >= UMBRAL_ATENCION) return 'atencion'
  return 'ok'
}

/** El porcentaje de un límite: consumo / umbral (no depende de si el `pct` del
 *  servidor viene en tanto por uno o por cien); sin umbral, el `pct` tal cual. */
export function pctDeLimite(l: Pick<LimiteConsumido, 'pct' | 'consumo' | 'umbral'>): number {
  if (l.umbral > 0) return porcentaje(l.consumo, l.umbral)
  return typeof l.pct === 'number' && Number.isFinite(l.pct) ? l.pct : 0
}

/** Porcentaje consumido de un presupuesto (horas − restantes) / horas. */
export function pctDePresupuesto(p: { horas: number; restantes: number } | null): number | null {
  if (!p || p.horas <= 0) return null
  return porcentaje(p.horas - p.restantes, p.horas)
}

/** El límite más apurado de una fila (o null si no hay ninguno). */
export function peorLimite(limites: LimiteConsumido[]): LimiteConsumido | null {
  return limites.reduce<LimiteConsumido | null>((peor, l) => (!peor || pctDeLimite(l) > pctDeLimite(peor) ? l : peor), null)
}

/** El nivel de una fila del resumen: el peor entre sus límites y su presupuesto. */
export function nivelDeFila(f: Pick<FilaResumenHe, 'limites' | 'presupuesto'>): NivelDeConsumo {
  const pcts = f.limites.map(pctDeLimite)
  const pp = pctDePresupuesto(f.presupuesto)
  if (pp !== null) pcts.push(pp)
  return nivelDeConsumo(pcts.length ? Math.max(...pcts) : 0)
}

export interface TotalesDeResumen {
  pedidas: number; aprobadas: number; pendientes: number; reales: number; sin_autorizar: number; a_pagar: number
}

/** Los totales de las filas del resumen (para las cifras de cabecera). */
export function totalesDeResumen(filas: FilaResumenHe[]): TotalesDeResumen {
  const t: TotalesDeResumen = { pedidas: 0, aprobadas: 0, pendientes: 0, reales: 0, sin_autorizar: 0, a_pagar: 0 }
  for (const f of filas) {
    t.pedidas += f.horas_pedidas
    t.aprobadas += f.horas_aprobadas
    t.pendientes += f.horas_pendientes
    t.reales += f.horas_reales
    t.sin_autorizar += f.horas_sin_autorizar
    t.a_pagar += f.horas_ponderadas_pago
  }
  for (const k of Object.keys(t) as Array<keyof TotalesDeResumen>) t[k] = Math.round(t[k] * 100) / 100
  return t
}

/** Línea de tiempo en orden (la más antigua arriba) y agrupada por día `YYYY-MM-DD`. */
export function lineaPorDia(eventos: EventoHe[]): Array<{ dia: string; eventos: EventoHe[] }> {
  const ordenados = [...eventos].sort((a, b) => a.cuando.localeCompare(b.cuando))
  const grupos: Array<{ dia: string; eventos: EventoHe[] }> = []
  for (const e of ordenados) {
    const dia = e.cuando.slice(0, 10)
    const ultimo = grupos[grupos.length - 1]
    if (ultimo && ultimo.dia === dia) ultimo.eventos.push(e)
    else grupos.push({ dia, eventos: [e] })
  }
  return grupos
}

/** Los datos libres de un evento como pares clave: valor (sin vacíos). */
export function paresDeDatos(datos: Record<string, unknown> | null | undefined): Array<[string, string]> {
  if (!datos) return []
  return Object.entries(datos)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)])
}

/** Horas entre dos 'HH:MM' (fin menor que inicio = cruza la medianoche); null si falta alguna. */
export function horasDeFranja(inicio: string | null | undefined, fin: string | null | undefined): number | null {
  const m = (x: string) => { const [h, mi] = x.split(':').map(Number); return h * 60 + (mi || 0) }
  if (!inicio || !fin || !/^\d{1,2}:\d{2}$/.test(inicio) || !/^\d{1,2}:\d{2}$/.test(fin)) return null
  let d = m(fin) - m(inicio)
  if (d <= 0) d += 24 * 60
  return Math.round((d / 60) * 100) / 100
}

/** Las políticas que aplicaron y, de cada una, las reglas que encajaron. */
export function reglasQueEncajan(explicacion: PoliticaExplicada[] | null | undefined): Array<{ politica: string; reglas: string[] }> {
  return (explicacion ?? []).filter(p => p.aplica)
    .map(p => ({ politica: p.politica, reglas: p.reglas.filter(r => r.cumple).map(r => r.regla) }))
}

/** Un CSV (coma, comillas dobles cuando hace falta, fin de línea CRLF). */
export function aCsv(cabecera: string[], filas: Array<Array<string | number | null | undefined>>): string {
  const celda = (v: string | number | null | undefined) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [cabecera, ...filas].map(f => f.map(celda).join(',')).join('\r\n')
}
