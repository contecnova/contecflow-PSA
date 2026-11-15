/**
 * Tipos de ausencias gobernadas por reglas (tarea #25, revisión 167).
 * Espejo de `app/services/ausencias/*` y `app/api/v1/endpoints/ausencias.py`.
 */
export type Unidad = 'dias' | 'medios_dias' | 'horas'
export type Visibilidad = 'todos' | 'equipo' | 'privada'
export type Saldo = 'vacaciones' | 'propio'
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
}
export type TurnoIn = Omit<Turno, 'id' | 'cruza_medianoche' | 'duracion_horas'>

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
}
export interface Cobertura {
  desde: string; hasta: string; turnos: Turno[]; celdas: CeldaDeCobertura[]; festivos: { fecha: string; nombre: string }[]
}

export interface PeticionDeAusencia {
  absence_type_id: string; start_date: string; end_date: string; reason?: string | null; shift_id?: string | null
  substitute_id?: string | null; half_day_start?: boolean; half_day_end?: boolean; hours?: number | null; id?: string
}

export interface SaldoDeAusencia {
  saldo: Saldo; unidad: Unidad; year: number; disponible: number; derecho: number; arrastre: number
  usado: number; pedido: number; restante: number; tipo_id?: string; tipos?: string[]
}

export interface HuecoDeCupo { fecha: string; turno: string | null; grupo: string | null; ocupadas: number; espera: number; libres: number }
export interface DetalleDeCupo {
  tipo: 'cupo'; clave: string; maximo: number; momento: 'solicitud' | 'aprobacion'; agrupar_por: string
  huecos: HuecoDeCupo[]; lleno: boolean; posicion_estimada: number | null; aplica: boolean
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
  dias: { fecha: string; turno: string | null; office_id: string | null }[]
  dias_laborables: number; cantidad: number; unidad: Unidad; saldo: SaldoDeAusencia | null; saldo_restante: number | null
  cupos: DetalleDeCupo[]; aprobaciones: AprobacionPrevista[]; documentos: DocumentoPrevisto[]
  avisos: string[]; bloqueos: string[]; lista_de_espera: boolean; requisitos: string[]
  cobertura_restante: number | null; companeros_ausentes: number
}

export interface AusenciaServida {
  id: string; user_id: string; user_name: string; type: string; type_label: string; absence_type_id: string | null
  type_color: string; type_icon: string; status: EstadoDeAusencia; status_label: string; status_color: string
  start_date: string; end_date: string; working_days: number | null; amount: number | null; unit: Unidad | null
  hours: number | null; half_day_start: boolean; half_day_end: boolean; shift_id: string | null
  substitute_id: string | null; substitute_name: string | null; reason: string | null; approved_by: string | null
  approved_at: string | null; rejection_reason: string | null; created_at: string | null; requested_at: string | null
  private: boolean
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
