/**
 * services/api/horas-extra.ts — horas extra (18-11-2026): petición previa o
 * declaración posterior, aprobación por flujos, control de la imputación,
 * presupuestos, resumen frente a los límites de las reglas y nómina.
 * El interceptor de `_core` ya desenvuelve `{ ok, data }`: `r.data` es el contenido.
 */
import api from './_core'

export type EstadoHe = 'pendiente' | 'aprobada' | 'rechazada' | 'cancelada'
export type OrigenHe = 'previa' | 'posterior'
export type TipoHe = 'laborable' | 'fuera_de_franja' | 'festivo' | 'no_laborable' | 'guardia'
export type ClaseDia = 'laborable' | 'festivo' | 'no_laborable'
export type CompensacionHe = 'pago' | 'bolsa' | 'ninguna'
export type ControlImputacion = 'ninguno' | 'avisar' | 'regularizar' | 'bloquear'
export type AmbitoPresupuesto = 'empresa' | 'departamento' | 'equipo' | 'proyecto'
export type PeriodoPresupuesto = 'mes' | 'anio'
export type DecisionHe = 'allow' | 'auto_approve' | 'review' | 'block'
export type AgruparPor = 'persona' | 'equipo' | 'departamento' | 'proyecto'
export type Tramo = [string, string]

export const ESTADOS_HE: EstadoHe[] = ['pendiente', 'aprobada', 'rechazada', 'cancelada']
export const ORIGENES_HE: OrigenHe[] = ['previa', 'posterior']
export const TIPOS_HE: TipoHe[] = ['laborable', 'fuera_de_franja', 'festivo', 'no_laborable', 'guardia']
export const COMPENSACIONES_HE: CompensacionHe[] = ['pago', 'bolsa', 'ninguna']
export const CONTROLES_HE: ControlImputacion[] = ['ninguno', 'avisar', 'regularizar', 'bloquear']
export const AMBITOS_HE: AmbitoPresupuesto[] = ['empresa', 'departamento', 'equipo', 'proyecto']

export interface Liquidacion { en: string; referencia: string; por: string | null }

export interface PeticionHe {
  id: string; user_id: string; persona: string; solicitante_id: string; solicitante: string
  origen: OrigenHe; tipo: TipoHe; clase_dia: ClaseDia; fecha: string
  hora_inicio: string | null; hora_fin: string | null
  horas: number; horas_autorizadas: number | null; horas_reales: number | null
  motivo: string | null; project_id: string | null; proyecto: string | null; ticket_id: string | null
  sustituto_id: string | null; sustituto: string | null
  compensacion: CompensacionHe; factor: number; horas_ponderadas: number
  estado: EstadoHe; liquidacion: Liquidacion | null
  avisos: string[]; bloqueos: string[]
  decidido_por: string | null; decidido_en: string | null; motivo_rechazo: string | null
  created_at: string
  en_aprobacion: boolean; puede_cancelar: boolean; puede_editar: boolean; puede_revisar: boolean
}

export interface PeticionHeIn {
  user_id?: string | null; fecha: string; tipo: TipoHe
  hora_inicio?: string | null; hora_fin?: string | null; horas?: number | null
  motivo?: string | null; project_id?: string | null; ticket_id?: string | null
  sustituto_id?: string | null; compensacion?: CompensacionHe | null
}

export interface ConfigHe {
  activo: boolean; control_imputacion: ControlImputacion; tolerancia_minutos: number
  compensaciones: CompensacionHe[]; compensacion_por_defecto: CompensacionHe
  workflow_id: string | null; tipo_bolsa_id: string | null
  pedir_en_nombre: boolean; exigir_motivo: boolean
  updated_at: string | null; updated_by: string | null
  puede_editar: boolean
  flujos: Array<{ id: string; name: string }>
  tipos_de_bolsa: Array<{ id: string; nombre: string }>
}
export type ConfigHeIn = Pick<ConfigHe, 'activo' | 'control_imputacion' | 'tolerancia_minutos' | 'compensaciones'
  | 'compensacion_por_defecto' | 'workflow_id' | 'tipo_bolsa_id' | 'pedir_en_nombre' | 'exigir_motivo'>

export interface PresupuestoHe {
  id: string; ambito: AmbitoPresupuesto; valor: string | null; etiqueta: string; periodo: PeriodoPresupuesto
  anio: number | null; horas: number; consumidas: number; restantes: number; nota: string | null; activo: boolean
}
export interface PresupuestoHeIn {
  ambito: AmbitoPresupuesto; valor: string | null; periodo: PeriodoPresupuesto; anio: number | null
  horas: number; nota: string | null; activo: boolean
}

export interface Acumulados { dia: number; semana: number; mes: number; anio: number; anio_pago: number }

export interface AprobacionPrevista {
  orden: number | null; nombre: string; tipo: string; aprobador: string; rol: string | null
  origen: 'flujo' | 'politica' | 'responsable'
}

export interface VistaPreviaHe {
  decision: DecisionHe; horas: number; clase_dia: ClaseDia
  horario: { horas: number; tramos: Tramo[]; festivo: string | null }
  horas_fuera_de_horario: number; acumulados: Acumulados
  presupuesto_restante: number | null; descanso_horas: number | null; dias_seguidos: number; antelacion_horas: number
  compensacion: CompensacionHe; factor: number; horas_ponderadas: number
  aprobaciones: AprobacionPrevista[]
  avisos: string[]; bloqueos: string[]; requisitos: string[]; errores: string[]
}

export interface EventoHe { tipo: string; quien: string | null; cuando: string; datos: Record<string, unknown> | null }

export interface ReglaExplicada { regla: string; cumple: boolean; [k: string]: unknown }
export interface PoliticaExplicada { politica: string; aplica: boolean; reglas: ReglaExplicada[] }
export interface EvaluacionHe {
  momento: string; decision: string; resultado: unknown; explicacion: PoliticaExplicada[] | null; created_at: string
}

export interface AprobacionHe {
  id: string; estado: string; paso_actual: number | null
  pasos: Array<{ orden: number; nombre: string; tipo: string; aprobador: string; rol: string | null }>
  decisiones: Array<{ orden: number; decision: string; nota: string | null; quien: string | null; cuando: string }>
  escalados: Array<{ accion: string; cuando: string; nota: string | null; paso: number | null }>
}

export interface DetalleHe {
  peticion: PeticionHe
  linea_de_tiempo: EventoHe[]
  evaluaciones: EvaluacionHe[]
  aprobacion: AprobacionHe | null
  dia: { horario_horas: number; tramos: Tramo[]; festivo: string | null; imputado: number; exceso_real: number; autorizadas_del_dia: number }
  imputaciones: Array<{ id: string; proyecto: string | null; horas: number; descripcion: string | null; aprobada: boolean }>
  compensacion: {
    tipo: CompensacionHe; horas_ponderadas: number
    movimiento_bolsa: { cantidad: number; fecha: string } | null
    liquidacion: Liquidacion | null
  }
  puede_gestionar: boolean
}

export interface ElementoBandejaHe {
  solicitud_id: string | null; paso: string | null; sin_flujo: boolean; peticion: PeticionHe
  contexto: { acumulados: Acumulados; presupuesto_restante: number | null; descanso_horas: number | null; dias_seguidos: number }
}

export interface TotalesHe { peticiones: number; horas: number; autorizadas: number; pendientes: number; ponderadas_pago: number }
export interface ListaHe { items: PeticionHe[]; totales: TotalesHe }

export type CampoLimite = 'horas_en_dia' | 'horas_en_semana' | 'horas_en_mes' | 'horas_en_anio' | 'horas_en_anio_pago'
export interface LimiteConsumido { campo: CampoLimite | string; umbral: number; consumo: number; pct: number; politica: string; efecto: string }
export interface FilaResumenHe {
  clave: string; etiqueta: string; peticiones: number
  horas_pedidas: number; horas_aprobadas: number; horas_pendientes: number; horas_rechazadas: number
  horas_reales: number; horas_sin_autorizar: number; horas_pago: number; horas_bolsa: number; horas_ponderadas_pago: number
  presupuesto: { horas: number; restantes: number } | null
  limites: LimiteConsumido[]
}
export interface ResumenHe {
  agrupar: AgruparPor; filas: FilaResumenHe[]
  limites_publicados: Array<{ campo: string; umbral: number; politica: string; regla: string; efecto: string }>
}

export interface SinAutorizarHe {
  user_id: string; persona: string; fecha: string; horario: number; imputado: number
  autorizadas: number; pendientes: number; sin_autorizar: number; peticion_id: string | null
}

export type AccionDeControl = 'nada' | 'avisar' | 'regularizar' | 'bloquear'
export interface ComprobacionHe {
  activo: boolean; control: ControlImputacion; horario: number; imputado: number
  autorizadas: number; sin_autorizar: number; accion: AccionDeControl
}

export interface LineaDeNomina {
  id: string; user_id: string; persona: string; fecha: string; tipo: TipoHe
  horas_autorizadas: number | null; horas_reales: number | null; factor: number; horas_ponderadas: number
  liquidacion: Liquidacion | null
}

export interface FiltrosHe {
  desde?: string; hasta?: string; estado?: string; origen?: string; tipo?: string; compensacion?: string
  user_id?: string; project_id?: string; equipo?: string; departamento?: string
}

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
/** Quita los filtros vacíos para no mandar `estado=`. */
const limpio = <T extends object>(o: T) =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== null && v !== undefined))

export const horasExtraApi = {
  config: () => D<ConfigHe>(api.get('/overtime/config')),
  guardarConfig: (c: ConfigHeIn) => D<ConfigHe>(api.put('/overtime/config', c)),
  presupuestos: (fecha?: string) => D<PresupuestoHe[]>(api.get('/overtime/budgets', { params: fecha ? { fecha } : {} })),
  crearPresupuesto: (p: PresupuestoHeIn) => D<PresupuestoHe>(api.post('/overtime/budgets', p)),
  guardarPresupuesto: (id: string, p: PresupuestoHeIn) => D<PresupuestoHe>(api.put(`/overtime/budgets/${id}`, p)),
  borrarPresupuesto: (id: string) => D<unknown>(api.delete(`/overtime/budgets/${id}`)),
  vistaPrevia: (p: PeticionHeIn) => D<VistaPreviaHe>(api.post('/overtime/preview', p)),
  pedir: (p: PeticionHeIn) => D<PeticionHe>(api.post('/overtime', p)),
  editar: (id: string, p: PeticionHeIn) => D<PeticionHe>(api.put(`/overtime/${id}`, p)),
  cancelar: (id: string, nota?: string) => D<PeticionHe>(api.post(`/overtime/${id}/cancel`, { nota: nota || null })),
  revisar: (id: string, aprobado: boolean, nota?: string, horasAutorizadas?: number | null) =>
    D<PeticionHe>(api.post(`/overtime/${id}/review`, {
      aprobado, nota: nota || null, ...(aprobado && horasAutorizadas != null ? { horas_autorizadas: horasAutorizadas } : {}),
    })),
  liquidar: (id: string, referencia: string) => D<PeticionHe>(api.post(`/overtime/${id}/settle`, { referencia })),
  mias: (f: { desde?: string; hasta?: string; estado?: string }) => D<PeticionHe[]>(api.get('/overtime/mine', { params: limpio(f) })),
  listar: (f: FiltrosHe) => D<ListaHe>(api.get('/overtime', { params: limpio(f) })),
  detalle: (id: string) => D<DetalleHe>(api.get(`/overtime/${id}`)),
  bandeja: () => D<ElementoBandejaHe[]>(api.get('/overtime/inbox')),
  resumen: (f: { desde?: string; hasta?: string; agrupar: AgruparPor }) => D<ResumenHe>(api.get('/overtime/summary', { params: limpio(f) })),
  sinAutorizar: (f: { desde?: string; hasta?: string; user_id?: string }) =>
    D<SinAutorizarHe[]>(api.get('/overtime/unauthorized', { params: limpio(f) })),
  comprobar: (fecha: string, horas: number, imputationId?: string) =>
    D<ComprobacionHe>(api.get('/overtime/check', { params: limpio({ fecha, horas, imputation_id: imputationId }) })),
  regularizar: (desde: string, hasta: string) =>
    D<{ creadas: number; actualizadas: number; anuladas: number }>(api.post('/overtime/regularize', { desde, hasta })),
  nomina: (f: { desde?: string; hasta?: string; liquidadas?: boolean | null }) =>
    D<LineaDeNomina[]>(api.get('/overtime/payroll', { params: limpio(f) })),
  cargarEjemplos: () =>
    D<{ politicas_creadas: number; tablas_creadas: unknown[] }>(api.post('/policies/examples/horas_extra')),
}
