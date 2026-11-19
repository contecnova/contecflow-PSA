/**
 * Umbrales de semáforo: una definición por MÉTRICA (19-11-2026).
 *
 * Antes cada pantalla decidía sus cortes para la misma métrica (presupuesto
 * consumido a 70/90, 75/90, 85/100, >80 o >90; carga a 85/100, 80 o
 * 60/85/100; SLA a 70/90, 75/90 u 80/95). Ahora los cortes son ajustes por
 * empresa (Configuración › Configuración dinámica › Semáforos) que llegan por
 * `/settings/org-defaults` (`umbrales`) y se leen con `useUmbrales()`
 * (hooks/useOrgSettings.ts). El backend aplica los mismos con
 * `app/core/umbrales.py` (`tono_de`).
 *
 * Regla de los cortes (la misma en los dos lados):
 * - «más es peor» (presupuesto, carga, riesgo…): `danger` si valor > crítico,
 *   `warning` si valor > aviso (con `inclusivo`, ≥: riesgo y aprobaciones);
 * - «menos es peor» (SLA, OKR, NPS, margen, salud, EVM…): `danger` si
 *   valor < crítico, `warning` si valor < aviso (con `inclusivo`, ≤: días
 *   que faltan para un vencimiento).
 *
 * Valores por defecto = los más usados al medirlo (DOCS.md, «Umbrales de
 * semáforo»); se usan mientras no responde el servidor.
 */

export type Metrica =
  | 'presupuesto' | 'carga' | 'sla' | 'okr' | 'nps' | 'margen'
  | 'sprint_completitud' | 'sprint_velocidad'
  | 'aprobacion_riesgo_sla' | 'aprobacion_rechazo' | 'vencimiento'
  | 'riesgo' | 'salud_proyecto' | 'salud_cliente' | 'evm'

export type Tono = 'success' | 'warning' | 'danger'

export type Corte = { aviso: number; critico: number; mayor_peor: boolean; inclusivo?: boolean }

export type Sueltos = {
  UMBRAL_SOBRECARGA_HORAS_SEMANA: number
  UMBRAL_APROBACION_PENDIENTES_CRITICO: number
  UMBRAL_APROBACION_DECISION_HORAS: number
  UMBRAL_VENCIMIENTO_HORIZONTE_DIAS: number
  UMBRAL_HITOS_HORIZONTE_DIAS: number
  UMBRAL_HITOS_INMINENTE_DIAS: number
  RESOURCE_UNDERUSE_PCT: number
}

export type Umbrales = Record<Metrica, Corte> & { sueltos: Sueltos }

export const UMBRALES_POR_DEFECTO: Umbrales = {
  presupuesto: { aviso: 70, critico: 90, mayor_peor: true },
  carga: { aviso: 85, critico: 100, mayor_peor: true },
  sla: { aviso: 90, critico: 75, mayor_peor: false },
  okr: { aviso: 60, critico: 30, mayor_peor: false },
  nps: { aviso: 50, critico: 0, mayor_peor: false },
  margen: { aviso: 50, critico: 30, mayor_peor: false },
  sprint_completitud: { aviso: 80, critico: 50, mayor_peor: false },
  sprint_velocidad: { aviso: 85, critico: 50, mayor_peor: false },
  aprobacion_riesgo_sla: { aviso: 50, critico: 80, mayor_peor: true, inclusivo: true },
  aprobacion_rechazo: { aviso: 10, critico: 25, mayor_peor: true, inclusivo: true },
  vencimiento: { aviso: 30, critico: 14, mayor_peor: false, inclusivo: true },
  riesgo: { aviso: 50, critico: 75, mayor_peor: true, inclusivo: true },
  salud_proyecto: { aviso: 70, critico: 45, mayor_peor: false },
  salud_cliente: { aviso: 60, critico: 40, mayor_peor: false },
  evm: { aviso: 0.9, critico: 0.85, mayor_peor: false },
  sueltos: {
    UMBRAL_SOBRECARGA_HORAS_SEMANA: 42,
    UMBRAL_APROBACION_PENDIENTES_CRITICO: 3,
    UMBRAL_APROBACION_DECISION_HORAS: 24,
    UMBRAL_VENCIMIENTO_HORIZONTE_DIAS: 90,
    UMBRAL_HITOS_HORIZONTE_DIAS: 60,
    UMBRAL_HITOS_INMINENTE_DIAS: 7,
    RESOURCE_UNDERUSE_PCT: 50,
  },
}

/**
 * Horas que se pueden imputar a una persona en un día: el mismo límite que
 * valida el servidor (`app/schemas/imputations.py`, `le=24`, y la suma del día
 * en `imputation_service`). Un solo sitio para todos los formularios de horas.
 */
export const HORAS_MAXIMAS_POR_DIA = 24

/** Mezcla lo que manda el servidor con los valores por defecto (métrica a métrica). */
export function conDefectos(parcial?: Partial<Umbrales> | null): Umbrales {
  if (!parcial) return UMBRALES_POR_DEFECTO
  const salida = { ...UMBRALES_POR_DEFECTO } as Umbrales
  for (const clave of Object.keys(UMBRALES_POR_DEFECTO) as Array<keyof Umbrales>) {
    const v = parcial[clave]
    if (v && typeof v === 'object') (salida as Record<string, unknown>)[clave] = { ...UMBRALES_POR_DEFECTO[clave], ...v }
  }
  return salida
}

/** El tono de `valor` para `metrica`. `null`/`undefined` → `undefined` (sin dato). */
export function tonoDe(metrica: Metrica, valor: number | null | undefined, umbrales: Umbrales = UMBRALES_POR_DEFECTO): Tono | undefined {
  if (valor == null || Number.isNaN(Number(valor))) return undefined
  const v = Number(valor)
  const c = umbrales[metrica] ?? UMBRALES_POR_DEFECTO[metrica]
  if (c.mayor_peor) {
    if (c.inclusivo ? v >= c.critico : v > c.critico) return 'danger'
    if (c.inclusivo ? v >= c.aviso : v > c.aviso) return 'warning'
    return 'success'
  }
  if (c.inclusivo ? v <= c.critico : v < c.critico) return 'danger'
  if (c.inclusivo ? v <= c.aviso : v < c.aviso) return 'warning'
  return 'success'
}

/** Variable CSS del tono (`var(--success)`…). Sin dato, `porDefecto`. */
export function colorDeTono(tono: Tono | undefined, porDefecto = 'var(--text-2)'): string {
  return tono ? `var(--${tono})` : porDefecto
}

/**
 * Estado de carga de una persona (% de capacidad) en cuatro bandas:
 * `sobrecargado` (> crítico), `alto` (> aviso), `ocupado` (≥ infrautilización)
 * y `disponible`. Lo usan Capacidad, Previsión y Recursos.
 */
export function estadoDeCarga(pct: number | null | undefined, umbrales: Umbrales = UMBRALES_POR_DEFECTO): 'sobrecargado' | 'alto' | 'ocupado' | 'disponible' {
  const v = Number(pct ?? 0)
  const tono = tonoDe('carga', v, umbrales)
  if (tono === 'danger') return 'sobrecargado'
  if (tono === 'warning') return 'alto'
  return v >= umbrales.sueltos.RESOURCE_UNDERUSE_PCT ? 'ocupado' : 'disponible'
}
