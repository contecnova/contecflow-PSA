/**
 * Tipos de ausencias gobernadas por reglas (tarea #25, revisión 167).
 * Espejo de `app/services/ausencias/*` y `app/api/v1/endpoints/ausencias.py`.
 */
export type Unidad = 'dias' | 'medios_dias' | 'horas'
export type Visibilidad = 'todos' | 'equipo' | 'privada'
export type Saldo = 'vacaciones' | 'propio' | 'bolsa'
/** Rev. 180: cómo se puede pedir un tipo (días enteros, medio día, franja horaria). */
export type ModoDePeticion = 'dias' | 'medio_dia' | 'horas'
export type PeriodoDeSaldo = 'anual' | 'semestral' | 'trimestral' | 'mensual' | 'sin_periodo'
/** Rev. 180: reglas de la bolsa de horas (horas de más imputadas que se acumulan como saldo). */
export interface ReglasDeBolsa {
  factor: number; factor_festivo: number; factor_no_laborable: number; umbral_minutos: number
  tope_diario: number | null; tope_periodo: number | null; solo_aprobadas: boolean
}
/** Franja horaria 'HH:MM'–'HH:MM' (fin menor que inicio = cruza la medianoche). */
export type Tramo = [string, string]
export type PlazoDesde = 'solicitud' | 'inicio' | 'fin'
export type Idioma = 'es' | 'en' | 'zh'
export type EstadoDeAusencia = 'pending' | 'approved' | 'rejected' | 'cancelled' | 'waitlisted'

export interface DestinatarioDeAviso {
  tipo: 'persona' | 'rol' | 'responsable' | 'grupo' | 'departamento' | 'solicitante'; valor?: string | null
}

export interface RequisitoDocumental {
  id?: string; tipo_de_documento_id: string; obligatorio: boolean; plazo_dias: number; plazo_desde: PlazoDesde
  repetir_cada_dias: number | null; recordar_dias_antes: number; escalar_dias_despues: number | null
  escalar_a: DestinatarioDeAviso[]; orden?: number
}

export interface TipoDeAusencia {
  id: string; clave: string; nombre: string; nombres: Partial<Record<Idioma, string>>; color: string; icono: string
  descuenta_saldo: boolean; saldo: Saldo | null; cupo_anual: number | null; unidad: Unidad; visibilidad: Visibilidad
  workflow_id: string | null; requiere_aprobacion: boolean; requiere_sustituto: boolean; datos_especiales: boolean
  activo: boolean; orden: number; de_sistema: boolean; requisitos: RequisitoDocumental[]
  // Rev. 180
  modos: ModoDePeticion[]; retribuido: boolean; periodo_saldo: PeriodoDeSaldo; inicio_periodo_mes: number
  arrastre_max: number | null; arrastre_caduca_meses: number | null; caduca_meses: number | null
  prorratear_alta: boolean; derecho_tabla_id: string | null; bolsa: ReglasDeBolsa | null
}
export type TipoDeAusenciaIn = Omit<TipoDeAusencia, 'id' | 'de_sistema'>

export interface TipoDeDocumento {
  id: string; clave: string; nombre: string; nombres: Partial<Record<Idioma, string>>; categoria_especial: boolean
  activo: boolean; orden: number
}
export type TipoDeDocumentoIn = Omit<TipoDeDocumento, 'id'>

export interface Turno {
  id: string; nombre: string; color: string; hora_inicio: string; hora_fin: string; cruza_medianoche: boolean
  duracion_horas: number; dias_semana: number[]; equipo: string | null; departamento: string | null
  office_id: string | null; personas_requeridas: number; trabaja_festivos: boolean; activo: boolean; orden: number
  /** Rev. 180: tramos del turno (uno si no es partido) y pausa no trabajada. */
  tramos: Tramo[]; partido: boolean; pausa_minutos: number
}
export type TurnoIn = Omit<Turno, 'id' | 'cruza_medianoche' | 'duracion_horas' | 'partido'>

export interface MiembroDeRotacion { id?: string; user_id: string; desde: string; hasta: string | null; desfase: number }
export interface Rotacion { id: string; nombre: string; ciclo: (string | null)[]; inicio: string; activo: boolean; miembros: MiembroDeRotacion[] }
export type RotacionIn = Omit<Rotacion, 'id'>

export interface CeldaDeCuadrante { turno_id: string | null; origen: 'rotacion' | 'cambio' | 'festivo' }
export interface PersonaDeCuadrante { id: string; nombre: string; equipo: string | null; departamento: string | null }
export interface Cuadrante {
  desde: string; hasta: string; dias: string[]; personas: PersonaDeCuadrante[]
  celdas: Record<string, Record<string, CeldaDeCuadrante>>; turnos: Turno[]
  festivos: { fecha: string; nombre: string; ambito: string | null }[]
}
export interface CambioDeTurno { user_id: string; fecha: string; turno_id: string | null; quitar?: boolean }

export interface CeldaDeCobertura {
  fecha: string; turno_id: string; requeridas: number; asignadas: number; ausentes: number; pendientes: number
  en_espera: number; disponibles: number; con_esta: number | null; estado: 'ok' | 'justo' | 'falta'
  ausentes_nombres: string[]; pendientes_nombres: string[]
  /** Rev. 180: personas con una ausencia por horas ese día (siguen en el turno). */
  parciales: number
}
export interface Cobertura {
  desde: string; hasta: string; turnos: Turno[]; celdas: CeldaDeCobertura[]; festivos: { fecha: string; nombre: string }[]
}

export interface PeticionDeAusencia {
  absence_type_id: string; start_date: string; end_date: string; reason?: string | null; shift_id?: string | null
  substitute_id?: string | null; half_day_start?: boolean; half_day_end?: boolean; hours?: number | null; id?: string
  /** Rev. 180: por días o por horas; por horas, la franja de cada día del rango. */
  modo?: 'dias' | 'horas'; start_time?: string | null; end_time?: string | null
}

export type UnidadDeSaldo = 'dias' | 'horas'
export interface CaducidadDeSaldo { fecha: string; cantidad: number; origen: string }
/** Rev. 180: un saldo con su periodo, arrastre, movimientos, caducidades y su equivalente en la otra unidad. */
export interface SaldoDeAusencia {
  saldo: Saldo; clave: string; tipo_id: string | null; gobierna: string | null; unidad: UnidadDeSaldo; year: number
  periodo: { clase: PeriodoDeSaldo; desde: string | null; hasta: string | null; etiqueta: string }
  derecho: number; derecho_origen: string | null; arrastre: number; arrastre_caduca: string | null; movimientos: number
  disponible: number; usado: number; pedido: number; caducado: number; restante: number; restante_al_cierre: number
  media_diaria_horas: number; equivalente: { unidad: UnidadDeSaldo; restante: number }
  proximas_caducidades: CaducidadDeSaldo[]; retribuido: boolean; tipos?: string[]
}

export interface HuecoDeCupo {
  fecha: string; turno: string | null; grupo: string | null; ocupadas: number; espera: number; libres: number
  /** Rev. 180: franja horaria del cupo si cuenta por franjas. */
  franja: string | null
}
export interface DetalleDeCupo {
  tipo: 'cupo'; clave: string; maximo: number; momento: 'solicitud' | 'aprobacion'; agrupar_por: string
  huecos: HuecoDeCupo[]; lleno: boolean; posicion_estimada: number | null; aplica: boolean; franja_minutos: number
}

export interface AprobacionPrevista {
  orden: number | null; nombre: string | null; tipo: string; aprobador: string | null; rol: string | null; origen: 'flujo' | 'politica'
}
export interface DocumentoPrevisto {
  tipo_id: string; nombre: string; plazo_dias: number; plazo_desde: PlazoDesde; repetir_cada_dias: number | null
  obligatorio: boolean; origen: 'tipo' | 'politica'
}
export interface VistaPreviaDeAusencia {
  decision: 'block' | 'waitlist' | 'review' | 'auto_approve' | 'allow'
  dias: { fecha: string; turno: string | null; office_id: string | null; horas: number; minutos: [number, number][] }[]
  /** Días EQUIVALENTES (2 h de un día de 8 h = 0,25). */
  dias_laborables: number; cantidad: number; unidad: Unidad; saldo: SaldoDeAusencia | null; saldo_restante: number | null
  cupos: DetalleDeCupo[]; aprobaciones: AprobacionPrevista[]; documentos: DocumentoPrevisto[]
  avisos: string[]; bloqueos: string[]; lista_de_espera: boolean; requisitos: string[]
  cobertura_restante: number | null; companeros_ausentes: number
  // Rev. 180
  modo: 'dias' | 'horas'; horas: number; horas_max_dia: number; horas_fuera_de_horario: number
  redondeo: { antes: number; despues: number; minutos: number; modo: string; politica: string | null } | null
  negativo_permitido: number; politicas_que_aplican: { politica: string; reglas: string[] }[]
  saldo_restante_horas: number | null
}

export interface AusenciaServida {
  id: string; user_id: string; user_name: string; type: string; type_label: string; absence_type_id: string | null
  type_color: string; type_icon: string; status: EstadoDeAusencia; status_label: string; status_color: string
  start_date: string; end_date: string; working_days: number | null; amount: number | null; unit: Unidad | null
  hours: number | null; half_day_start: boolean; half_day_end: boolean; shift_id: string | null
  substitute_id: string | null; substitute_name: string | null; reason: string | null; approved_by: string | null
  approved_at: string | null; rejection_reason: string | null; created_at: string | null; requested_at: string | null
  private: boolean
  /** Rev. 180: por horas, la franja de cada día y las horas de horario que cubre. */
  modo: 'dias' | 'horas'; start_time: string | null; end_time: string | null; scheduled_hours: number | null
}

export interface DocumentoDeAusencia {
  id: string; tipo_id: string | null; tipo: string | null; version: number; estado: 'vigente' | 'sustituido'
  sustituye_a: string | null; especial: boolean; puede_ver: boolean; nombre_de_fichero: string | null
  tamano: number | null; nota: string | null; subido_por: string | null; subido_en: string | null
}
export interface RequisitoDeAusencia {
  id: string; tipo_id: string; tipo: string | null; origen: 'tipo' | 'politica' | 'manual'; secuencia: number
  vence: string; estado: 'pendiente' | 'entregado' | 'vencido' | 'dispensado'; nota: string | null
  recordado_en: string | null; escalado_en: string | null
}
export interface EventoDeAusencia { tipo: string; quien: string | null; cuando: string | null; datos: Record<string, unknown> }
export interface PlazaReservada {
  clave: string; fecha: string; turno: string | null; grupo: string | null; estado: 'ocupa' | 'espera'; por_encima: boolean; capacidad: number
}
export interface AprobacionDeAusencia {
  id: string; estado: string; paso_actual: number
  pasos: { orden: number; nombre: string; tipo: string; aprobador: string; rol: string | null }[]
  decisiones: { orden: number; decision: string; nota: string | null; quien: string | null; cuando: string | null }[]
}
export interface ExplicacionResumida {
  decision: string
  explicacion: { politicas: { politica: string; aplica: boolean; motivo?: string; reglas: { regla: string; cumple: boolean | null }[] }[] }
}
export interface DetalleDeAusencia {
  ausencia: AusenciaServida; linea_de_tiempo: EventoDeAusencia[]; documentos: DocumentoDeAusencia[]
  requisitos: RequisitoDeAusencia[]; puede_subir: boolean; plazas: PlazaReservada[]; posicion_en_espera: number | null
  aprobacion: AprobacionDeAusencia | null; puede_gestionar: boolean; explicacion: ExplicacionResumida | null
}

export interface ElementoDeBandeja {
  solicitud_id: string | null; paso: string | null; sin_flujo: boolean; ausencia: AusenciaServida
  explicacion: ExplicacionResumida | null; impacto: CeldaDeCobertura[]; companeros_ausentes: number
  cobertura_restante: number | null; saldo_restante: number | null; plazas: PlazaReservada[]
}

export interface EjemplosCargados {
  turnos: string[]; flujo: string | null; politica: string | null; flujo_id: string; flujo_activo: boolean
  pasos_siguientes: string[]
}
export interface AccesoEspecial { id: string; user_id: string; nombre: string; concedido_por: string | null; created_at: string | null }

// ── Rev. 180: horario efectivo, jornadas, ficha laboral, saldos por persona, festivos ──

export interface AusenciaEnHorario {
  id: string; tipo_id: string | null
  /** 'private' = ausencia privada para quien mira (se pinta «Ausencia» sin tipo). */
  tipo: string
  estado: EstadoDeAusencia; tramos: Tramo[]; horas: number; completa: boolean; modo: 'dias' | 'horas'
  nombre: string | null; color: string | null
}
export interface CeldaDeHorario {
  fecha: string; origen: 'cambio' | 'rotacion' | 'jornada' | 'empresa'; turno_id: string | null; jornada_id: string | null
  tramos: Tramo[]; pausa_minutos: number; festivo: string | null; trabaja_festivo: boolean; fuera_de_contrato: boolean
  laborable: boolean; horas_teoricas: number; horas: number; libres: Tramo[]; etiqueta: string | null; color: string | null
  ausencias: AusenciaEnHorario[]
}
export interface PersonaDeHorario {
  id: string; nombre: string; equipo: string | null; departamento: string | null; sede: string | null
  horas_teoricas: number; horas: number; celdas: Record<string, CeldaDeHorario>
}
export interface HorarioEfectivo {
  desde: string; hasta: string; personas: PersonaDeHorario[]; turnos: Turno[]; jornadas: { id: string; nombre: string; color: string }[]
}
export interface FiltroDeHorario { desde: string; hasta: string; equipo?: string; departamento?: string; user_ids?: string[] }

export type DiaDeSemana = '1' | '2' | '3' | '4' | '5' | '6' | '7'
export type AmbitoDeJornada = 'empresa' | 'sede' | 'departamento' | 'equipo' | 'grupo' | 'persona'
export interface AsignacionDeJornada {
  id: string; jornada_id: string; ambito: AmbitoDeJornada; valor: string | null; desde: string | null; hasta: string | null
  /** Cada año entre esas fechas (jornada de verano). */
  recurrente_anual: boolean; prioridad: number; nota: string | null
}
export type AsignacionDeJornadaIn = Omit<AsignacionDeJornada, 'id'>
export interface Jornada {
  id: string; nombre: string; nombres: Partial<Record<Idioma, string>>; color: string; semana: Record<DiaDeSemana, Tramo[]>
  pausa_minutos: number; horas_por_dia: Record<DiaDeSemana, number>; horas_semana: number; activo: boolean; orden: number
  asignaciones: AsignacionDeJornada[]
}
export type JornadaIn = Pick<Jornada, 'nombre' | 'nombres' | 'color' | 'semana' | 'pausa_minutos' | 'activo' | 'orden'>

export interface FichaLaboral {
  user_id: string; nombre: string; office_id: string | null; hire_date: string | null; employment_type: string | null
  weekly_capacity_hours: number | null; equipo: string | null; departamento: string | null
}
export type FichaLaboralIn = Pick<FichaLaboral, 'office_id' | 'hire_date' | 'employment_type'>

export interface SaldosDePersona { user_id: string; nombre: string; equipo: string | null; departamento: string | null; saldos: SaldoDeAusencia[] }
export interface MovimientoDeSaldo {
  id: string; user_id: string; saldo_clave: string; fecha: string; cantidad: number; unidad: UnidadDeSaldo
  origen: 'manual' | 'bolsa'; referencia: string | null; caduca: string | null; nota: string | null
  created_by: string | null; created_at: string | null
}
export interface AjusteDeSaldoIn {
  user_id: string; saldo_clave: string; cantidad: number; unidad?: UnidadDeSaldo | null; fecha?: string | null
  caduca?: string | null; nota: string
}
export interface RecalculoDeBolsa { tipos: number; personas: number; creados: number; cambiados: number; borrados: number }

export type TipoDeFestivo = 'public' | 'regional' | 'company'
export interface FestivoIn { name: string; date: string; type: string; applies_to: string | null; office_id: string | null }
export interface Festivo extends FestivoIn { id: string }
