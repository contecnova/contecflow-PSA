/**
 * services/api/presupuestos.ts — presupuestos con partidas, real calculado, versiones y aprobación (revisión 2026-11).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }` (y deja la lista en `r.data` para `{ items, meta }`).
 */
import api from './_core'

export type Ambito = 'proyecto' | 'proyecto_previsto' | 'departamento' | 'area'
export interface Partida {
  id: string; tipo: string; descripcion: string; user_id?: string | null; user_name?: string | null; perfil?: string | null
  horas?: number | null; coste_hora?: number | null; importe: number; meses: Record<string, number>
}
export interface MesInforme { mes: string; plan: number; real: number; desviacion: number; cerrado: boolean; en_curso: boolean }
export interface Informe {
  meses: MesInforme[]; por_tipo: { tipo: string; plan: number; real: number; desviacion: number; desviacion_pct: number | null }[]
  total_plan: number; total_real: number; plan_hasta_hoy: number; desviacion_hasta_hoy: number; prevision_cierre: number; sin_real: boolean
}
export interface Presupuesto {
  id: string; name: string; year: number; ambito: Ambito; department?: string | null; area?: string | null
  project_id?: string | null; project_name?: string | null; cliente_id?: string | null; tipo_proyecto?: string | null
  periodo_desde: string; periodo_hasta: string; currency: string; notes?: string | null; version: number; origen_id: string
  estado: 'borrador' | 'enviado' | 'aprobado' | 'rechazado' | 'sustituido'; motivo_rechazo?: string | null; total_plan: number
  total_real?: number; plan_hasta_hoy?: number; desviacion_hasta_hoy?: number; prevision_cierre?: number
}
export interface FichaPresupuesto extends Presupuesto {
  lineas: Partida[]; informe: Informe; versiones: { id: string; version: number; estado: string; total_plan: number }[]
  aprobacion_en_bandeja?: string | null; puedo_editar: boolean; puedo_aprobar: boolean; tipos: string[]
}

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)

export const presupuestosApi = {
  listar: (params: Record<string, unknown>) => D<Presupuesto[]>(api.get('/budgets', { params })),
  resumen: (year?: number) => D<{ year: number; presupuestos: number; aprobados: number; total_plan: number; total_real: number
    plan_hasta_hoy: number; prevision_cierre: number; por_mes: { mes: string; plan: number; real: number }[] }>(api.get('/budgets/summary', { params: { year } })),
  ficha: (id: string) => D<FichaPresupuesto>(api.get(`/budgets/${id}`)),
  crear: (body: Record<string, unknown>) => D<FichaPresupuesto>(api.post('/budgets', body)),
  editar: (id: string, body: Record<string, unknown>) => D<FichaPresupuesto>(api.patch(`/budgets/${id}`, body)),
  crearPartida: (id: string, body: Record<string, unknown>) => D<FichaPresupuesto>(api.post(`/budgets/${id}/lines`, body)),
  editarPartida: (id: string, lid: string, body: Record<string, unknown>) => D<FichaPresupuesto>(api.patch(`/budgets/${id}/lines/${lid}`, body)),
  borrarPartida: (id: string, lid: string) => D<FichaPresupuesto>(api.delete(`/budgets/${id}/lines/${lid}`)),
  enviar: (id: string) => D<FichaPresupuesto>(api.post(`/budgets/${id}/submit`)),
  decidir: (id: string, aprobado: boolean, motivo?: string) => D<FichaPresupuesto>(api.post(`/budgets/${id}/decision`, { aprobado, motivo })),
  nuevaVersion: (id: string) => D<FichaPresupuesto>(api.post(`/budgets/${id}/new-version`)),
  vincular: (id: string, project_id: string) => D<FichaPresupuesto>(api.post(`/budgets/${id}/link-project`, { project_id })),
}
