/**
 * services/api/cambiosEstandar.ts — Catálogo de cambios estándar del CAB (23-11-2026, A-SD19).
 *
 * `/sd/standard-changes` (app/api/v1/endpoints/service_desk/cambios_estandar.py):
 * leer con `sd.completo`; proponer, editar, aprobar, suspender, reactivar y dar
 * de baja con `sd.gestionar`. El interceptor de `_core` desenvuelve `{ data, meta }`.
 */
import api from './_core'

export type EstadoDeModeloEstandar = 'proposed' | 'approved' | 'suspended' | 'retired'
export type RiesgoDeCambio = 'low' | 'medium' | 'high' | 'critical'

/** `serializar_modelo` (cambios_estandar_service.py). */
export interface ModeloDeCambioEstandar {
  id: string
  name: string
  description: string | null
  procedure: string
  rollback_plan: string | null
  test_plan: string | null
  max_risk: RiesgoDeCambio
  applies_to_ci_ids: string[]
  applies_to_ci_types: string[]
  applies_to_service_ids: string[]
  status: EstadoDeModeloEstandar
  is_active: boolean
  /** Aprobado, activo y con la revisión periódica sin vencer: hoy vale como estándar. */
  vigente: boolean
  caducado: boolean
  proposed_by: string | null
  proposer: string | null
  approved_by: string | null
  approver: string | null
  approved_at: string | null
  review_interval_days: number | null
  next_review_at: string | null
  suspended_at: string | null
  suspended_reason: string | null
  use_count: number
  success_count: number
  failure_count: number
  failure_rate_pct: number | null
  created_at: string | null
}

/** `ModeloEstandarIn` / `ModeloEstandarUpdate`. */
export interface ModeloDeCambioEstandarIn {
  name: string
  description?: string | null
  procedure: string
  rollback_plan?: string | null
  test_plan?: string | null
  max_risk: RiesgoDeCambio
  applies_to_ci_ids?: string[]
  applies_to_ci_types?: string[]
  applies_to_service_ids?: string[]
  review_interval_days?: number | null
}

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
const BASE = '/sd/standard-changes'

export const cambiosEstandarApi = {
  listar: (params?: { solo_vigentes?: boolean; incluir_bajas?: boolean }) => D<ModeloDeCambioEstandar[]>(api.get(BASE, { params })),
  proponer: (datos: ModeloDeCambioEstandarIn) => D<ModeloDeCambioEstandar>(api.post(BASE, datos)),
  editar: (id: string, datos: Partial<ModeloDeCambioEstandarIn>) => D<ModeloDeCambioEstandar>(api.patch(`${BASE}/${id}`, datos)),
  aprobar: (id: string) => D<ModeloDeCambioEstandar>(api.post(`${BASE}/${id}/approve`)),
  suspender: (id: string, reason: string) => D<ModeloDeCambioEstandar>(api.post(`${BASE}/${id}/suspend`, { reason })),
  reactivar: (id: string) => D<ModeloDeCambioEstandar>(api.post(`${BASE}/${id}/reactivate`)),
  retirar: (id: string) => D<ModeloDeCambioEstandar>(api.delete(`${BASE}/${id}`)),
}
