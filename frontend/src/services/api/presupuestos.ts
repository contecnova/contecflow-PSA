/**
 * services/api/presupuestos.ts — presupuestos con partidas, real calculado, versiones y aprobación (revisión 2026-11).
 * Preparar a fondo: áreas, jerarquía con techo, partidas con conductores, persona por coste cargado,
 * vacantes, ingresos, CAPEX, supuestos y escenarios, plantillas y campañas.
 * Seguir a fondo: comprometido (ALM y pedidos), cierre mensual, desviaciones explicadas, reprevisión,
 * traspasos con aprobación, detalle del real y cuadro de control.
 * El interceptor de `_core` ya desenvuelve `{ data, meta }` (y deja la lista en `r.data` para `{ items, meta }`).
 */
import api from './_core'

export type Ambito = 'proyecto' | 'proyecto_previsto' | 'departamento' | 'area'
export type Recurrencia = 'unica' | 'mensual' | 'trimestral' | 'anual'
export interface Partida {
  id: string; tipo: string; descripcion: string; user_id?: string | null; user_name?: string | null; perfil?: string | null
  horas?: number | null; coste_hora?: number | null; importe: number; meses: Record<string, number>
  sentido: 'gasto' | 'ingreso'; naturaleza: 'opex' | 'capex'; vida_meses?: number | null
  unidades?: number | null; precio_unitario?: number | null; recurrencia?: Recurrencia | null
  mes_desde?: string | null; mes_hasta?: string | null; dedicacion_pct?: number | null
  fecha_alta?: string | null; pais?: string | null; salario_anual?: number | null; justificacion?: string | null
}
export interface MesInforme {
  mes: string; plan: number; real: number; desviacion: number; cerrado: boolean; en_curso: boolean
  ingreso_plan: number; ingreso_real: number; amortizacion: number
}
export interface Informe {
  meses: MesInforme[]; por_tipo: { tipo: string; plan: number; real: number; desviacion: number; desviacion_pct: number | null }[]
  total_plan: number; total_real: number; plan_hasta_hoy: number; desviacion_hasta_hoy: number; prevision_cierre: number; sin_real: boolean
  ingreso_plan: number; ingreso_real: number; margen_plan: number; margen_real: number
  opex_plan: number; capex_plan: number; amortizacion_total: number
}
export interface Supuestos { inflacion_pct?: number; [k: string]: unknown }
export interface Presupuesto {
  id: string; name: string; year: number; ambito: Ambito; department?: string | null; area?: string | null
  project_id?: string | null; project_name?: string | null; cliente_id?: string | null; tipo_proyecto?: string | null
  periodo_desde: string; periodo_hasta: string; currency: string; notes?: string | null; version: number; origen_id: string
  estado: 'borrador' | 'enviado' | 'aprobado' | 'rechazado' | 'sustituido'; motivo_rechazo?: string | null; total_plan: number
  total_ingreso: number; total_real?: number; plan_hasta_hoy?: number; desviacion_hasta_hoy?: number; prevision_cierre?: number
  area_id?: string | null; area_name?: string | null; padre_id?: string | null; padre_name?: string | null
  padre_ambito?: Ambito | null; padre_ficha_id?: string | null; techo?: number | null
  responsable_id?: string | null; responsable_name?: string | null; campana_id?: string | null; campana_name?: string | null
  escenario: string; supuestos: Supuestos
}
export interface EstadoDelTecho { techo: number; consumido_por_hijos: number; disponible: number; excedido: boolean }
export interface FichaPresupuesto extends Presupuesto {
  lineas: Partida[]; informe: Informe; versiones: { id: string; version: number; estado: string; total_plan: number }[]
  hijos: { id: string; name: string; ambito: Ambito; estado: string; version: number; total_plan: number }[]
  techo_estado: EstadoDelTecho | null; consolidado_plan: number | null; aviso_techo_del_padre: string | null
  aprobacion_en_bandeja?: string | null; puedo_editar: boolean; puedo_aprobar: boolean; tipos: string[]; tipos_ingreso: string[]
  seguir: Seguir | null; pedidos: Pedido[]; traspasos: Traspaso[]; mes_actual?: string
  puedo_gestionar?: boolean; puedo_decidir_traspasos?: boolean
}
export type MetodoPrevision = 'plan' | 'ritmo' | 'manual'
export interface Desviacion { mes: string; tipo: string; plan: number; real: number; desviacion: number; desviacion_pct: number | null; explicacion: string | null }
export interface Seguir {
  por_tipo: { tipo: string; plan: number; real: number; comprometido: number; disponible: number; prevision: number
    metodo: MetodoPrevision; consumo_pct: number | null }[]
  plan: number; real: number; comprometido: number; disponible: number; prevision: number
  meses_cerrados: string[]; meses_por_cerrar: string[]
  comprometido_por_mes: Record<string, number>; prevision_por_mes: Record<string, number>
  desviaciones_sin_explicar: Desviacion[]; traspasos_pendientes: number
}
export interface Pedido {
  id: string; tipo: string; descripcion: string; proveedor?: string | null; referencia?: string | null; importe: number; mes: string
  estado: 'comprometido' | 'facturado' | 'anulado'; fecha_factura?: string | null; importe_facturado?: number | null
}
export interface Traspaso {
  id: string; budget_id: string; desde_linea_id?: string | null; hacia_linea_id?: string | null; hacia_tipo?: string | null
  hacia_descripcion?: string | null; importe: number; motivo: string; estado: 'pendiente' | 'aprobado' | 'rechazado'
  solicitante_id: string; motivo_rechazo?: string | null; created_at?: string | null
}
export interface Apunte { origen: 'imputacion' | 'gasto' | 'pedido'; id: string; fecha: string; tipo: string; quien?: string | null
  concepto: string; horas?: number; importe: number }
export interface RenglonDelCuadro {
  id: string; name: string; ambito: Ambito; estado: string; version: number; escenario: string; currency: string
  plan: number; real: number; comprometido: number; disponible: number; prevision: number; consumo_pct: number | null
  meses_por_cerrar: number; desviaciones_sin_explicar: number; traspasos_pendientes: number; semaforo: 'verde' | 'ambar' | 'rojo'
}
export interface Plantilla { id: string; nombre: string; ambito?: Ambito | null; tipo_proyecto?: string | null; partidas: Partial<Partida>[] }
export interface Campana {
  id: string; nombre: string; year: number; fecha_limite: string; abierta: boolean; instrucciones?: string | null
  dias_restantes: number; presupuestos: number; por_estado: Record<string, number>
}
export interface Area { id: string; name: string; description?: string | null; manager_id?: string | null; departamentos: string[] }
export interface Comparacion {
  presupuestos: { id: string; name: string; version: number; escenario: string; estado: string; gasto: number; ingreso: number
    margen: number; por_tipo: Record<string, number>; por_mes: Record<string, number>; supuestos: Supuestos }[]
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
  escenario: (id: string, nombre: string, supuestos?: Supuestos) => D<FichaPresupuesto>(api.post(`/budgets/${id}/scenario`, { nombre, supuestos })),
  comparar: (ids: string[]) => D<Comparacion>(api.post('/budgets/compare', { ids })),
  plantillas: () => D<Plantilla[]>(api.get('/budget-templates')),
  guardarPlantilla: (body: Record<string, unknown>, id?: string) =>
    D<Plantilla>(id ? api.patch(`/budget-templates/${id}`, body) : api.post('/budget-templates', body)),
  borrarPlantilla: (id: string) => D<{ ok: boolean }>(api.delete(`/budget-templates/${id}`)),
  campanas: () => D<Campana[]>(api.get('/budget-campaigns')),
  guardarCampana: (body: Record<string, unknown>, id?: string) =>
    D<Campana>(id ? api.patch(`/budget-campaigns/${id}`, body) : api.post('/budget-campaigns', body)),
  cuadro: (year?: number) => D<RenglonDelCuadro[]>(api.get('/budgets/control-board', { params: { year } })),
  cerrarMes: (id: string, mes: string) => D<FichaPresupuesto>(api.post(`/budgets/${id}/close`, { mes })),
  reabrirMes: (id: string, mes: string) => D<FichaPresupuesto>(api.delete(`/budgets/${id}/close/${mes}`)),
  explicar: (id: string, mes: string, tipo: string, explicacion: string) =>
    D<FichaPresupuesto>(api.post(`/budgets/${id}/variance-notes`, { mes, tipo, explicacion })),
  prevision: (id: string, tipo: string, metodo: MetodoPrevision, meses?: Record<string, number>) =>
    D<FichaPresupuesto>(api.put(`/budgets/${id}/forecast`, { tipo, metodo, meses })),
  detalleDelReal: (id: string, mes: string, tipo?: string) => D<Apunte[]>(api.get(`/budgets/${id}/drilldown`, { params: { mes, tipo } })),
  exportarCsv: (id: string) => api.get(`/budgets/${id}/export.csv`, { responseType: 'blob' }).then(r => r.data as Blob),
  crearPedido: (id: string, body: Record<string, unknown>) => D<{ id: string; avisos: string[] }>(api.post(`/budgets/${id}/commitments`, body)),
  estadoDePedido: (pid: string, body: Record<string, unknown>) => D<Pedido>(api.patch(`/budget-commitments/${pid}`, body)),
  pedirTraspaso: (id: string, body: Record<string, unknown>) => D<Traspaso>(api.post(`/budgets/${id}/transfers`, body)),
  decidirTraspaso: (tid: string, aprobado: boolean, motivo?: string) =>
    D<Traspaso>(api.post(`/budget-transfers/${tid}/decision`, { aprobado, motivo })),
  areas: () => D<Area[]>(api.get('/settings/areas')),
  guardarArea: (body: Record<string, unknown>, id?: string) => D<Area>(id ? api.patch(`/settings/areas/${id}`, body) : api.post('/settings/areas', body)),
  borrarArea: (id: string) => D<{ ok: boolean }>(api.delete(`/settings/areas/${id}`)),
}
