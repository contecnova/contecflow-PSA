// Auditoría 04b M9: regla de totales del pipeline (espejo de resumir_pipeline en el backend).
import { describe, expect, it } from 'vitest'
import { cumpleFiltroEstado, resumirPipeline } from '../pipelineStages'

const opps = [
  { stage: 'lead', expected_revenue: 1000, weighted_revenue: 100 },
  { stage: 'negotiation', expected_revenue: 2000, weighted_revenue: 1500 },
  { stage: 'won', expected_revenue: 5000, weighted_revenue: 5000 },
  { stage: 'won', expected_revenue: 3000, weighted_revenue: 3000 },
  { stage: 'lost', expected_revenue: 4000, weighted_revenue: 400 },
  { stage: 'cancelled', expected_revenue: 7000, weighted_revenue: 700 },
]

describe('resumirPipeline', () => {
  it('pipeline y ponderado solo de abiertas; canceladas aparte', () => {
    const r = resumirPipeline(opps)
    expect(r.openCount).toBe(2)
    expect(r.openValue).toBe(3000)
    expect(r.weightedValue).toBe(1600)
    expect(r.cancelledCount).toBe(1)
    expect(r.cancelledValue).toBe(7000)
    expect(r.lostValue).toBe(4000)
    expect(r.wonValue).toBe(8000)
  })

  it('tasa de éxito = ganadas / (ganadas + perdidas), sin canceladas', () => {
    expect(resumirPipeline(opps).winRate).toBeCloseTo((2 / 3) * 100)
    expect(resumirPipeline([{ stage: 'cancelled', expected_revenue: 1 }]).winRate).toBe(0)
  })
})

describe('cumpleFiltroEstado', () => {
  it('filtra por estado agregado', () => {
    expect(cumpleFiltroEstado('proposal', 'open')).toBe(true)
    expect(cumpleFiltroEstado('cancelled', 'open')).toBe(false)
    expect(cumpleFiltroEstado('cancelled', 'cancelled')).toBe(true)
    expect(cumpleFiltroEstado('lost', 'all')).toBe(true)
  })
})
