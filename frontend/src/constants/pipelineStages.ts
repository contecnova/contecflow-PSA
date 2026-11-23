/**
 * Etapas del pipeline comercial y regla de cálculo de sus totales.
 *
 * 23-11-2026 (auditoría 04b M9): un único sitio para los estados, espejo de
 * `app/models/pipeline.py` (ETAPAS_ABIERTAS / ETAPAS_CERRADAS / ETAPAS_DECIDIDAS).
 * Regla de mercado (Salesforce/HubSpot):
 *  - Valor del pipeline abierto y previsión ponderada: solo etapas abiertas.
 *  - Tasa de éxito = ganadas / (ganadas + perdidas).
 *  - Canceladas = «sin decisión»: fuera de la tasa y del pipeline; aparte.
 */

export const ETAPA_GANADA = 'won'
export const ETAPA_PERDIDA = 'lost'
export const ETAPA_CANCELADA = 'cancelled'

export const ETAPAS_ABIERTAS: readonly string[] = ['lead', 'qualification', 'proposal', 'negotiation']
export const ETAPAS_CERRADAS: readonly string[] = [ETAPA_GANADA, ETAPA_PERDIDA, ETAPA_CANCELADA]
/** Orden de las columnas del tablero. */
export const ETAPAS_PIPELINE: readonly string[] = [...ETAPAS_ABIERTAS, ...ETAPAS_CERRADAS]
/** Una perdida o cancelada no se convierte en proyecto. */
export const ETAPAS_SIN_CONVERSION: readonly string[] = [ETAPA_PERDIDA, ETAPA_CANCELADA]

export type EstadoPipeline = 'open' | 'won' | 'lost' | 'cancelled'
export type FiltroEstadoPipeline = 'all' | EstadoPipeline
export const FILTROS_ESTADO: readonly FiltroEstadoPipeline[] = ['all', 'open', 'won', 'lost', 'cancelled']

/** Estado agregado de una etapa; una etapa desconocida se trata como abierta (el tablero la pinta en «lead»). */
export function estadoDeEtapa(stage: string | null | undefined): EstadoPipeline {
  if (stage === ETAPA_GANADA) return 'won'
  if (stage === ETAPA_PERDIDA) return 'lost'
  if (stage === ETAPA_CANCELADA) return 'cancelled'
  return 'open'
}

export function cumpleFiltroEstado(stage: string | null | undefined, filtro: FiltroEstadoPipeline): boolean {
  return filtro === 'all' || estadoDeEtapa(stage) === filtro
}

type OppMinima = { stage?: string | null; expected_revenue?: number | null; weighted_revenue?: number | null }

export type ResumenPipeline = {
  openCount: number
  openValue: number
  weightedValue: number
  wonCount: number
  wonValue: number
  lostCount: number
  lostValue: number
  cancelledCount: number
  cancelledValue: number
  /** % ganadas / (ganadas + perdidas); 0 si no hay decididas. */
  winRate: number
}

/** Mismo cálculo que `resumir_pipeline` (app/services/pipeline_service.py). */
export function resumirPipeline(opps: readonly OppMinima[]): ResumenPipeline {
  const r: ResumenPipeline = {
    openCount: 0, openValue: 0, weightedValue: 0,
    wonCount: 0, wonValue: 0, lostCount: 0, lostValue: 0,
    cancelledCount: 0, cancelledValue: 0, winRate: 0,
  }
  for (const o of opps) {
    const importe = Number(o.expected_revenue) || 0
    switch (estadoDeEtapa(o.stage)) {
      case 'open':
        r.openCount += 1
        r.openValue += importe
        r.weightedValue += Number(o.weighted_revenue) || 0
        break
      case 'won':
        r.wonCount += 1
        r.wonValue += importe
        break
      case 'lost':
        r.lostCount += 1
        r.lostValue += importe
        break
      case 'cancelled':
        r.cancelledCount += 1
        r.cancelledValue += importe
        break
    }
  }
  const decididas = r.wonCount + r.lostCount
  r.winRate = decididas ? (r.wonCount / decididas) * 100 : 0
  return r
}
